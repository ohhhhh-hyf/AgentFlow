"""模板路由的零 LLM 守卫：占位识别（含方括号字面）、门禁方向、模板结构不变量。

用法::

    python -m tools.template_router._selftest      # 全绿退出码 0，有失败退出码 1

回归背景（2026-09，实测）：
- `_PLACEHOLDER_RE = \\[([^\\[\\]]+)\\]` 不认"方括号里还有方括号"，所以说明里写了字面
  `- [ ]`（markdown 复选语法）的那一行不再被当成占位说明，而退化成**固定文案**：
  拼装路径把说明原文当正文写出（家校沟通/法律咨询的最后一栏永远填不上），
  自由渲染路径门禁反过来要求它逐字出现——不抄就报「模板固定文字丢失」，抄了才放行。
- 本模块把修复钉成契约：行级优先识别、多对括号仍逐对、门禁方向反转、固定段方括号告警。
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from ._base import iter_placeholders, split_template_meta
from ._detect import parse_placeholder_template
from ._gate import scan_fixed_bracket_literals, validate_rendered_output
from ._placeholder import plan_placeholder_fill

PASS: list[str] = []
FAIL: list[str] = []

# 各模板"标量字段数"基线快照（按模板目录分别记；只允许变多，不允许变少）：
# 少了就意味着某条说明又被误判成固定文案（占位识别回退）。切到别的代次时按对应快照比；
# 没有快照的目录（如以后的 v4）退化为"每个模板至少 1 个字段"。
SCALAR_BASELINE_BY_DIR: dict[str, dict[str, int]] = {
    "template_v2": {
        "class_transcript": 4, "clinical_advisory": 4, "contract_vetting": 4,
        "conversation_transcript": 4, "court_transcript": 4, "debate_forum": 4,
        "decision_review": 4, "exchange_forum": 4, "general_minutes": 6,
        "government_bulletin": 3, "group_seminar": 4, "hiring_report": 3,
        "home_school_liaison": 4, "interview_debrief": 4, "interview_transcript": 3,
        "knowledge_memo": 3, "legal_advisory": 4, "media_briefing": 4,
        "media_qa_session": 4, "personal_memo": 4, "product_launch": 4,
        "project_progress": 4, "psychological_session": 3, "research_dialogue": 3,
        "retrospective_session": 4, "site_visit_tour": 4, "special_lecture": 4,
        "team_meeting": 3, "workshop_session": 4,
    },
    # v3 的结构优化改了几处栏位形态（general_minutes 由 6 个槽位改成 2 栏），故单独记一份。
    # court_transcript / hiring_report / project_progress 另有"表格栏说明"行（紧跟表格的
    # `[按下表逐行填写…]`）不计入字段——它们没有正文位，明细由表格承载（见 test_table_caption_*）。
    "template_v3": {
        "class_transcript": 4, "clinical_advisory": 4, "contract_vetting": 4,
        "conversation_transcript": 4, "court_transcript": 3, "debate_forum": 4,
        "decision_review": 4, "exchange_forum": 4, "general_minutes": 2,
        "government_bulletin": 3, "group_seminar": 4, "hiring_report": 2,
        "home_school_liaison": 4, "interview_debrief": 4, "interview_transcript": 3,
        "knowledge_memo": 3, "legal_advisory": 4, "media_briefing": 4,
        "media_qa_session": 4, "personal_memo": 4, "product_launch": 4,
        "project_progress": 2, "psychological_session": 3, "research_dialogue": 3,
        "retrospective_session": 4, "site_visit_tour": 4, "special_lecture": 4,
        "team_meeting": 3, "workshop_session": 4,
    },
}

# template_v2 里已知的"固定段含方括号字面"：personal_memo 的两行示例待办 `- [ ] …`
# 含字面 `[ ]`，被门禁当固定文案（template_v3 已修）。切到别的模板目录时这份白名单为空。
KNOWN_PENDING_BRACKET_LITERALS: set[str] = {"personal_memo"}


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(("PASS  " if ok else "FAIL  ") + name + (f" | {detail}" if detail else ""))


def _active_dir() -> Path:
    """当前生效模板目录（由 ``AGENTFLOW_TEMPLATE_DIR`` 决定，别写死 template_v2/v3）。"""
    from app.config import template_dir

    return Path(template_dir())


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
    from ._placeholder import _line_placeholders

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
    """填充 prompt 允许字段值内用下级标题分板块（A2 口径），只禁与栏目标题同级。

    背景：模板里「二级标题写成员/模块」「多层级结构」这类说明，原先被 prompt 的
    "不要写 Markdown 标题（# / ##）"一刀切挡住 → 拼装路径不产出小标题、自由渲染路径产出，
    同一模板两条路径样式漂移。改成"只禁同级 `#`、允许 `##`/`###`"后两边口径一致。
    """
    from ._base import _PLACEHOLDER_FILL_SYSTEM as prompt

    check("填充 prompt 允许栏内用下级标题（提到 `##` 分组的许可）",
          "允许" in prompt and "##" in prompt and "栏内自行分组" in prompt, "")
    check("填充 prompt 不再一刀切禁止字段值写标题",
          "不要写 Markdown 标题" not in prompt, "")
    check("仍保留「不要重复栏目标题」与「不要写同级标题」两条保护",
          "不要重复栏目标题" in prompt and "同级" in prompt, "")


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
        with caplog.at_level(logging.WARNING, logger="tools.template_router._gate"):
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

    # 「固定段含方括号字面」：白名单只对 template_v2 生效（personal_memo 那两行示例待办
    # 在 v3 已修）；切到别的模板目录时这份白名单按空处理，出现任何一条都判失败。
    pending = KNOWN_PENDING_BRACKET_LITERALS if tdir.name == "template_v2" else set()
    unknown = sorted(set(bracketed) - pending)
    check("当前模板目录里没有新增的「固定段含方括号字面」",
          not unknown,
          f"新增={unknown}；已知待应用={sorted(set(bracketed) & pending)}")

    # 未生效的另一代模板（缺省是 template_v3）也顺手体检一下：它在的话应当干净
    other = tdir.parent / ("template_v3" if tdir.name != "template_v3" else "template_v2")
    if other.is_dir() and other != tdir:
        dirty = [p.stem for p in sorted(other.glob("*.md")) if scan_fixed_bracket_literals(p.read_text(encoding="utf-8"))]
        other_pending = KNOWN_PENDING_BRACKET_LITERALS if other.name == "template_v2" else set()
        check(f"{other.name}（另一代模板）里没有新增的「固定段含方括号字面」",
              not (set(dirty) - other_pending),
              f"={dirty[:4]}；已知待应用={sorted(set(dirty) & other_pending)}")


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


def test_gate_flags_bare_heading() -> None:
    """空栏（光杆标题）必须被门禁判为硬伤。

    背景（2026-09，now.xlsx 实测 22 条里 2 条中招）：占位符拼装的栏目标题由程序按模板
    打印，模型漏给字段/留空时就产出「只有栏目标题、正文空着」的半截文档（观感像被截断）；
    自由渲染路径模型自己也会写光杆标题。父标题只带子标题不算空栏，「未提及」算有正文。
    """
    from tools.execution.hard_execution import empty_section_issues, gate_render_output

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
    """漏填兜底：字段缺失 → 点名缺栏重试；三轮仍缺 → None（不回半截文档，交 freeform）。"""
    import asyncio

    from ._placeholder import fill_placeholder_template

    class _FakeFillClient:
        def __init__(self, payloads: list[str]) -> None:
            self.payloads = list(payloads)
            self.calls = 0
            self.users: list[str] = []

        async def text(self, system: str, user: str, **_kw) -> str:
            self.calls += 1
            self.users.append(user)
            return self.payloads[min(self.calls - 1, len(self.payloads) - 1)]

    partial = '{"fields": {"1": "甲栏内容。", "2": "乙栏内容。"}, "tables": []}'
    full = '{"fields": {"1": "甲栏内容。", "2": "乙栏内容。", "3": "丙栏内容。"}, "tables": []}'

    c1 = _FakeFillClient([partial])
    out1 = asyncio.run(fill_placeholder_template(c1, "内容来源：甲乙丙。", FILL_TPL))
    check("字段缺失不放行半截文档（返回 None → 交自由渲染）", out1 is None, f"out={out1!r}")
    check("缺栏按上限重试 3 轮", c1.calls == 3, f"calls={c1.calls}")
    check("重试指令点名缺哪一栏",
          len(c1.users) > 1 and "字段3" in c1.users[1],
          f"{c1.users[1][:100] if len(c1.users) > 1 else ''!r}")

    c2 = _FakeFillClient([partial, full])
    out2 = asyncio.run(fill_placeholder_template(c2, "内容来源：甲乙丙。", FILL_TPL))
    check("重试补齐后按完整字段拼装",
          bool(out2) and "丙栏内容" in (out2 or ""), f"out={(out2 or '')[:60]!r}")
    check("补齐即停（不无谓多调一次）", c2.calls == 2, f"calls={c2.calls}")


def test_fill_prompt_requires_all_keys() -> None:
    """提示层：输出约定与字段清单都点明「键必须齐全」（缺键＝漏填）。"""
    from ._base import _PLACEHOLDER_FILL_SYSTEM as system
    from ._placeholder import build_placeholder_fill_user

    user = build_placeholder_fill_user("内容来源：略。", FILL_TPL)
    check("系统提示要求 fields 覆盖全部编号", "必须给出清单里的全部编号" in system, "")
    check("系统提示禁止省略键", "不要省略该键" in system, "")
    check("用户提示的字段清单标明必须给全编号",
          "fields 必须给出下列**全部**编号" in user, "")
    check("用户提示点明缺键＝漏填", "缺键＝漏填" in user, "")


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

    背景（2026-09，sample.xlsx 实测）：`[按下表逐行填写…]` 紧跟表格时被当成必填正文字段，
    模型把明细全写进表格后只能填「未提及」→ 产出「标题 + 未提及 + 九行表格」的自相矛盾形态
    （项目进度会的进度追踪/风险预警、面试报告的能力评估）；庭审记录则把诉辩表改写成散文。
    """
    from ._base import is_table_caption, table_caption_lines
    from ._placeholder import assemble_placeholder_output, plan_placeholder_fill

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


