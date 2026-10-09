"""tests/unit/core/templates/test_template_gate.py -- 模板渲染门禁、光杆标题与格式合规校验单元测试。"""
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

def test_gate_direction_and_warning(caplog) -> None:  # type: ignore[no-untyped-def]
    """门禁：写真实内容放行；回声说明原文报错；固定段方括号告警可被捕获。"""
    tpl = (
        "# [沟通概况]\n[一段话概括沟通双方与主题]\n\n"
        "# [共识与配合事项]\n[明确家校共识与分工，用 `- [ ]` 待办格式列出双方分工]\n"
    )
    good = "# 沟通概况\n家长会沟通。\n\n# 共识与配合事项\n- [ ] 家长：签字\n- [ ] 老师：反馈\n"
    echo = (
        "# 沟通概况\n家长会沟通。\n\n# 共识与配合事项\n"
        "[明确家校共识与分工，用 `- [ ]` 待办格式列出双方分工]\n"
    )
    errs_good = validate_rendered_output(good, tpl)
    errs_echo = validate_rendered_output(echo, tpl)
    check("写真实待办内容 → 放行（修复前报「模板固定文字丢失」）", not errs_good, f"{errs_good}")
    check("回声说明原文 → 报残留占位符（修复前被放行）",
          any("残留占位符" in e for e in errs_echo), f"{errs_echo}")

    # 反向：真正会退化成固定文案的两种形态必须被抓出来并告警
    # ① 括号没闭合（`[附件` 这类）② 括号内容不像占位说明（`[x]` / `[1,2]`）
    for label, odd in (
        ("未闭合括号", "# [标题]\n[占位一] 见 [附件\n"),
        ("不像占位符的括号", "# [标题]\n[占位一] 见 [x] 与 [1,2]\n"),
    ):
        hits = scan_fixed_bracket_literals(odd)
        check(f"固定段含方括号字面被扫出（{label}）", bool(hits), f"{hits[:1]}")
        caplog.records.clear()
        with caplog.at_level(logging.WARNING, logger="core.templates.router._gate"):
            validate_rendered_output("# 标题\n占位一 见 附件\n", odd)
        check(f"并打出 WARNING（{label}，不再静默逼出复述）",
              any("固定段含方括号字面" in r.getMessage() for r in caplog.records),
              f"{[r.getMessage()[:36] for r in caplog.records]}")

def test_templates_regression() -> None:
    """全量模板回归：字段数不低于基线（识别不许回退），且无"固定段含方括号"残留。"""
    tdir = _active_dir()
    md_files = sorted(p for p in tdir.glob("*.md") if p.stem.lower() not in {"readme", "diff"})
    check(f"模板目录 {tdir.name} 下有模板文件", bool(md_files), f"n={len(md_files)}")
    baseline = SCALAR_BASELINE_BY_DIR.get(tdir.name, {})
    lost: list[str] = []
    bracketed: list[str] = []
    tables_bad: list[str] = []
    for p in md_files:
        text = p.read_text(encoding="utf-8")
        fmt, _ = split_template_meta(text)
        plan = plan_placeholder_fill(fmt)
        base = baseline.get(p.stem, 1)  # 无快照的目录：只要求每个模板至少 1 个字段
        if len(plan["scalars"]) < base:
            lost.append(f"{p.stem}:{len(plan['scalars'])}<{base}")
        if scan_fixed_bracket_literals(fmt):
            bracketed.append(p.stem)
        n_tables = len(re.findall(r"^\|[\s:\-|]+\|\s*$", fmt, re.M))
        if n_tables != len(plan["row_templates"]):
            tables_bad.append(f"{p.stem}:表{n_tables}≠行模板{len(plan['row_templates'])}")
    check(f"{tdir.name} 里没有模板的占位识别回退（字段数 ≥ 基线）", not lost, f"{lost[:4]}")
    check("每张表都有占位数据行（表数 == 行模板数）", not tables_bad, f"{tables_bad[:4]}")

    unknown = sorted(set(bracketed))
    check("当前模板目录里没有新增的「固定段含方括号字面」",
          not unknown,
          f"新增={unknown}")

    chinese_brackets = [
        p.stem for p in md_files
        if any(ch in p.read_text(encoding="utf-8") for ch in ("【", "】", "（", "）"))
    ]
    check("template 模板全部采用半角英文括号 [] 与 ()", not chinese_brackets, f"含中文括号={chinese_brackets}")

