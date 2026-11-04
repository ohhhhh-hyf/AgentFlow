# 拆分自 test_placeholder_parser.py，覆盖：test_first_column_min, test_section_char_budget_scope, test_default_word_precedence…

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
from tests.support.expectations import expect
from tests.unit.core.templates._common import (
    BODY_CAPTION_TPL,
    CAPTION_TPL,
    FILL_RULE_KEYS,
    FILL_TPL,
    KNOWN_PENDING_BRACKET_LITERALS,
    SCALAR_BASELINE_BY_DIR,
    SHAPE_RULE_KEYS,
    TEMPLATE_SHAPE_SNIPPETS,
    _active_dir,
)

pytestmark = pytest.mark.integration

FILL_TPL = (
    "# [甲栏]\n[一段话概括甲栏内容]\n\n"
    "# [乙栏]\n[一段话概括乙栏内容]\n\n"
    "# [丙栏]\n[一段话概括丙栏内容]\n"
)

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

def test_first_column_min() -> None:
    """总述栏（第 1 栏）下限：按原文规模算（tier 下限的 22%，夹 180–400），写进【篇幅预算】。

    回归背景（2026-09 now.xlsx 实测 56 条）：首栏汉字中位数约 150（最薄 88），
    而通用兜底只给了上限（≤3 段/≤400 字）——上限治不了薄；下限只给第 1 栏，明细栏不逼。
    """
    from core.templates.length_budget import budget_line, first_column_min

    expect(first_column_min(2999) == 180, "首栏下限：<3k 档取地板 180", f"{first_column_min(2999)}")
    expect(first_column_min(5000) == 238, "首栏下限：3k–8k 档＝tier 下限 ×22%", f"{first_column_min(5000)}")
    expect(first_column_min(12000) == 370, "首栏下限：8k–20k 档", f"{first_column_min(12000)}")
    expect(first_column_min(30000) == 400, "首栏下限：≥20k 档封顶 400", f"{first_column_min(30000)}")
    expect(first_column_min(200) is None, "首栏下限：原文过短（<300 汉字）不约束", f"{first_column_min(200)}")

    line = budget_line(5000)
    expect("第 1 栏（概况/总述）" in line and "参考下限 238 汉字" in line, "【篇幅预算】写明第 1 栏口径与具体下限", f"{line[-130:]}")
    expect("第 1 栏" not in budget_line(200), "过短原文不注入第 1 栏口径", f"{budget_line(200)!r}")
    expect(not any(k in line.split("第 1 栏")[1] for k in ("全文", "整篇", "通篇", "合计", "总共")), "首栏口径不含「全文/合计」类整篇标记（避免被解析成全文上限）", f"{line[-130:]}")


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
    expect(bool(para) and para[0]["title"] == "概况", "段落上限：栏名取到（不再退化成「本节」）", f"{para}")
    expect(bool(para) and para[0].get("scope") == "paragraph", "段落上限：单段预算标为 paragraph", f"{para}")
    expect(bool(para) and para[0]["hi"] == 200, "段落上限：上限值取 200", f"{para}")

    item = parse_section_char_budgets(item_tpl)
    expect(not item, "单条预算（每条 30–100 字）不产生整节上限", f"{item}")

    both = parse_section_char_budgets(both_tpl)
    expect(bool(both) and both[0]["hi"] == 400 and both[0].get("scope") == "section", "单条 + 整节并存时只留整节预算（400）", f"{both}")


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
        expect("模板允许省略" in text or "模板没约定" in text,
               f"{label}：缺省词按模板约定、通用层只兜底「未提及」", "")
    stale = [
        k
        for k in ("无则「未明确」", "缺内容直接写「未提及」")
        if k in PLACEHOLDER_RULES or k in BODY_FORMAT_RULES or k in MINUTES_RENDER_TEMPLATE_PROMPT
    ]
    expect(not stale, "通用层不再强推单一缺省词（旧写法已清除）", f"残留={stale}")


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
    expect(not parse_document_char_budget(tpl).get("hi"), "段落说明里的全文标记不产生全文预算", f"{parse_document_char_budget(tpl)}")
    expect(any(
              b["hi"] == 400 and b.get("scope") == "paragraph"
              for b in parse_section_char_budgets(tpl)
          ), "同一栏的段落预算仍能识别", f"{parse_section_char_budgets(tpl)}")
    real = runtime_tpl(
        "# 乙\n\n<!-- requirement\n全文合计约200-300字，覆盖背景与结论\n-->\n\n# [摘要]\n[写点东西]\n"
    )
    expect(parse_document_char_budget(real).get("hi") == 300, "真·全文预算（标记贴着数字）仍被识别", f"{parse_document_char_budget(real)}")
    misread = [
        md.stem
        for md in sorted(_active_dir().glob("*.md"))
        if md.stem.lower() not in {"readme", "diff"}
        and parse_document_char_budget(runtime_tpl(md.read_text(encoding="utf-8"))).get("hi")
    ]
    expect(not misread, "模板目录里没有被误判的全文预算", f"误判={misread}")


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
    expect("单段概括，约 250–350 字" in interview and "单段不超过 300 字" not in interview, "采访记录：概况栏为单段 250–350", "")
    caps = [b for b in parse_section_char_budgets(interview) if b["title"] == "访谈概述"]
    expect(bool(caps) and caps[0]["scope"] == "paragraph" and caps[0]["hi"] == 350, "采访记录：概况栏解析出段落预算 250–350", f"{caps}")
    prog = (_active_dir() / "project_progress.md").read_text(encoding="utf-8")
    pcaps = [b for b in parse_section_char_budgets(prog) if b["title"] == "项目概况"]
    expect(bool(pcaps) and int(pcaps[0]["lo"] or 0) <= int(pcaps[0]["hi"]), "项目进度会：概况栏节级预算 lo ≤ hi", f"{pcaps}")

    long_para = "这是受访者的观点与结论。" * 40  # ≈440 汉字，超过 350×1.2
    doc = "# 采访记录\n\n# 访谈概述\n" + long_para + "\n"
    fixed, notes = split_overlong_paragraphs(doc, interview)
    parts = [p.strip() for p in fixed.split("# 访谈概述", 1)[1].split("\n\n") if p.strip()]
    expect(bool(notes) and len(parts) >= 2 and max(han(p) for p in parts) <= 350, "采访记录：440 字单段被拆（段落预算 350 兜单段）", f"段长={[han(p) for p in parts]} {notes}")

    # 节级预算的栏（无「单段/每段」字样）也要兜单段：超过整节上限即拆
    lecture = (_active_dir() / "special_lecture.md").read_text(encoding="utf-8")
    lcaps = [b for b in parse_section_char_budgets(lecture) if b["title"] == "讲座概况"]
    expect(bool(lcaps) and lcaps[0]["scope"] == "paragraph", "专题讲座：概况栏仍是段落预算（用于验证段落兜底）", f"{lcaps}")
    long2 = "这是讲座的主旨与结论。" * 45  # 450 汉字 > 400（节级上限）
    doc2 = "# 专题讲座\n\n# 讲座概况\n" + long2 + "\n"
    fixed2, notes2 = split_overlong_paragraphs(doc2, lecture)
    parts2 = [p.strip() for p in fixed2.split("# 讲座概况", 1)[1].split("\n\n") if p.strip()]
    expect(bool(notes2) and len(parts2) >= 2, "专题讲座：节级预算下 440 字单段也会被拆（节上限即单段上界）", f"段长={[han(p) for p in parts2]} {notes2}")

    # ② 父节预算继承：带 `## 子标题` 的栏目不能再让段落上限失效
    tpl_para_text = (
        "# 研讨速览\n\n"
        "## [研讨速记]\n"
        "[一段话描述该段，每段最多 250 字]\n\n"
        "## [全文摘要]\n"
        "[一段话（一段写完，约 250–400 字）交代主旨]\n"
    )
    gcaps = [b for b in parse_section_char_budgets(tpl_para_text) if b["title"] == "研讨速记"]
    expect(bool(gcaps) and gcaps[0]["hi"] == 250 and gcaps[0]["scope"] == "paragraph", "段落级预算 (200,250) 解析生效", f"{gcaps}")
    para_sub = "这是一段概览文字。" * 55  # ≈440 汉字，单段
    for label, doc in (
        ("无子标题", "# 研讨速览\n\n# 研讨速记\n" + para_sub + "\n"),
        ("带 ## 时间段", "# 研讨速览\n\n# 研讨速记\n## 08:00-12:30 现场检查\n" + para_sub + "\n"),
    ):
        fixed, notes = split_overlong_paragraphs(doc, tpl_para_text)
        seg_parts = [q for q in fixed.split("\n\n") if "概览文字" in q]
        expect(bool(notes) and len(seg_parts) >= 2
              and max(sum(1 for c in q if "一" <= c <= "鿿") for q in seg_parts) <= 260, f"带子标题栏目 440 字段按 250 字上限拆分（{label}）", f"段数={len(seg_parts)} {notes}")

    # ③ 声明只作用于本栏：同一文档里其它栏（全文摘要）仍按节级上限拆
    doc4 = (
        "# 研讨速览\n\n# 全文摘要\n" + para_sub
        + "\n\n# 研讨速记\n## 08:00-12:30 现场检查\n" + para_sub + "\n"
    )
    fixed4, notes4 = split_overlong_paragraphs(doc4, tpl_para_text)
    abs_part = fixed4.split("# 全文摘要", 1)[1].split("# 研讨速记", 1)[0]
    expect(any("全文摘要" in n for n in notes4)
          and len([q for q in abs_part.split("\n\n") if "概览文字" in q]) >= 2, "两栏各自按自己的上限拆（摘要节级 400 / 速记段落级 250）", f"{notes4}")

    # ④ 单句超长（句界拆不动）→ 仍必须报「超出段落字数上限」，不能静默
    from core.execution.gate import _overlong_issue

    gm = (_active_dir() / "general_minutes.md").read_text(encoding="utf-8")
    one = "这是一句没有任何句号的超长段落" + "持续延伸内容" * 80 + "。"
    doc3 = "# 通用纪要\n\n# 全文摘要\n" + one + "\n"
    over = _overlong_issue(gm, doc3) or ""
    expect("超出段落字数上限" in over and "全文摘要" in over, "通用纪要：摘要栏单句超长仍报超限（不再静默）", over[:80])

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
    expect("项目概况" in sec_names and "进度追踪" in sec_names and "后续计划" in sec_names, "H2 产物能正确切分各栏目（不吞进首栏）", f"{sec_names}")
    budget_err = _overlong_issue(prog_text, doc_h2)
    expect(budget_err is None, "H2 产物各栏目独立核算字数（首栏不误报超限）", f"{budget_err}")


