"""tests/unit/core/templates/test_placeholder_parser.py -- 占位符 AST、正则与字面量解析单元测试。"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import pytest

from core.templates.router._base import iter_placeholders, split_template_meta
from core.templates.router._detect import parse_placeholder_template
from core.templates.router._gate import scan_fixed_bracket_literals, validate_rendered_output
from core.templates.router._placeholder import plan_placeholder_fill
from tests.unit.core.templates._common import (
    BODY_CAPTION_TPL,
    CAPTION_TPL,
    FAIL,
    FILL_RULE_KEYS,
    FILL_TPL,
    KNOWN_PENDING_BRACKET_LITERALS,
    PASS,
    SCALAR_BASELINE_BY_DIR,
    SHAPE_RULE_KEYS,
    TEMPLATE_SHAPE_SNIPPETS,
    _active_dir,
    check,
)

def test_iter_placeholders() -> None:
    """行级优先：整行 `[...]` 即使内含方括号字面也按一个占位；多对括号仍逐对。"""
    nested = "[明确家校达成的共识、后续配合措施及跟进计划，用 `- [ ]` 待办格式列出双方分工]"
    got = iter_placeholders(nested)
    check("整行占位（说明里带 `- [ ]` 字面）→ 1 个占位且内容为整句",
          len(got) == 1 and got[0].group(1).startswith("明确家校达成的共识") and "- [ ]" in got[0].group(1),
          f"n={len(got)}")
    check("行级占位的位置覆盖整行（供 next_char/切片用）",
          len(got) == 1 and nested[got[0].start() : got[0].end()] == nested,
          f"span={got[0].span() if got else None}")
    pair = iter_placeholders("[A] 与 [B]")
    check("一行两对括号仍逐对匹配（不回退成整行吞掉）",
          len(pair) == 2 and [m.group(1) for m in pair] == ["A", "B"], f"{[m.group(1) for m in pair]}")
    two_lines = "第一行 [甲]\n第二行 [乙]"
    spans = iter_placeholders(two_lines)
    check("多行时位置仍相对整段（跨行偏移正确）",
          len(spans) == 2
          and two_lines[spans[0].start() : spans[0].end()] == "[甲]"
          and two_lines[spans[1].start() : spans[1].end()] == "[乙]",
          f"{[m.span() for m in spans]}")
    for raw in ("| [维度] | … |", "- [具体内容描述]", "# [栏目标题]", "段落里的 [小括号] 说明"):
        m = iter_placeholders(raw)
        check(f"常规行不受影响：{raw[:22]}", len(m) >= 1, f"n={len(m)}")

def test_line_placeholders_filters_noise() -> None:
    """`_line_placeholders` 仍过滤掉不像占位符的括号（JSON/链接残留）。"""
    from core.templates.router._placeholder import _line_placeholders

    check("不像占位符的整行括号被过滤（如 `[x]`）", _line_placeholders("[x]") == [], "")
    check("像占位符的说明行被保留", len(_line_placeholders("[一段话概括会议主要内容与结论]")) == 1, "")

def test_parser_sees_field_not_text() -> None:
    """含字面 `[ ]` 的说明行应解析成**字段**，而不是固定文字段。"""
    tpl = (
        "# [沟通概况]\n[一段话概括沟通双方与主题]\n\n"
        "# [共识与配合事项]\n[明确家校共识与分工，用 `- [ ]` 待办格式列出双方分工]\n"
    )
    segs = parse_placeholder_template(tpl)
    kinds = [s["kind"] for s in segs]
    check("说明行解析为字段（不再是 text 段）", kinds.count("field") == 2, f"kinds={kinds}")
    check("固定段里不再出现带方括号的说明", scan_fixed_bracket_literals(tpl) == [],
          f"{scan_fixed_bracket_literals(tpl)}")

def test_prompt_allows_sub_headings() -> None:
    """渲染规则（PLACEHOLDER_RULES/BODY_FORMAT_RULES）允许字段值内用下级标题分板块，只禁与栏目标题同名/同级。

    背景：模板里「二级标题写成员/模块」「多层级结构」这类说明，原先被 prompt 的
    "不要写 Markdown 标题（# / ##）"一刀切挡住 → 改成"只禁同级 `#`、允许 `##`/`###`"后两边口径一致。
    """
    from core.templates.body_rules import BODY_FORMAT_RULES
    from core.templates.template_prompt import PLACEHOLDER_RULES

    prompt = PLACEHOLDER_RULES
    check("模板规则包含树状两级分组规则与 ## 组名许可",
          "## 组名" in prompt and "树状两级" in prompt, "")
    check("模板规则不再一刀切禁止写标题",
          "不要写 Markdown 标题" not in prompt, "")
    check("仍保留「禁止同名重复」保护（禁止把栏名当标签复述）",
          "禁止同名重复" in prompt and "不得把栏名当标签复述" in prompt, "")

def test_buggy_template_now_works() -> None:
    """两条历史坏损模板（模板文件未改也应被代码修复救回）：末栏恢复为字段。"""
    tdir = _active_dir()
    for tid, head in (("home_school_liaison", "明确家校达成成的共识"), ("legal_advisory", "明确律师给出的解决方案")):
        p = tdir / f"{tid}.md"
        if not p.is_file():
            continue
        fmt, _ = split_template_meta(p.read_text(encoding="utf-8"))
        hints = [str(s.get("raw")) for s in plan_placeholder_fill(fmt)["scalars"]]
        ok = len(hints) >= 4 and (hints[-1].startswith(head[:8]) or hints[-1].startswith("明确"))
        check(f"{tid}：末栏恢复为可填字段（不再退化成固定文案）", ok, f"字段数={len(hints)}")


FILL_TPL = (
    "# [甲栏]\n[一段话概括甲栏内容]\n\n"
    "# [乙栏]\n[一段话概括乙栏内容]\n\n"
    "# [丙栏]\n[一段话概括丙栏内容]\n"
)

def test_placeholder_route_rules() -> None:
    """Fast Render 路由层：对占位符模板自动判定并下发 PLACEHOLDER_RULES 完整规则契约。"""
    from core.templates.router import route_template

    routed = route_template("内容来源：略。", FILL_TPL, "无模板系统提示", "模板基础提示\n")
    check("route_template 正确分派占位符模板", routed is not None, "")
    if routed is not None:
        sys_prompt, user_msg = routed
        check("系统提示词包含模板基础规则与 PLACEHOLDER_RULES", "模板基础提示" in sys_prompt and "占位符模板" in sys_prompt, "")
        check("系统提示词包含形态排版规则", "树状两级" in sys_prompt, "")
        check("用户消息包含内容来源与模板原文", "内容来源：略。" in user_msg and "模板原文：" in user_msg, "")
        check("用户消息包含模板结构解析", "【模板结构解析】" in user_msg, "")


CAPTION_TPL = (
    "# [甲栏]\n[一段话概括甲]\n\n"
    "# [进度追踪]\n"
    "[按下表逐行填写各模块的进展与当前状态（一行一个模块）；不要另建表格，表内已写的明细不在别处重复]\n\n"
    "| 模块 | 进展 |\n| --- | --- |\n| … | … |\n\n"
    "# [乙栏]\n[一段话概括乙]\n"
)
BODY_CAPTION_TPL = (
    "# [治疗方案与医嘱]\n"
    "[医嘱清单：检查安排、用药、生活方式、复诊与陪同要求各占一条，每条都是 `- ` 分点行；药品明细只写进下表]\n\n"
    "| 药名 | 剂量 |\n| --- | --- |\n| … | … |\n"
)

def test_table_caption_not_a_field() -> None:
    """表格栏说明：不进字段清单、不打印正文位、不吃掉其它字段的值。

    背景（2026-09，now.xlsx 实测）：`[按下表逐行填写…]` 紧跟表格时被当成必填正文字段，
    模型把明细全写进表格后只能填「未提及」→ 产出「标题 + 未提及 + 九行表格」的自相矛盾形态
    （项目进度会的进度追踪/风险预警、面试报告的能力评估）；庭审记录则把诉辩表改写成散文。
    """
    from core.templates.router._base import is_table_caption, table_caption_lines
    from core.templates.router._placeholder import assemble_placeholder_output, plan_placeholder_fill

    plan = plan_placeholder_fill(CAPTION_TPL)
    hints = [str(s.get("hint") or "") for s in plan["scalars"]]
    check("表格栏说明不进字段清单（甲/乙两栏 + 1 张表）",
          len(plan["scalars"]) == 2 and len(plan["row_templates"]) == 1, f"{hints}")
    check("紧跟表格的说明行被判为表格栏说明", table_caption_lines(CAPTION_TPL) == {4},
          f"{table_caption_lines(CAPTION_TPL)}")
    check("要求正文的医嘱清单不被误判（要 `- ` 分点）",
          not is_table_caption("医嘱清单：检查安排、用药各占一条，每条都是 `- ` 分点行")
          and table_caption_lines(BODY_CAPTION_TPL) == set(),
          f"{table_caption_lines(BODY_CAPTION_TPL)}")

    out = assemble_placeholder_output(
        CAPTION_TPL, {"1": "甲内容。", "2": "乙内容。"}, tables=[[["模块A", "进行中"]]]
    )
    check("拼装：说明行不打印、表格照常输出", "按下表逐行填写" not in out and "模块A" in out, "")
    check("拼装：不产生「未提及」正文", "未提及" not in out, f"{out!r}")
    check("拼装：后面的字段不错位（乙栏拿到自己的值）",
          "# 乙栏\n乙内容。" in out.replace("\r\n", "\n"), f"{out!r}")

def test_first_column_min() -> None:
    """总述栏（第 1 栏）下限：按原文规模算（tier 下限的 22%，夹 180–400），写进【篇幅预算】。

    回归背景（2026-09 now.xlsx 实测 56 条）：首栏汉字中位数约 150（最薄 88），
    而通用兜底只给了上限（≤3 段/≤400 字）——上限治不了薄；下限只给第 1 栏，明细栏不逼。
    """
    from core.templates.length_budget import budget_line, first_column_min

    check("首栏下限：<3k 档取地板 180", first_column_min(2999) == 180, f"{first_column_min(2999)}")
    check("首栏下限：3k–8k 档＝tier 下限 ×22%", first_column_min(5000) == 238, f"{first_column_min(5000)}")
    check("首栏下限：8k–20k 档", first_column_min(12000) == 370, f"{first_column_min(12000)}")
    check("首栏下限：≥20k 档封顶 400", first_column_min(30000) == 400, f"{first_column_min(30000)}")
    check("首栏下限：原文过短（<300 汉字）不约束", first_column_min(200) is None, f"{first_column_min(200)}")

    line = budget_line(5000)
    check("【篇幅预算】写明第 1 栏口径与具体下限",
          "第 1 栏（概况/总述）" in line and "参考下限 238 汉字" in line, f"{line[-130:]}")
    check("过短原文不注入第 1 栏口径", "第 1 栏" not in budget_line(200), f"{budget_line(200)!r}")
    check("首栏口径不含「全文/合计」类整篇标记（避免被解析成全文上限）",
          not any(k in line.split("第 1 栏")[1] for k in ("全文", "整篇", "通篇", "合计", "总共")),
          f"{line[-130:]}")

def test_section_char_budget_scope() -> None:
    """段落字数上限：栏名要取到（`# [概况]` → 概况）；单条预算不许当整节上限。

    回归背景：栏名用 `re.sub(r"\\[[^\\[\\]]*\\]", "", ...)` 连括号内容一起删掉 →
    拿到「本节」，_overlong_issue 的标题匹配永不命中（模板声明的上限静默失效）；
    而只修标题又会让「每条 30–100 字」被当成整节 100 字上限（合规的 5 条会被判超限返工）。
    """
    from core.templates.template_eval import parse_section_char_budgets

    para_tpl = "# [概况]\n[只写 3–6 句概览；**单段不超过约 200 字**，信息多就拆段]\n"
    item_tpl = "# [要点]\n[每个维度一行；每条 30–100 字，信息多就拆条]\n"
    both_tpl = "# [要点]\n[每条 30–100 字；本栏约 400 字]\n"

    para = parse_section_char_budgets(para_tpl)
    check("段落上限：栏名取到（不再退化成「本节」）",
          bool(para) and para[0]["title"] == "概况", f"{para}")
    check("段落上限：单段预算标为 paragraph",
          bool(para) and para[0].get("scope") == "paragraph", f"{para}")
    check("段落上限：上限值取 200",
          bool(para) and para[0]["hi"] == 200, f"{para}")

    item = parse_section_char_budgets(item_tpl)
    check("单条预算（每条 30–100 字）不产生整节上限", not item, f"{item}")

    both = parse_section_char_budgets(both_tpl)
    check("单条 + 整节并存时只留整节预算（400）",
          bool(both) and both[0]["hi"] == 400 and both[0].get("scope") == "section",
          f"{both}")

def test_default_word_precedence() -> None:
    """缺省词口径：模板约定优先，通用层只兜底「未提及」（模板文件不改）。

    回归背景：通用层曾写死「责任人列无则「未明确」」，与项目进度会模板要求的
    「缺项直接写「无」」冲突——同一行里同时出现「未明确」和「无」两种缺省词。
    """
    from domains.meeting.tasks.minutes.prompts import MINUTES_RENDER_TEMPLATE_PROMPT
    from core.templates.body_rules import BODY_FORMAT_RULES
    from core.templates.template_prompt import PLACEHOLDER_RULES

    for label, text in (
        ("自由渲染 PLACEHOLDER_RULES", PLACEHOLDER_RULES),
        ("共用形态规则", BODY_FORMAT_RULES),
        ("纪要模板渲染 prompt", MINUTES_RENDER_TEMPLATE_PROMPT),
    ):
        check(
            f"{label}：缺省词按模板约定、通用层只兜底「未提及」",
            "模板没约定" in text or "未约定时写「未提及」" in text,
            "",
        )
    stale = [
        k
        for k in ("无则「未明确」", "缺内容直接写「未提及」")
        if k in PLACEHOLDER_RULES or k in BODY_FORMAT_RULES or k in MINUTES_RENDER_TEMPLATE_PROMPT
    ]
    check("通用层不再强推单一缺省词（旧写法已清除）", not stale, f"残留={stale}")

def test_document_budget_not_misread() -> None:
    """全文预算不许从"段落说明里顺带出现的全文标记"误判出来。

    回归背景（2026-09 性能复盘）：general_minutes 的摘要说明同时写了「（摘要通篇无数字＝不合格）」与
    「每段不超过 400 字」——"通篇"命中全文标记，于是整份纪要（600–2600 字）被判
    「超出全文上限 400 字」：触发压缩返工（多一次整篇 LLM 调用），freeform 路径还会按句界
    截断到 ~420 字（既慢又丢内容）。
    """
    from core.templates.template_eval import (
        parse_document_char_budget,
        parse_section_char_budgets,
    )

    from core.templates.router._base import split_template_meta, wrap_template_requirement

    def runtime_tpl(text: str) -> str:
        body, req = split_template_meta(text)
        lines = body.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("# "):
                lines = lines[i + 1 :]
                break
        return wrap_template_requirement("\n".join(lines).strip(), req)

    trap = (
        "# 甲\n\n<!-- requirement\n客观记录\n-->\n\n"
        "# [摘要]\n[一段话（最多 3 段、每段不超过 400 字）交代要点（通篇无数字＝不合格）]\n"
    )
    tpl = runtime_tpl(trap)
    check("段落说明里的全文标记不产生全文预算",
          not parse_document_char_budget(tpl).get("hi"),
          f"{parse_document_char_budget(tpl)}")
    check("同一栏的段落预算仍能识别",
          any(
              b["hi"] == 400 and b.get("scope") == "paragraph"
              for b in parse_section_char_budgets(tpl)
          ),
          f"{parse_section_char_budgets(tpl)}")
    real = runtime_tpl(
        "# 乙\n\n<!-- requirement\n全文合计约200-300字，覆盖背景与结论\n-->\n\n# [摘要]\n[写点东西]\n"
    )
    check("真·全文预算（标记贴着数字）仍被识别",
          parse_document_char_budget(real).get("hi") == 300, f"{parse_document_char_budget(real)}")
    misread = [
        md.stem
        for md in sorted(_active_dir().glob("*.md"))
        if md.stem.lower() not in {"readme", "diff"}
        and parse_document_char_budget(runtime_tpl(md.read_text(encoding="utf-8"))).get("hi")
    ]
    check("模板目录里没有被误判的全文预算", not misread, f"误判={misread}")

def test_paragraph_cap_from_explicit_per_para() -> None:
    """单段字数上限以「单段/每段」旁边的数字为准；节级预算的栏也要兜单段。

    回归背景（2026-09-18）：[访谈概述] 只写「约 250–400 字」，解析成**节级**预算 →
    拆段函数（只吃段落级）跳过它，实测 418 字单段静默不拆、517 字只有一条软提示。
    修法：① 栏说明补「单段不超过 300 字」；② 「单段/每段」旁的数成为段落上限
    （区间会盖过它）；③ 节级预算的栏，单段超过整节上限也拆。
    """
    from core.execution.gate import split_overlong_paragraphs
    from core.templates.template_eval import parse_section_char_budgets

    han = lambda t: len([c for c in t if "\u4e00" <= c <= "\u9fff"])
    interview = (_active_dir() / "interview_transcript.md").read_text(encoding="utf-8")
    check("采访记录：概况栏为一段 250–400（不再写单段 300 + 分 2 段）",
          "一段写完，约 250–400 字" in interview and "单段不超过 300 字" not in interview, "")
    caps = [b for b in parse_section_char_budgets(interview) if b["title"] == "访谈概述"]
    check("采访记录：概况栏解析出节级预算 250–400",
          bool(caps) and caps[0]["scope"] == "section" and caps[0]["hi"] == 400, f"{caps}")
    prog = (_active_dir() / "project_progress.md").read_text(encoding="utf-8")
    pcaps = [b for b in parse_section_char_budgets(prog) if b["title"] == "项目概况"]
    check("项目进度会：概况栏节级预算 lo ≤ hi",
          bool(pcaps) and int(pcaps[0]["lo"] or 0) <= int(pcaps[0]["hi"]), f"{pcaps}")

    long_para = "这是受访者的观点与结论。" * 38  # ≈418 汉字
    doc = "# 采访记录\n\n# 访谈概述\n" + long_para + "\n"
    fixed, notes = split_overlong_paragraphs(doc, interview)
    parts = [p.strip() for p in fixed.split("# 访谈概述", 1)[1].split("\n\n") if p.strip()]
    check("采访记录：418 字单段被拆（节级 400 兜单段）",
          bool(notes) and len(parts) >= 2 and max(han(p) for p in parts) <= 400,
          f"段长={[han(p) for p in parts]} {notes}")

    # 节级预算的栏（无「单段/每段」字样）也要兜单段：超过整节上限即拆
    lecture = (_active_dir() / "special_lecture.md").read_text(encoding="utf-8")
    lcaps = [b for b in parse_section_char_budgets(lecture) if b["title"] == "讲座概况"]
    check("专题讲座：概况栏仍是节级预算（用于验证节级兜底）",
          bool(lcaps) and lcaps[0]["scope"] == "section", f"{lcaps}")
    long2 = "这是讲座的主旨与结论。" * 45  # 450 汉字 > 400（节级上限）
    doc2 = "# 专题讲座\n\n# 讲座概况\n" + long2 + "\n"
    fixed2, notes2 = split_overlong_paragraphs(doc2, lecture)
    parts2 = [p.strip() for p in fixed2.split("# 讲座概况", 1)[1].split("\n\n") if p.strip()]
    check("专题讲座：节级预算下 440 字单段也会被拆（节上限即单段上界）",
          bool(notes2) and len(parts2) >= 2, f"段长={[han(p) for p in parts2]} {notes2}")

    # ② 父节预算继承：带 `## 子标题` 的栏目不能再让段落上限失效
    tpl_para_text = (
        "# 研讨速览\n\n"
        "## [研讨速记]\n"
        "[一段话描述该段，每段最多 250 字]\n\n"
        "## [全文摘要]\n"
        "[一段话（一段写完，约 250–400 字）交代主旨]\n"
    )
    gcaps = [b for b in parse_section_char_budgets(tpl_para_text) if b["title"] == "研讨速记"]
    check("段落级预算 (200,250) 解析生效",
          bool(gcaps) and gcaps[0]["hi"] == 250 and gcaps[0]["scope"] == "paragraph", f"{gcaps}")
    para_sub = "这是一段概览文字。" * 55  # ≈440 汉字，单段
    for label, doc in (
        ("无子标题", "# 研讨速览\n\n# 研讨速记\n" + para_sub + "\n"),
        ("带 ## 时间段", "# 研讨速览\n\n# 研讨速记\n## 08:00-12:30 现场检查\n" + para_sub + "\n"),
    ):
        fixed, notes = split_overlong_paragraphs(doc, tpl_para_text)
        seg_parts = [q for q in fixed.split("\n\n") if "概览文字" in q]
        check(f"带子标题栏目 440 字段按 250 字上限拆分（{label}）",
              bool(notes) and len(seg_parts) >= 2
              and max(sum(1 for c in q if "一" <= c <= "鿿") for q in seg_parts) <= 260,
              f"段数={len(seg_parts)} {notes}")

    # ③ 声明只作用于本栏：同一文档里其它栏（全文摘要）仍按节级上限拆
    doc4 = (
        "# 研讨速览\n\n# 全文摘要\n" + para_sub
        + "\n\n# 研讨速记\n## 08:00-12:30 现场检查\n" + para_sub + "\n"
    )
    fixed4, notes4 = split_overlong_paragraphs(doc4, tpl_para_text)
    abs_part = fixed4.split("# 全文摘要", 1)[1].split("# 研讨速记", 1)[0]
    check("两栏各自按自己的上限拆（摘要节级 400 / 速记段落级 250）",
          any("全文摘要" in n for n in notes4)
          and len([q for q in abs_part.split("\n\n") if "概览文字" in q]) >= 2,
          f"{notes4}")

    # ④ 单句超长（句界拆不动）→ 仍必须报「超出段落字数上限」，不能静默
    from core.execution.gate import _overlong_issue

    gm = (_active_dir() / "general_minutes.md").read_text(encoding="utf-8")
    one = "这是一句没有任何句号的超长段落" + "持续延伸内容" * 80 + "。"
    doc3 = "# 通用纪要\n\n# 全文摘要\n" + one + "\n"
    over = _overlong_issue(gm, doc3) or ""
    check("通用纪要：摘要栏单句超长仍报超限（不再静默）",
          "超出段落字数上限" in over and "全文摘要" in over, over[:80])

    # ⑤ 自适应切分：产物以 ## 划分各栏时，后序栏目不被误吞进首栏
    from core.execution.hard_execution import _top_level_sections

    prog_text = (_active_dir() / "project_progress.md").read_text(encoding="utf-8")
    doc_h2 = (
        "## 项目概况\n\n本阶段项目整体按期推进，关键接口已完成联调，核心风险处于可控状态。\n\n"
        "## 进度追踪\n\n| 模块 | 进展 | 状态 |\n| 认证 | 已上线 | 正常 |\n\n"
        "## 风险预警\n\n| 风险/瓶颈 | 等级 | 影响 | 责任人 | 应对计划 |\n| 压测延期 | 中 | 延迟 | 张三 | 增加资源 |\n\n"
        "## 后续计划\n\n- **联调验收**：完成端到端联调 + 测试组 + 下周三\n"
    )
    secs = _top_level_sections(doc_h2)
    sec_names = [s[0].strip("# ").strip() for s in secs]
    check("H2 产物能正确切分各栏目（不吞进首栏）",
          "项目概况" in sec_names and "进度追踪" in sec_names and "后续计划" in sec_names,
          f"{sec_names}")
    budget_err = _overlong_issue(prog_text, doc_h2)
    check("H2 产物各栏目独立核算字数（首栏不误报超限）", budget_err is None, f"{budget_err}")

def test_default_minutes_template() -> None:
    """纪要线不传模板 → 自动路由到「通用纪要」（不再走无模板自由渲染）。

    回归背景（2026-09-18 实测无模板纪要）：完全听模型的——栏目自定、无缺省词、
    无段落上限、不跑模板门禁（同一份原文 6410 汉字 / 最长单行 515 字 / 超篇幅上限 16% 无人管）。
    """
    from app.config import DEFAULT_MINUTES_TEMPLATE
    from app.tasks import _template_file

    check("默认纪要模板常量为 general_minutes",
          DEFAULT_MINUTES_TEMPLATE == "general_minutes", DEFAULT_MINUTES_TEMPLATE)

    auto = _template_file("meeting", "minutes", "")
    check("纪要线留空 → 自动套用模板（返回模板文件）", auto is not None, f"{auto}")
    if auto is not None:
        text = auto.read_text(encoding="utf-8")
        check("自动套用的就是「通用纪要」（含全文摘要/要点梳理栏）",
              "# [全文摘要]" in text and "# [要点梳理]" in text, text[:60])
    check("其它线留空仍不套模板（minutes_trace）",
          _template_file("meeting", "minutes_trace", "") is None, "")
    check("其它域留空仍不套模板（notes/catalog）",
          _template_file("notes", "catalog", "") is None, "")

    from app.tasks import ApiError

    try:
        _template_file("meeting", "minutes", "不存在的模板")
        raised = False
    except ApiError:
        raised = True
    check("显式传入非法模板仍 400（不静默套默认）", raised, "")
    check("显式传入合法模板照旧生效",
          _template_file("meeting", "minutes", "项目进度会") is not None, "")

def test_ellipsis_table_row_template_recognized() -> None:
    """省略号样例行（`| … |`）也要被认成表格行模板——否则空表/缺表/行数检查整体失效。

    回归背景（2026-09-18 第27条实测）：就医咨询药品表只有表头没有数据行，但
    extract_template_table_constraints 只认 `[...]` 占位 → constraints=[] →
    「表格无有效数据行」对这类模板永不触发，空表静默落盘。
    """
    from core.templates.template_eval import (
        evaluate_output_against_template,
        extract_template_table_constraints,
    )

    advisory = (_active_dir() / "clinical_advisory.md").read_text(encoding="utf-8")
    cons = extract_template_table_constraints(advisory)
    check("就医咨询：`| … |` 样例表被认成约束（section=治疗方案与医嘱）",
          bool(cons) and "[治疗方案与医嘱]" in cons[0]["section_title"], f"{cons}")

    art = (
        "# 就医咨询\n\n"
        "# [治疗方案与医嘱]\n"
        "- **用药**：医生开了药。\n\n"
        "| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |\n"
        "| --- | --- | --- | --- | --- |\n"
    )
    check("表头在、数据行缺失 → 报「表格无有效数据行」（硬伤，走 repair）",
          "表格无有效数据行" in evaluate_output_against_template(advisory, art)[0]
          if evaluate_output_against_template(advisory, art) else False,
          f"{evaluate_output_against_template(advisory, art)}")

    # 顺带钉住 row-hint 的两个误判源（会把"形态/泛指"读成行数上限）
    from core.templates.template_eval import parse_row_hint

    check("「不要用连续多行独占一行的…」不是 1 行上限",
          parse_row_hint("不要用连续多行独占一行的 `**类别**：` 段落代替分点") is None, "")
    check("「每行一个X」是形态要求不是数量", parse_row_hint("每行一个事项") is None, "")
    check("「最多 3 行」仍是真上限", parse_row_hint("最多 3 行") == 3, "")

    # 真实产物回归：正常带数据的表不再被"约需 1 行"误伤
    for stem, artifact in (
        ("clinical_advisory", "5b17e044d210441a87bce540540b7163"),
        ("debate_forum", "67648012"),
        ("project_progress", "dff4ac29"),
    ):
        tpl = (_active_dir() / f"{stem}.md").read_text(encoding="utf-8")
        matches = sorted(Path("data/test/output").glob(f"{artifact}*/result.md"))
        if not matches:
            continue
        issues = [
            x
            for x in evaluate_output_against_template(tpl, matches[0].read_text(encoding="utf-8", errors="ignore"))
            if "行（超出）" in x
        ]
        check(f"{stem}：带数据行不被「约需 1 行」误判", not issues, f"{issues[:1]}")

def test_output_volume_and_hierarchy() -> None:
    """总量天花板 + 理解层限流 + 两级层级标准（治"太平、太碎、超原文"）。

    用户指出（2026-09-19）：① 纪要超原文；② 挖得太细太碎、耗时长；③ 层级太平难浏览。
    根因：理解层"宁多不漏"全量抽取 → 草稿"把细节写开" → 渲染"每一项写足"，
    装配规则还允许"与原文同量级 90%–110%"。
    """
    import pathlib

    from core.templates.length_budget import capped_budget

    check("天花板：原文 ×80% 与档位取小（3500 字原文 → 上限 2800）",
          capped_budget(3500) == (1080, 2800), f"{capped_budget(3500)}")
    check("天花板：30000 字原文仍受档位上限约束（8000）",
          capped_budget(30000) == (2400, 8000), f"{capped_budget(30000)}")
    bl = __import__("core.templates.length_budget", fromlist=["budget_line"]).budget_line(3500)
    check("【篇幅预算】写明不超过原文 80%",
          "任何情况下不超过原文的 80%" in bl, bl[:120])
    check("【篇幅预算】下限口径收窄（补关键事实，不扩写寒暄与过程）",
          "不扩写寒暄与过程铺陈" in bl, "")

    u = pathlib.Path("domains/meeting/meeting_core/prompts.py").read_text(encoding="utf-8")
    check("理解层：key_points 每议题 ≤8 条、全篇 ≤30 条（按支撑力取舍）",
          "每议题最多 8 条、全篇最多 30 条" in u, "")
    check("理解层：寒暄/程序性发言不进索引",
          "过程性重复、寒暄、程序性发言不进索引" in u, "")
    check("理解层：同一事实重复表述只留信息最全的一条",
          "同一事实的多次重复表述只留信息最全的一条" in u, "")

    br = pathlib.Path("core/templates/body_rules.py").read_text(encoding="utf-8")
    check("层级标准：栏内条目超 6 条必须归组（每组 2–5 条）",
          "超过 6 条时必须归组" in br and "每组 2–5 条" in br, "")
    mp = pathlib.Path("domains/meeting/tasks/minutes/prompts.py").read_text(encoding="utf-8")
    check("渲染：两级结构是默认形态（旧的分组禁令已反转）",
          "两级结构是默认形态" in mp and "纪要正文一律不用" not in mp, "")
    check("渲染：写清结论/关键数字/责任人/时限（过程铺陈压缩）",
          "结论、关键数字、责任人、时限" in mp and "过程铺陈压缩" in mp, "")
    check("草稿：写开对象收窄（过程铺陈与背景默认压缩）",
          "过程铺陈与背景默认压缩成半句" in mp, "")

def test_domain_specific_accuracy_rules() -> None:
    """医疗、招生、媒体和庭审模板保留各自的事实边界。"""
    d = _active_dir()

    admission = (d / "admission_briefing.md").read_text(encoding="utf-8")
    check("招生宣讲：关键数据栏排除联系方式与行动型时间节点",
          "联系方式、咨询渠道、报名/材料截止等行动型时间节点不得放入本栏" in admission
          and "统一归 [后续联系与行动]" in admission, "")
    check("招生宣讲：联系方式与行动时间集中到后续联系栏",
          "全部联系方式、咨询渠道和行动型时间节点" in admission
          and "这些内容不再写入 [关键数据与信息]" in admission, "")
    key_data = admission.split("# [关键数据与信息]", 1)[1].split("# [Q&A 环节]", 1)[0]
    check("招生宣讲：关键数据样例表不再含联系方式/关键时间节点行",
          "| 联系方式 |" not in key_data and "| 关键时间节点 |" not in key_data, key_data[-160:])

    media = (d / "media_qa_session.md").read_text(encoding="utf-8")
    check("媒体问答：确定的转写错误可校正，数字/人名须有上下文证据",
          "上下文能够唯一确认的转写错误可以校正" in media
          and "时间、数字、人名只有在同一原文存在明确上下文证据时才可校正" in media
          and "证据不足时保留原写法" in media, "")
    check("媒体问答：旧的绝对不修正口径已移除", "不做修正、不改写" not in media, "")

    court = (d / "court_transcript.md").read_text(encoding="utf-8")
    for need in (
        "当事人主张、代理人意见、证人陈述、鉴定意见、其他来源陈述与法院查明/认定必须分别标明来源",
        "不得把任何一方陈述改写成客观事实或法院结论",
        "证据内容不等于法院已采信事实",
        "只有原文明示的法院查明、认定、裁定、判决",
        "尚未裁判",
    ):
        check(f"庭审记录：含事实归属规则「{need}」", need in court, "")
    # 庭审记录重构：法庭调查彻底移除预设组名，按事实要点自适应以清单项平铺展开
    check("庭审记录：法庭调查彻底移除预设组名，改为自适应事项清单",
          "不设预设大类" in court
          and "证人证言、鉴定意见或第三方材料明确标明陈述人或来源" in court
          and "## 证人、鉴定与其他来源陈述" not in court
          and "## 证人/鉴定陈述" not in court, "")
    check("庭审记录：法庭调查按案情推进写全（全场无记录才写未提及）",
          "全场无调查与举证写「未提及」" in court, "")
    # 2026-09-20 本批 8 份庭审产物实测：[庭审结果] 8/8 都是单段、204–310 汉字，
    # 段内 5–8 个「；」把 6–9 项内容压在一起（争议焦点/调解结果/金额权利安排/履行期限），
    # 关键金额埋在长句里；该栏是模板里**唯一没有声明形态、也没有尺寸**的栏
    # （诉辩栏有表格、举证栏有四部分 `##`）→ 模型没有可依附的结构，只能写成一段。
    # 用户口径：按点分述，且**不放示例项目名清单**（示例会被照抄成固定标签）。
    res_spec = next(l.strip() for l in court.splitlines() if l.startswith("[归纳"))
    check("庭审记录：[庭审结果] 改为一项一条分述（不挤成一段）",
          "一项一条分述" in res_spec and "不要挤成一段" in res_spec
          and "`- **项目名**：内容`" in res_spec, res_spec[:80])
    check("庭审记录：[庭审结果] 保留来源纪律（当事人主张不得写成法院认定）",
          "只有原文明示的法院查明、认定、裁定、判决、调解结果或下次开庭安排才能作为结果" in res_spec
          and "不得写成法院认定" in res_spec, "")
    check("庭审记录：[庭审结果] 金额/比例/期限照原文，多安排用子条",
          "金额、比例、履行期限照原文写全" in res_spec
          and "需要拆分时用缩进子条 `  - `" in res_spec, "")
    check("庭审记录：[庭审结果] 保留「尚未裁判」口径与不硬凑",
          "尚未裁判时写「尚未裁判」并列出未决事项" in res_spec and "没有的不写" in res_spec, "")
    check("庭审记录：[庭审结果] 不再出现示例式项目名清单（软引导已清除）",
          "`- **争议焦点**：…`" not in court and "`- **法院查明**：…`" not in court
          and "`- **合议庭认定**：…`" not in court and "`- **裁判/调解结果**：…`" not in court
          and "`- **未决事项**：…`" not in court, "")
    understanding = Path("domains/meeting/meeting_core/prompts.py").read_text(encoding="utf-8")
    check("会议理解：有立场的陈述必须保留归属，不升级成事实",
          "陈述归属不得丢" in understanding and "不得把一方说法改写成客观事实" in understanding
          and "才能写成已认定事实" in understanding, "")