def test_gate_flags_bare_heading() -> None:
    """空栏（光杆标题）必须被门禁判为硬伤。

    背景（2026-09，now.xlsx 实测 22 条里 2 条中招）：占位符拼装的栏目标题由程序按模板
    打印，模型漏给字段/留空时就产出「只有栏目标题、正文空着」的半截文档（观感像被截断）；
    自由渲染路径模型自己也会写光杆标题。父标题只带子标题不算空栏，「未提及」算有正文。
    """
    from core.execution.gate import empty_section_issues, gate_render_output

    tpl = (
        "# [沟通概况]\n[一段话概括沟通双方与主题]\n\n"
        "# [共识与配合事项]\n[明确家校共识与分工]\n"
    )
    bare = "# 沟通概况\n家长会沟通。\n\n# 共识与配合事项\n"
    ok_text = "# 沟通概况\n家长会沟通。\n\n# 共识与配合事项\n未提及\n"
    nested = "# 核心知识点\n## 光的直线传播\n- 光沿直线传播。\n"
    titled = "# 课堂记录\n# 课程概况\n本节课讲光学。\n# 课后任务\n写作业。\n"
    check("光杆标题被判空栏",
          empty_section_issues(bare, tpl) == ["「共识与配合事项」只有标题没有正文（空栏）"],
          f"{empty_section_issues(bare, tpl)}")
    check("父标题只带子标题不算空栏（正文在子节里）", empty_section_issues(nested) == [], "")
    check("缺省词「未提及」算有正文", empty_section_issues(ok_text, tpl) == [], "")
    check("文档标题（模板首行 `# 中文名`）没有正文不算空栏",
          empty_section_issues(titled, "# 课堂记录\n\n# [课程概况]\n[概括]\n") == [], "")
    gate = gate_render_output(tpl, bare)
    check("空栏进硬伤清单（gate_ok=False，触发 repair）",
          not gate["gate_ok"] and any("只有标题没有正文" in x for x in gate["hard_issues"]),
          f"hard={gate['hard_issues']}")
    check("填了缺省词的正文照常放行", gate_render_output(tpl, ok_text)["gate_ok"], "")

def test_missing_field_guard() -> None:
    """占位符填充防护：不支持流式客户端时立即安全降级为 None（不再死循环重试）。"""
    import asyncio
    from core.templates.router._placeholder import fill_placeholder_template

    class _SyncOnlyClient:
        async def text(self, *a, **k):
            return "{}"

    c = _SyncOnlyClient()
    out = asyncio.run(fill_placeholder_template(c, "内容来源：甲乙丙。", FILL_TPL))
    check("不支持 stream 的客户端安全降级为 None（不再死循环重试）", out is None, "")

def test_shape_rules_in_prompts() -> None:
    """形态与写足口径必须落在自由渲染 prompt 与共用形态规则。

    同一套规则由 BODY_FORMAT_RULES 单点维护，注入到自由渲染 PLACEHOLDER_RULES 等下游。
    """
    from core.templates.body_rules import BODY_FORMAT_RULES
    from core.templates.template_prompt import PLACEHOLDER_RULES
    from core.templates.router import route_template

    for label, text in (
        ("共用形态规则 BODY_FORMAT_RULES", BODY_FORMAT_RULES),
        ("自由渲染 PLACEHOLDER_RULES", PLACEHOLDER_RULES),
    ):
        for keys, tag in ((SHAPE_RULE_KEYS, "形态六条"), (FILL_RULE_KEYS, "写足/表格栏口径")):
            missing = [k for k in keys if k not in text]
            check(f"{label} 含{tag}", not missing, f"缺={missing}")
    stale = [k for k in ("两级结构", "每条以 `**分类标签**：` 开头") if k in BODY_FORMAT_RULES or k in PLACEHOLDER_RULES]
    check("旧的「每条都套分类标签」口径已移除（它是裸标签段的成因）", not stale, f"仍含={stale}")
    check("旧的「每条 20–80 字」下限已上调", "每条 20–80 字" not in BODY_FORMAT_RULES and "每条 20–80 字" not in PLACEHOLDER_RULES, "")

    # 通用层不绑定具体模板的栏目：栏目说明只来自【模板原文】与字段清单。
    # 回归背景：曾把项目进度会的「进度追踪/风险预警」写死在共用填充消息里，
    # 于是 30 个模板（含决策评审会、团队例会）都被要求写这两个不存在的栏目。
    _sys_p, user_p = route_template("内容来源：略。", FILL_TPL, "无模板系统提示", "模板基础提示")
    head = re.split(r"【模板写作要求】|【内容来源】|模板原文：", user_p)[0]
    titles: set[str] = set()
    for md in sorted(_active_dir().glob("*.md")):
        if md.stem.lower() in {"readme", "diff"}:
            continue
        text = md.read_text(encoding="utf-8")
        titles.update(
            m.group(1).strip()
            for m in re.finditer(
                r"^#{1,6}\s*\[([^\[\]]+)\]\s*$", text, re.MULTILINE
            )
            if m.group(1).strip()
        )
    leaked = sorted(t for t in titles if t in head)
    check("模板路由消息不写死具体模板的栏目名", not leaked, f"泄漏={leaked[:5]}")