def test_shape_rules_in_prompts() -> None:
    """形态与写足口径必须同时落在装配 prompt 与自由渲染 prompt（两条路径一致）。

    背景（2026-09，now/before 22 对 + sample 24 条实测）：装配路径的
    「每条以 `**分类标签**：` 开头」压过了「并列事实用 `- ` 一条一行」，产出 91 处裸标签段
    （行20 连续 13 行清单写成段落）、12 处标题/栏目名与标签同名、33 行单行加粗 >3 处；
    「每条 20–80 字」的下限又成了目标值 → 40 个点平均 20 字、半句碎片单独成条
    （团队例会 `**参数修改**：✅ 已完成，修改了参数。`）。两条路径共用同一套规则后，
    同一模板不再因走哪条路径而漂移。
    """
    from tools.templates.template_prompt import PLACEHOLDER_RULES

    from ._base import _PLACEHOLDER_FILL_SYSTEM as fill_system
    from ._placeholder import build_placeholder_fill_user

    user = build_placeholder_fill_user("内容来源：略。", FILL_TPL)
    for label, text in (
        ("装配 system prompt", fill_system),
        ("装配 user 消息", user),
        ("自由渲染 PLACEHOLDER_RULES", PLACEHOLDER_RULES),
    ):
        for keys, tag in ((SHAPE_RULE_KEYS, "形态六条"), (FILL_RULE_KEYS, "写足/表格栏口径")):
            missing = [k for k in keys if k not in text]
            check(f"{label} 含{tag}", not missing, f"缺={missing}")
    stale = [k for k in ("两级结构", "每条以 `**分类标签**：` 开头") if k in fill_system]
    check("旧的「每条都套分类标签」口径已移除（它是裸标签段的成因）", not stale, f"仍含={stale}")
    check("旧的「每条 20–80 字」下限已上调", "每条 20–80 字" not in fill_system, "")