def test_output_volume_and_hierarchy() -> None:
    """总量天花板 + 理解层限流 + 两级层级标准（治"太平、太碎、超原文"）。

    用户指出（2026-09-19）：① 纪要超原文；② 挖得太细太碎、耗时长；③ 层级太平难浏览。
    根因：理解层"宁多不漏"全量抽取 → 草稿"把细节写开" → 渲染"每一项写足"，
    装配规则还允许"与原文同量级 90%–110%"。
    """
    import pathlib

    from core.templates.length_budget import capped_budget

    expect(capped_budget(3500) == (1080, 2800), "天花板：原文 ×80% 与档位取小（3500 字原文 → 上限 2800）", f"{capped_budget(3500)}")
    expect(capped_budget(30000) == (2400, 8000), "天花板：30000 字原文仍受档位上限约束（8000）", f"{capped_budget(30000)}")
    bl = __import__("core.templates.length_budget", fromlist=["budget_line"]).budget_line(3500)
    expect("任何情况下不超过原文的 80%" in bl, "【篇幅预算】写明不超过原文 80%", bl[:120])
    expect("不扩写寒暄与过程铺陈" in bl, "【篇幅预算】下限口径收窄（补关键事实，不扩写寒暄与过程）", "")

    u = pathlib.Path("domains/meeting/meeting_core/prompts.py").read_text(encoding="utf-8")
    expect("去重提炼" in u and "同一事实多次提及只保留最全的一条" in u,
           "理解层：同一事实多次提及只保留最全的一条", "")

    br = pathlib.Path("core/templates/body_rules.py").read_text(encoding="utf-8")
    expect("并列事项按业务或大类分组" in br and "每条交代一个完整事项" in br,
           "层级标准：按业务分组，每条交代一个完整事项", "")
    mp = pathlib.Path("domains/meeting/tasks/minutes/prompts.py").read_text(encoding="utf-8")
    expect("回到会议原文补全关键参数、结论、责任归属" in mp, "草稿：回原文补全关键参数/结论/责任归属", "")
    expect("过程性讨论、发言顺序与寒暄不写" in mp, "草稿：过程性讨论与寒暄不写", "")