# 形态六条：分组不并事实 / 大类分组 / 禁止同名 / 段落上限 / 按需加粗 / 未决口径（+ 语音识别纠错口径）
SHAPE_RULE_KEYS = (
    "分组不并事实",
    "算形态缺陷",
    "大类分组",
    "禁止同名重复",
    "段落上限",
    "按需加粗",
    "未决/待澄清栏口径",
    "猜测补全",
)
# 写足与表格栏口径（A–E 批）：完整交代 + 模板决定条长 / 不拆多条 / 状态标记边界 / 表格唯一承载
# + 2026-09 第二批五条：超 100 字必须拆 / 同标签最多 1 次 / 有素材不得未提及+不写说明句 /
#   按需加粗（不设每栏最低数量）/ `## 名称` 之下必须 `- `
# + 2026-09 第三批两条（now.xlsx 总结复盘会：条目 21–36 字且只剩结论）：
#   条目 = 一个事项的完整交代 / 禁止结论式孤条
FILL_RULE_KEYS = (
    "条目长度以模板显式要求为准",
    "简单且完整的行动项可以短于 30 字",
    "完整交代",
    "结论式孤条",
    "同一句话不拆多条",
    "状态标记",
    "表格栏",
    "不可拆事实可以超过 120 字",
    "最多出现 1 次",
    "禁止写「原文未提及…」这类缺失说明句",
    "不设每栏最低数量",
    "成员称呼",
    "小节之下必须分条列出",
)


TEMPLATE_SHAPE_SNIPPETS = {
    "retrospective_session": "- **改进事项名**：",
    "hiring_report": "本栏明细由下表承载",
    "hiring_report#维度": "不自行发明能力模型",
    "media_briefing": "一条讲透一个主题",
    "site_visit_tour": "都要汇总到这里",
    "knowledge_memo": "不要再以同名",
    "clinical_advisory": "每条都是 `- ` 分点行",
    "home_school_liaison": "每一件事都要落进清单",
    "project_progress": "本栏明细由下表承载",
    "project_progress#后续": "按事项分点写",
    "court_transcript": "本栏明细由下表承载",
    "team_meeting": "四要素",
    # 低结构化/闲聊型场景的稳定性口径：没有结论也要写明，不留空洞栏目
    "admission_briefing": "原文点到的事实一律不得丢",
    "conversation_transcript": "未形成明确结论",
    "group_seminar": "没有统一意见时写本场达成的倾向性认识与主要分歧点",
    # 场景适配（2026-09 第二批）：知识点必须 `- `、建议必须汇总、摘要单段上限、空栏目正当写法
    "class_transcript": "不得写成连续段落",
    "general_minutes": "一段写完，约 250–400 字",
    "personal_memo": "不要写「未提及」",
    "psychological_session": "不强行总结结论",
}

def test_template_shape_instructions() -> None:
    """模板层的形态/表格栏/覆盖口径不许被回退（防「责任人无，时间无」「未提及 + 表格」复发）。"""
    tdir = _active_dir()
    missing: list[str] = []
    for key, snippet in TEMPLATE_SHAPE_SNIPPETS.items():
        tid = key.split("#", 1)[0]
        p = tdir / f"{tid}.md"
        if not p.is_file():
            missing.append(f"{tid}:缺文件")
            continue
        if snippet not in p.read_text(encoding="utf-8"):
            missing.append(f"{tid}:缺「{snippet}」")
    check(f"{tdir.name} 的形态/表格栏/覆盖口径到位", not missing, f"{missing}")