# 形态六条：分点优先 / 大类分组 / 禁止同名 / 段落上限 / 加粗封顶 / 未决口径（+ 语音识别纠错口径）
SHAPE_RULE_KEYS = (
    "分点优先",
    "算形态缺陷",
    "大类分组",
    "禁止同名重复",
    "段落上限",
    "加粗配额",
    "未决/待澄清栏口径",
    "猜测补全",
)
# 写足与表格栏口径（A–E 批）：每条 30–100 字 + 两项要素 / 不拆多条 / 状态标记边界 / 表格栏总述
FILL_RULE_KEYS = ("30–100 字", "至少两项要素", "同一句话不拆多条", "状态标记", "表格栏")


TEMPLATE_SHAPE_SNIPPETS = {
    "retrospective_session": "不要每条都补「责任人无，时间无」",
    "hiring_report": "本栏明细由下表承载",
    "hiring_report#维度": "岗位匹配度、问题解决能力、思维逻辑性、应变能力",
    "media_briefing": "一条一行 `- `",
    "site_visit_tour": "一个景点一行",
    "knowledge_memo": "不要再以同名",
    "clinical_advisory": "每条都是 `- ` 分点行",
    "home_school_liaison": "每一件事都要落进清单",
    "project_progress": "本栏明细由下表承载",
    "project_progress#后续": "从概况与原文提取下一步",
    "court_transcript": "本栏明细由下表承载",
    "team_meeting": "四要素",
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


def main() -> int:
    caplog_records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            caplog_records.append(record)

    handler = _Collect()
    logging.getLogger("tools.template_router._gate").addHandler(handler)
    logging.getLogger("tools.template_router._gate").setLevel(logging.WARNING)

    class _Cap:
        records = caplog_records

        def at_level(self, *a, **k):  # noqa: ANN002, ANN003
            return self

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *a):  # noqa: ANN002
            return False

    try:
        test_iter_placeholders()
        test_line_placeholders_filters_noise()
        test_parser_sees_field_not_text()
        test_prompt_allows_sub_headings()
        test_gate_direction_and_warning(_Cap())
        test_templates_regression()
        test_buggy_template_now_works()
        test_gate_flags_bare_heading()
        test_missing_field_guard()
        test_fill_prompt_requires_all_keys()
        test_table_caption_not_a_field()
        test_shape_rules_in_prompts()
        test_template_shape_instructions()
    finally:
        logging.getLogger("tools.template_router._gate").removeHandler(handler)

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项：" + "，".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