def test_advisory_checks() -> None:
    """咨询级检查：超长条/超长段/缺失说明句被抓出来，且不影响 gate_ok（不触发返工）。"""
    from core.execution.gate import (
        advisory_issues,
        gate_render_output,
        overlong_items,
    )

    long_item = "- **学科领军人物**：" + "吕建新教授" * 45 + "。"
    long_para = "# 课程概况\n" + "本节课讲解光学复习要点。" * 50 + "\n"
    meta = "# 讲座概况\n本次讲座由肖楠总主讲，机构信息原文未提及。\n"
    tpl = "# [课程概况]\n[一段话概括]\n\n# [核心观点]\n[写要点]\n"
    hits_item = advisory_issues(long_item)
    hits_para = advisory_issues(long_para)
    hits_meta = advisory_issues(meta)
    check("超长条（>200 字的一条）被抓出", any("一条" in h for h in hits_item), f"{hits_item}")
    check("超长段（>450 字的段落）被抓出", any("一段" in h for h in hits_para), f"{hits_para}")
    check("正常概况段（231–400 字，规格允许每段 400 字以内）不误报",
          advisory_issues("# 概况\n" + "本节课讲解光学复习要点。" * 30 + "\n") == [], "")
    numbered_list = "# 政策要点\n" + "\n".join(f"{i}. 扎实推进第{i}项工作落实，深化改革创新发展。" for i in range(1, 25)) + "\n"
    check("数字编号列表不累加判定为超长段", advisory_issues(numbered_list) == [], f"{advisory_issues(numbered_list)}")
    check("缺失说明句「原文未提及…」被抓出",
          any("缺失说明句" in h for h in hits_meta), f"{hits_meta}")
    gate = gate_render_output(tpl, long_para)
    check("咨询级问题不影响 gate_ok（只记录、不触发返工）",
          bool(gate.get("gate_ok")) and list(gate.get("advisory_issues") or []),
          f"ok={gate.get('gate_ok')} advisory={gate.get('advisory_issues')}")
    check("正常文本不产生咨询级告警", advisory_issues("# 甲\n- **乙**：正常一条。\n") == [], "")
    check("超长条判据单点函数：与 advisory 报的逐字相同（逐栏填充共用同一实现）",
          overlong_items(long_item) == [h for h in hits_item if "一条" in h],
          f"{overlong_items(long_item)}")
    check("超长条判据：短条不误报、条数上限生效",
          overlong_items("- **乙**：正常一条。") == []
          and len(overlong_items("\n".join([long_item] * 3), limit=2)) == 2,
          "")

def test_general_minutes_speedread() -> None:
    """通用纪要：精简为摘要与要点双栏结构（移除冗余的分段速览）。"""
    from core.templates.router._base import (
        split_template_meta,
        wrap_template_requirement,
    )
    from core.templates.router._placeholder import plan_placeholder_fill
    from core.templates.template_eval import parse_section_char_budgets

    raw = (_active_dir() / "general_minutes.md").read_text(encoding="utf-8")
    body, req = split_template_meta(raw)
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines = lines[i + 1 :]
            break
    tpl = wrap_template_requirement("\n".join(lines).strip(), req)

    plan = plan_placeholder_fill(tpl)
    hints = [str(s.get("hint") or "") for s in plan["scalars"]]
    check("通用纪要：标准三栏结构（全文摘要、要点梳理、结论与决定）", len(plan["scalars"]) == 3, f"字段数={len(plan['scalars'])}")
    check("通用纪要：已无「分段速览」冗余栏",
          not any("分段速览" in h for h in hints), f"{hints}")
    check("通用纪要：包含独立的「结论与决定」栏",
          any("结论与决定" in h or "拍板" in h for h in hints), f"{hints}")
    # 摘要定位：立足全局宏观概览与战略定调，细节与论据下沉至 [要点梳理]
    abstract = hints[0]
    check("通用纪要：摘要立足宏观概览与全局决议，细节下沉要点梳理",
          "全面概述会议背景" in abstract and "主要参会方" in abstract
          and "拍板定夺的最关键决议" in abstract and "具体研讨细节" in abstract, abstract[:90])
    check("通用纪要：旧数字配额口径已彻底清除（不再要求每板块数字或限制几条数字）",
          "至少带 1–3 个" not in abstract and "一条数字都没有＝不合格" not in abstract
          and "选 3–5 个" not in abstract and "禁止逐板块展开数字" not in abstract, "")
    budgets = parse_section_char_budgets(tpl)
    check("通用纪要：摘要为一段 250–400（节级）",
          any(b["title"] == "全文摘要" and b["lo"] == 250 and b["hi"] == 400 and b["scope"] == "section" for b in budgets),
          f"{budgets}")
    from core.execution.gate import split_overlong_paragraphs

    long_seg = "这是一段要点梳理文字。" * 55  # ≈440 汉字
    fixed_seg, seg_notes = split_overlong_paragraphs(
        "# 通用纪要\n\n# [全文摘要]\n" + long_seg + "\n", tpl
    )
    seg_parts = [q for q in fixed_seg.split("\n\n") if "要点梳理文字" in q]
    check("通用纪要：超长段被程序按句界拆分（400 字节级上限生效）",
          bool(seg_notes) and len(seg_parts) >= 2,
          f"段数={len(seg_parts)} {seg_notes}")
    leftover = [
        p.stem
        for p in _active_dir().glob("*.md")
        if "单段不超过约 200 字" in p.read_text(encoding="utf-8")
    ]
    check("模板目录不再有「单段不超过约 200 字」", not leftover, f"残留={leftover}")

def test_qa_speaker_labels() -> None:
    """问答栏：能对上人就用「称呼：」（姓名→角色），对不上才退回「问/答」，且不许双重标注。

    回归背景（2026-09，新闻发布实测）：模板强制写成「**问**：…」，标签不带身份 → 模型把身份塞进内容，
    出现「**问**：主持人提问，中国是否继续相信联合国…」这类双重标注（全批 3 处）。
    """
    import re as _re

    qa_templates = {
        "media_briefing": "Q&A环节",
        "media_qa_session": "核心提问与回应",
        "admission_briefing": "Q&A 环节",
        "special_lecture": "Q&A 环节",
    }
    missing: list[str] = []
    old_mandate: list[str] = []
    for stem in qa_templates:
        text = (_active_dir() / f"{stem}.md").read_text(encoding="utf-8")
        if "两方都对应不上人时才写成" not in text:
            missing.append(stem)
        if _re.search(r"[，：]写成「\*\*问\*\*：…」换行", text):  # 旧强制句式；新文是「才写成…」
            old_mandate.append(stem)
    check("4 个问答模板都写清「称呼优先、问/答兜底」", not missing, f"缺={missing}")
    check("旧的「一律写成 问/答」口径已清除", not old_mandate, f"残留={old_mandate}")
    check("问答模板都禁止双重标注（「xx提问」式说明）",
          all("这类重复说明" in (_active_dir() / f"{s}.md").read_text(encoding="utf-8")
              for s in qa_templates), "")
    no_bold = [
        s for s in qa_templates
        if "每轮称呼都加粗" not in (_active_dir() / f"{s}.md").read_text(encoding="utf-8")
    ]
    check("问答模板都要求称呼行加粗（与旧 **问**/**答** 形式一致）",
          not no_bold, f"缺={no_bold}")

    from core.templates.body_rules import BODY_FORMAT_RULES

    check("共用形态规则为对话称呼开了加粗例外",
          "问答/对话的称呼行按模板要求每轮加粗" in BODY_FORMAT_RULES, "")

def test_no_test_corpus_leak() -> None:
    """模板 md 不许夹带测试语料的实体/内容作示例（软引导会让模型照着写）。

    回归背景（2026-09）：为修"栏目薄"临时写进模板的例子把测试数据带了进去——
    「延伸：民谣吉他与留胡子的设想」「`主持人：…` 换行 `王毅：…`」「抽奖与红包」「如 `00:14-00:50 会议概述`」。
    这与设计原则相悖（不夹带针对特定测试数据的示例或软引导），且会让输出照着例子长。
    """
    blocked = [
        "卢萨卡", "蒙泽", "某皮卡", "玉米面", "业委会", "物业费", "哥斯拉", "红楼梦", "三国演义",
        "阿富汗", "王毅", "慕安会", "慕尼黑", "手机图库", "夏令营", "民谣吉他", "留胡子",
        "南京照相馆", "电子科技大学", "抽奖", "红包", "00:14", "会议概述", "纯净永无止境", "诚意满满",
    ]
    leaked = []
    for md in sorted(_active_dir().glob("*.md")):
        if md.stem.lower() in {"readme", "diff"}:
            continue
        text = md.read_text(encoding="utf-8")
        hit = [w for w in blocked if w in text]
        if hit:
            leaked.append((md.stem, hit))
    check("模板 md 不夹带测试语料实体/内容", not leaked, f"命中={leaked}")

def test_debate_side_attribution_and_fabrication() -> None:
    """辩论会立场/环节归属 + 四类模板的"不得补写原文没有的行动与角色"（2026-09-20）。

    回归背景（score_now.xlsx now_25 辩论会：准确性 2.5，全库唯一低于 3 分）：
    ① 1.2×3 —— 把反方对正方的攻击写成正方主张、把正方结辩观点写成反方、把主持人宣布的环节结果
    当成某方立场；② 1.1×2 —— 捏造反方结辩内容与评委结论。
    另有 now_22（小组讨论 1.1×9）：参会人员、主持人、下一步分工全是原文没有的。
    """
    d = _active_dir()
    deb = (d / "debate_forum.md").read_text(encoding="utf-8")
    check("辩论 requirement：立场归属以原文为准 + 不得凭论点推断阵营",
          "**立场归属以原文为准**" in deb and "不得凭论点内容推断阵营" in deb, "")
    check("辩论：主持人的环节结果属环节信息，不得写成某方立场",
          "主持人的环节结果与规则信息（环节胜负、获得小结时间等）属环节信息" in deb
          and "不得写成某一方的立场或主张" in deb, "")
    check("辩论：各栏只还原本环节（不搬其它环节内容）",
          "各栏只还原本环节原文出现的原话与判断" in deb
          and "不得把其它环节的论点搬进结辩或点评" in deb, "")
    check("辩论 [辩论内容概述]：提到某方立场只写原文明确归属该方的表述",
          "**提到某一方立场时只写原文明确归属该方的表述**" in deb
          and "分不清就写「一方」或只写议题" in deb, "")

    fab = (
        ("小组讨论", "group_seminar.md", (
            ("**原文没说参会成员就不写**", "参会成员只在原文明说时写"),
            ("**只有原文说出具体事项与责任方或时间点的才算**", "后续分工必须有具体事项"),
            ("**只写原文说出的产出与一致/分歧", "共识栏不得补写安排"),
        )),
        ("工作研讨会", "workshop_session.md", (
            ("**原文没说参与方就不写**", "参与方只在原文明说时写"),
            ("**只写原文说出具体事项与责任方或跟进人的内容**", "后续探索必须有具体事项"),
        )),
        ("团队例会", "team_meeting.md", (
            ("**原文没说参会人员就不写**", "参会人员只在原文明说时写"),
            ("不得补写原文没有的「下一步」或「后续安排」", "决定与待办不得补写动作"),
        )),
        ("课堂记录", "class_transcript.md", (
            ("**学生的话与教师的点评必须取自原文明确说出的内容**",
             "互动栏不得改写教师讲解"),
        )),
    )
    for name, fn, rules in fab:
        text = (d / fn).read_text(encoding="utf-8")
        for anchor, what in rules:
            check(f"{name}：{what}", anchor in text, "")

def test_reject_hardening() -> None:
    """无理由的 reject 不当否决 + 摘录未覆盖 ≠ 捏造（治"误判→返工→无理由 reject→降级"）。

    回归背景（2026-09-18 11:39 实测）：草稿里的《种地吧》细节（十个男孩/农业公司/小月季）
    都在原文里，但审核者拿到的"按草稿事实点摘录"没覆盖那段 → 判"无原文依据" → revise →
    返工没改（草稿 579→584 字）→ 二轮 reject（feedback 按契约为空，日志 findings=null）→
    整线降级成拼接文本，而那段降级文本里恰好又包含这些"无依据"的细节。
    """
    from core.schema.validation import soften_unreasoned_reject

    # ① 有理由的 reject 原样保留
    reasoned = {
        "decision": "reject",
        "feedback": [],
        "facts_check": {"status": "fail", "findings": ["把「建议下月再议」写成了已决策"]},
        "consistency_check": {"status": "pass", "findings": []},
    }
    kept, note = soften_unreasoned_reject(dict(reasoned))
    check("reject 带具体理由 → 原样生效", kept["decision"] == "reject" and note is None, f"{note}")

    # ② 无理由的 reject → 降为 approve 并留痕
    bare = {
        "decision": "reject",
        "feedback": [],
        "facts_check": {"status": "fail", "findings": []},
        "consistency_check": {"status": "pass", "findings": []},
    }
    soft, note = soften_unreasoned_reject(dict(bare))
    check("无理由 reject → 降为 approve", soft["decision"] == "approve" and soft.get("reject_downgraded"), f"{soft}")
    check("降级后 feedback 置空（approve 语义要求）", soft["feedback"] == [], f"{soft['feedback']}")
    check("降级留痕有说明", bool(note) and "按 approve" in str(note), f"{note}")

    # ③ approve / revise 不受影响
    for decision in ("approve", "revise"):
        payload = {"decision": decision, "feedback": ["x"] if decision == "revise" else []}
        out, note = soften_unreasoned_reject(dict(payload))
        check(f"{decision} 不被本兜底改动", out["decision"] == decision and note is None, f"{out}")

    # ④ 文案：审核侧必须被明确告知"未覆盖 ≠ 捏造"与"reject 要写理由"
    from domains.meeting.tasks.minutes import prompts as minutes_prompts

    domain_prompt = minutes_prompts.MINUTES_SUPERVISOR_DOMAIN_PROMPT
    check("审核领域提示词：无理由 reject 会被按 approve 处理",
          "没写理由的 reject 会被程序按 approve 处理" in domain_prompt, "")
    check("审核领域提示词：核对不了按未覆盖处理（不是捏造）",
          "写「未能核对：X」并 approve" in domain_prompt, "")
    engine_src = (
        __import__("pathlib").Path("core/graph/nodes.py").read_text(encoding="utf-8")
    )
    check("审核证据包：明文写「摘录未覆盖 ≠ 无依据」",
          "摘录未覆盖 ≠ 无依据" in engine_src and "不得据此 revise 或 reject" in engine_src, "")
    check("审核节点：软化的 reject 已接入（approve 后不再走 fallback）",
          "soften_unreasoned_reject(payload)" in engine_src
          and "reject_downgraded" in engine_src, "")
    schema_src = (
        __import__("pathlib").Path("core/schema/contracts.py").read_text(encoding="utf-8")
    )
    check("审核契约说明：reject 需写明具体理由",
          "该检查项的 findings 要写明具体理由" in schema_src, "")

def test_qa_precision_rules() -> None:
    """问答栏只收真问答（治"陈述句当提问"）：判据写在共用形态规则里，模板侧只留专用口径。

    回归背景（2026-09 now.xlsx）：新闻发布两场对比——提问形式清晰的那场 7 条问句全部合格；
    提问是间接表述的那场 3 条全部写成「主持人周琦提问，…？」这种引导式转述（既不是原文问句、
    也不是纯疑问句），答话还有 230 字的讲稿式搬运。五个问答模板此前都没有"什么算问答"的判据。
    """
    from core.templates.router._placeholder import plan_placeholder_fill
    from core.templates.body_rules import BODY_FORMAT_RULES

    for need in (
        "问答栏只收真问答",
        "自问自答与讲解式设问",
        "不得写成「XX提问，…？」式引导转述",
        "答话只写回应要点",
        "模板未指定上限时，答话超过约 300 字压到 300 字以内",
        "答话只写回应要点并保持单段，不拆段、不使用列表",
        "压缩只删例子与铺垫",
        "问答栏：若模板声明「整栏隐去/无问答直接省略」",
    ):
        check(f"共用形态规则含问答精度口径：{need}", need in BODY_FORMAT_RULES, "")
    check("段落上限规则为问答轮次开了例外（再长也不拆段、长答话按要点压缩）",
          "问答/对话的一轮" in BODY_FORMAT_RULES and "再长也不拆段" in BODY_FORMAT_RULES
          and "长答话按要点压缩" in BODY_FORMAT_RULES, "")

    qa_templates = ("media_briefing", "media_qa_session", "admission_briefing", "special_lecture")
    retired = ("覆盖所有重要提问", "答话可归并但不得改口径", "内容相似的合并成一条")
    from core.templates.template_eval import parse_section_char_budgets

    for stem in qa_templates:
        text = (_active_dir() / f"{stem}.md").read_text(encoding="utf-8")
        check(f"{stem}：问答栏声明缺省词（空栏不成硬伤）", "未提及" in text, "")
        check(f"{stem}：已删掉与共用层重复的旧口径",
              not any(r in text for r in retired),
              f"残留={[r for r in retired if r in text]}")
        plan = plan_placeholder_fill(text)
        qa = [s for s in plan["scalars"] if "独立成段" in (s.get("hint") or "")]
        check(f"{stem}：问答栏 missing=True（留空自动补「未提及」）",
              bool(qa) and qa[0].get("missing") is True,
              f"{[s.get('missing') for s in qa]}")
        # 问答长度口径：各模板保留可解析的「每段上限」提示（media_briefing 于 2026-09-22 有意收紧到 350）
        para = [b for b in parse_section_char_budgets(text) if b.get("scope") == "paragraph"]
        expect_hi = 350 if stem == "media_briefing" else 400
        check(f"{stem}：问答栏保留可解析的长度口径（{expect_hi}/段，作提示）",
              any(int(b["hi"]) == expect_hi for b in para), f"{para}")
        check(f"{stem}：问答栏写明答话可压缩、仍按单段连着写（不拆段）",
              "答话可压缩、不必逐句照抄" in text and "仍**单段**连着写" in text
              and "答话超过约 400 字必须分点" not in text, "")

    # 一问一答各占一段：称呼行（对话轮次）不参与段落拆分，普通散文段照旧会被拆
    from core.execution.gate import split_overlong_paragraphs

    tpl = (_active_dir() / "media_qa_session.md").read_text(encoding="utf-8")
    long_ans = "这是一段很长的答话。" * 80
    han = lambda p: len([c for c in p if "\u4e00" <= c <= "\u9fff"])
    doc = "# 媒体问答\n\n# 核心提问与回应\n**1. 记者**：这次政策的核心是什么？\n**答**：" + long_ans + "\n"
    fixed, notes = split_overlong_paragraphs(doc, tpl)
    check("问答栏超长答话保持一整段（不再被拆段/换段、文字未改）",
          not notes and fixed.replace("\n", "") == doc.replace("\n", "")
          and max((han(ln) for ln in fixed.splitlines() if ln.strip()), default=0) > 400,
          f"{notes} 最长行={max((han(ln) for ln in fixed.splitlines() if ln.strip()), default=0)}")
    brief_tpl = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    plain = "# 新闻发布\n\n# 发布会概况\n" + ("这是一段很长的概况散文。" * 40) + "\n"
    check("普通散文段仍按句界拆分（网没坏）",
          bool(split_overlong_paragraphs(plain, brief_tpl)[1]), "")
    bullet = "# 媒体问答\n\n# 核心提问与回应\n- **要点**：" + long_ans + "\n"
    check("`- ` 条目行仍不受段落上限管辖（交给条目规则）",
          not split_overlong_paragraphs(bullet, tpl)[1], "")

def test_general_minutes_gate_and_minutes_styles_html() -> None:
    """验证通用纪要粗体决策标签不被门禁误判为占位符，且 minutes_styles 生成有效 HTML。"""
    from core.templates.router._gate import validate_rendered_output
    from domains.meeting.hooks import HOOKS
    from pathlib import Path

    tpl_path = Path(__file__).resolve().parents[4] / "resources" / "templates" / "general_minutes.md"
    tpl = tpl_path.read_text(encoding="utf-8")

    good_text = (
        "# 通用纪要\n\n"
        "## 全文摘要\n本次会议为小区物业招标答疑及评标会。\n\n"
        "## 要点梳理\n1. **[改造计划与时间]**\n   > 富家物业承诺一年内完成一系列改造项目。(富家物业)\n\n"
        "## 结论与决定\n1. **[中标候选人]选定深圳市资平物业发展有限公司为中标候选人**（评标委员会）\n   > 依据：评标打分结果。\n"
    )
    errs_good = validate_rendered_output(good_text, tpl)
    check("通用纪要决策项加粗标签放行（不误判为残留占位符）", not errs_good, f"{errs_good}")

    bad_text = (
        "# 通用纪要\n\n"
        "## 全文摘要\n本次会议为小区物业招标答疑及评标会。\n\n"
        "## 要点梳理\n1. **[此处填写具体业务议题]**\n   > 具体事实。\n"
    )
    errs_bad = validate_rendered_output(bad_text, tpl)
    check("通用纪要真实指令提示词占位符正确拦截", any("此处填写" in x for x in errs_bad), f"{errs_bad}")

    styles_html = HOOKS.html_for("minutes_styles", "测试多样式纪要", "# 测试多样式纪要\n\n正文内容", {})
    check("minutes_styles 任务线生成有效 HTML", bool(styles_html and "<!doctype html>" in styles_html), f"{bool(styles_html)}")

