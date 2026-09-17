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
    # v3 的结构优化改了几处栏位形态（general_minutes 由 6 个槽位改成 2 栏，2026-09 又补「分段速览」成 3 栏），故单独记一份。
    # court_transcript / hiring_report / project_progress 另有"表格栏说明"行（紧跟表格的
    # `[按下表逐行填写…]`）不计入字段——它们没有正文位，明细由表格承载（见 test_table_caption_*）。
    "template_v3": {
        "class_transcript": 4, "clinical_advisory": 4, "contract_vetting": 4,
        "conversation_transcript": 4, "court_transcript": 3, "debate_forum": 4,
        "decision_review": 4, "exchange_forum": 4, "general_minutes": 3,
        "government_bulletin": 3, "group_seminar": 4, "hiring_report": 2,
        "home_school_liaison": 4, "interview_debrief": 4, "interview_transcript": 3,
        "knowledge_memo": 3, "legal_advisory": 4, "media_briefing": 4,
        "media_qa_session": 4, "personal_memo": 4, "product_launch": 4,
        "admission_briefing": 5,
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

    背景（2026-09，now.xlsx 实测）：`[按下表逐行填写…]` 紧跟表格时被当成必填正文字段，
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

    # 通用层不绑定具体模板的栏目：栏目说明只来自【模板原文】与字段清单。
    # 回归背景：曾把项目进度会的「进度追踪/风险预警」写死在共用填充消息里，
    # 于是 30 个模板（含决策评审会、团队例会）都被要求写这两个不存在的栏目。
    head = re.split(r"【模板写作要求】|【内容来源】", user)[0]
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
    check("装配 user 消息不写死具体模板的栏目名", not leaked, f"泄漏={leaked[:5]}")


# 形态六条：分点优先 / 大类分组 / 禁止同名 / 段落上限 / 加粗封顶 / 未决口径（+ 语音识别纠错口径）
SHAPE_RULE_KEYS = (
    "分点优先",
    "算形态缺陷",
    "大类分组",
    "禁止同名重复",
    "段落上限",
    "加粗两头都要管",
    "未决/待澄清栏口径",
    "猜测补全",
)
# 写足与表格栏口径（A–E 批）：每条 30–100 字 + 两项要素 / 不拆多条 / 状态标记边界 / 表格栏总述
# + 2026-09 第二批五条：超 100 字必须拆 / 同标签最多 1 次 / 有素材不得未提及+不写说明句 /
#   加粗两头管住（每栏至少 1–2 处）/ `## 名称` 之下必须 `- `
# + 2026-09 第三批两条（now.xlsx 总结复盘会：条目 21–36 字且只剩结论）：
#   条目 = 一个事项的完整交代 / 禁止结论式孤条
FILL_RULE_KEYS = (
    "30–100 字",
    "至少两项要素",
    "完整交代",
    "结论式孤条",
    "同一句话不拆多条",
    "状态标记",
    "表格栏",
    "超过 100 字必须拆",
    "最多出现 1 次",
    "禁止写「原文未提及…」这类缺失说明句",
    "每栏至少 1–2 处加粗",
    "`## 名称` 小节之下**必须** `- ` 一条一行",
)


TEMPLATE_SHAPE_SNIPPETS = {
    "retrospective_session": "不要每条都补「责任人无，时间无」",
    "hiring_report": "本栏明细由下表承载",
    "hiring_report#维度": "岗位匹配度、问题解决能力、思维逻辑性、应变能力",
    "media_briefing": "一条一行 `- `",
    "site_visit_tour": "都要汇总到这里",
    "knowledge_memo": "不要再以同名",
    "clinical_advisory": "每条都是 `- ` 分点行",
    "home_school_liaison": "每一件事都要落进清单",
    "project_progress": "本栏明细由下表承载",
    "project_progress#后续": "从概况与原文提取下一步",
    "court_transcript": "本栏明细由下表承载",
    "team_meeting": "四要素",
    # 低结构化/闲聊型场景的稳定性口径：没有结论也要写明，不留空洞栏目
    "admission_briefing": "原文点到的事实一律不得丢",
    "conversation_transcript": "未形成明确结论",
    "group_seminar": "没有统一意见时写本场达成的倾向性认识与主要分歧点",
    # 场景适配（2026-09 第二批）：知识点必须 `- `、建议必须汇总、摘要单段上限、空栏目正当写法
    "class_transcript": "不得写成连续段落",
    "general_minutes": "每段不超过 400 字",
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
    from tools.execution.hard_execution import advisory_issues, gate_render_output

    long_item = "- **学科领军人物**：" + "吕建新教授" * 45 + "。"
    long_para = "# 课程概况\n" + "本节课讲解光学复习要点。" * 35 + "\n"
    meta = "# 讲座概况\n本次讲座由肖楠总主讲，机构信息原文未提及。\n"
    tpl = "# [课程概况]\n[一段话概括]\n\n# [核心观点]\n[写要点]\n"
    hits_item = advisory_issues(long_item)
    hits_para = advisory_issues(long_para)
    hits_meta = advisory_issues(meta)
    check("超长条（>200 字的一条）被抓出", any("一条" in h for h in hits_item), f"{hits_item}")
    check("超长段（>320 字的段落）被抓出", any("一段" in h for h in hits_para), f"{hits_para}")
    check("正常概况段（231–275 字，规格允许每段 400 字以内）不误报",
          advisory_issues("# 概况\n" + "本节课讲解光学复习要点。" * 20 + "\n") == [], "")
    check("缺失说明句「原文未提及…」被抓出",
          any("缺失说明句" in h for h in hits_meta), f"{hits_meta}")
    gate = gate_render_output(tpl, long_para)
    check("咨询级问题不影响 gate_ok（只记录、不触发返工）",
          bool(gate.get("gate_ok")) and list(gate.get("advisory_issues") or []),
          f"ok={gate.get('gate_ok')} advisory={gate.get('advisory_issues')}")
    check("正常文本不产生咨询级告警", advisory_issues("# 甲\n- **乙**：正常一条。\n") == [], "")


def test_supervisor_unavailable_flow() -> None:
    """"审核不可用"整链路：节点返回保守 approve + 不 degraded；路由走 __end__（不再降级）。

    旧行为：审核调用失败 → reject_review + degraded → route 走 fallback → 用户拿到
    确定性拼装文本（低结构化闲聊型输入实测踩中）。新行为：保守放行 + 质量警告。
    """
    import asyncio

    from tools.core.domain_engine import DomainNodes

    class _Boom:
        async def review(self, context: str):  # noqa: ANN001
            raise RuntimeError("supervisor 输出无法满足结构契约：字段不一致：缺失=['feedback']")

    class _Stub(DomainNodes):
        MAX_REVISIONS = 1
        _task_lines = {"minutes": {
            "supervisor_attr": "sup",
            "reject_review": {
                "decision": "reject",
                "feedback": [],
                "facts_check": {"status": "fail", "findings": ["内容空洞"]},
                "perspective_check": {"status": "pass", "findings": []},
                "consistency_check": {"status": "fail", "findings": ["口径不一致"]},
            },
        }}
        _line_cn_names = {"minutes": "纪要"}

        def __init__(self) -> None:
            self.sup = _Boom()

        def _supervisor_context(self, state: dict, line_name: str) -> str:  # noqa: D102
            return "审核上下文"

    stub = _Stub()
    node = stub._make_supervisor_node("minutes")
    out = asyncio.run(node({"lines": {"minutes": {"draft": {"headline": "闲聊"}}}}))
    line_state = out["lines"]["minutes"]
    check("审核调用失败 → 本线不降级（照常渲染）", line_state.get("degraded") is False, f"{line_state.get('degraded')}")
    check("审核调用失败 → 保守 approve", (line_state.get("review") or {}).get("decision") == "approve", "")
    check("审核调用失败 → 记录原因（供 quality_warning/monitor）",
          "结构契约" in str(line_state.get("review_unavailable") or ""), f"{line_state.get('review_unavailable')}")
    check("仍标记 quality_degraded（如实提示未做质量把关）", bool(out.get("quality_degraded")), "")
    route = stub._make_route("minutes")
    state_after = {"lines": {"minutes": {"review": line_state["review"], "revision_count": 0}}}
    check("路由不再走 fallback（approve → __end__）", route(state_after) == "__end__", f"{route(state_after)}")


def test_minutes_chain_consistency() -> None:
    """纪要链路口径一致（2026-09 审计 ① ② ③）：形态单点化 + 摘要预算合一 + 审核两句。

    审计发现的矛盾：①摘要条数/句数在草稿 prompt（2–8 条、1–5 句）、契约（≤4 条、
    ≤3 句）、渲染 prompt 三处互斥；②形态在草稿/渲染 prompt 里是旧口径
    （每条以分类标签开头、每栏至少 2 个分类标签、20–80 字、加粗每条 2–3 处），
    与装配侧冲突——"每栏至少 2 个分类标签"正是标签复用（行20「盖章互动」×4）的成因；
    ③审核"无锚点空条/关键遗漏"会把合规的合并段判成空条，是剩余降级路径。
    """
    from domain.meeting.tasks.minutes.contracts import MINUTES_GENERATION_OUTPUT_CONTRACT as gen_contract
    from domain.meeting.tasks.minutes.prompts import (
        MINUTES_GENERATION_SYSTEM_PROMPT as draft,
        MINUTES_RENDER_PROMPT as render,
        MINUTES_SUPERVISOR_DOMAIN_PROMPT as supervisor,
    )
    from tools.templates.body_rules import BODY_FORMAT_RULES
    from tools.templates.template_prompt import PLACEHOLDER_RULES

    from ._base import _PLACEHOLDER_FILL_SYSTEM as fill_system
    from ._placeholder import build_placeholder_fill_user

    user = build_placeholder_fill_user("内容来源：略。", FILL_TPL)
    # ③ 形态单点化：五处逐字包含同一份规则
    for label, text in (
        ("装配 system prompt", fill_system),
        ("装配 user 消息", user),
        ("自由渲染 PLACEHOLDER_RULES", PLACEHOLDER_RULES),
        ("纪要草稿 prompt", draft),
        ("纪要渲染 prompt", render),
    ):
        check(f"{label} 逐字包含 BODY_FORMAT_RULES（单点维护）", BODY_FORMAT_RULES in text, "")
    stale = ["每栏至少 2 个分类标签", "每条 20–80 字", "每条 2–3 处（分类标签"]
    hit = [k for k in stale if any(k in t for t in (fill_system, user, PLACEHOLDER_RULES, draft, render))]
    check("旧形态口径已从全部路径清除", not hit, f"残留={hit}")

    # ② 摘要分段：三处同一套（段数按内容、单段 ≤3 句/约 200 字），且旧数字已清除
    check("草稿 prompt / 契约都不再设固定段数上限",
          "≤4 段" not in draft and "≤4 段" not in gen_contract, "")
    check("草稿 prompt / 契约同写「不超过 3 句或约 200 字」",
          "不超过 3 句或约 200 字" in draft and "不超过 3 句或约 200 字" in gen_contract, "")
    check("契约声明「段数/句数是表达预算，不构成删事实的理由」",
          "不构成删事实的理由" in gen_contract, "")
    old_summary = [
        k
        for k in ("全篇 2–8 条", "每段最多 3 句", "2–8 条", "≤4 段", "每段 2–5 句", "2–5 句")
        if k in draft or k in gen_contract or k in render
    ]
    check("旧的互斥摘要口径已清除", not old_summary, f"残留={old_summary}")

    # ① 审核两句：合并段不算空条 + 关键遗漏按事实判（各只保留一份，不许重复）
    check("审核 prompt：合并型摘要段不算空条", "合并型摘要段不算空条" in supervisor, "")
    check("审核 prompt：关键遗漏按事实判、不按条数判",
          "按事实判，不按条数判" in supervisor, "")
    check("审核 prompt：不拦截/要拦截各只一份（旧的重复块已合并）",
          supervisor.count("不拦截：") == 1 and supervisor.count("要拦截：") == 1,
          f"不拦截={supervisor.count('不拦截：')} 要拦截={supervisor.count('要拦截：')}")


def test_understanding_trim_lists() -> None:
    """理解裁剪：可空名单与必须写全名单不许重叠，两名单并集 = 契约全部字段。

    回归背景：两张名单各写一份（后者写死在 agent 里），曾出现 risk_hints
    同时被列为「可空」和「必须写全」，且必须写全名单漏掉 topics/risks/open_questions。
    """
    from dataclasses import fields as dc_fields

    from domain.meeting.meeting_core.meeting_understanding_agent import (
        _trim_instruction,
    )
    from domain.meeting.models import MeetingUnderstanding

    order = [f.name for f in dc_fields(MeetingUnderstanding)]
    cases = (
        ("minutes", {"risk_hints"}),
        ("risks", {"topics", "action_hints"}),
        ("actions", {"topics", "risks", "open_questions", "risk_hints"}),
    )
    for line, skip in cases:
        text = _trim_instruction(line, skip)
        blank_line = next(l for l in text.splitlines() if "只允许以下字段输出空数组" in l)
        keep_line = next(l for l in text.splitlines() if "必须照常" in l)
        # 只取名单本体：「仅供 X 线使用」里的线名可能恰好等于字段名（risks）
        blank_part = blank_line.split("空数组 []：", 1)[-1]
        keep_part = keep_line.split("（", 1)[-1].split("）", 1)[0]
        blank_fields = {f for f in order if f in blank_part}
        keep_fields = {f for f in order if f in keep_part}
        check(f"裁剪名单-{line}：可空与必须写全不重叠",
              not (blank_fields & keep_fields),
              f"重叠={sorted(blank_fields & keep_fields)}")
        check(f"裁剪名单-{line}：两名单并集 = 契约全部字段",
              blank_fields | keep_fields == set(order),
              f"缺={sorted(set(order) - (blank_fields | keep_fields))}")
        check(f"裁剪名单-{line}：可空名单与本线裁剪一致",
              blank_fields == skip, f"实际={sorted(blank_fields)}")
    check("无可裁剪字段时不拼裁剪指令", _trim_instruction("", set()) == "", "")


def test_overview_cap_and_column_scope() -> None:
    """概括/背景栏：逐栏给出上限与边界，且不许跨栏复述。

    回归背景（now.xlsx 实测）：`exchange_forum` 的 [沟通背景与目的] 无上限 →
    模型写出 2764 字、45 句的单段，并把 [信息同步] 的明细又复述一遍。
    对策：字段清单里逐栏给"最多 3 段、每段不超过 400 字"+「本栏不复述」，
    栏位自己声明了尺寸的以模板为准；规则层加「一栏只写自己的事」。
    """
    from tools.template_router._base import _describe_field
    from tools.templates.body_rules import BODY_FORMAT_RULES
    from tools.templates.template_prompt import PLACEHOLDER_RULES

    from ._base import _PLACEHOLDER_FILL_SYSTEM as fill_system
    from ._detect import _parse_field
    from ._placeholder import build_placeholder_fill_user

    # ① 未声明尺寸的概括栏：拿到默认上限 + 边界
    plain = _describe_field(1, _parse_field("一段话概括参与方、沟通主题与目的、达成的结果"))
    check("概括栏（无尺寸声明）拿到默认上限",
          "最多 3 段、每段不超过 400 字" in plain, f"{plain[:80]}")
    check("概括栏（无尺寸声明）带「本栏不复述」边界",
          "本栏不复述" in plain and "归各自栏目" in plain, f"{plain[:80]}")

    # ② 自己声明了尺寸的概括栏：以模板为准，不叠加默认上限
    sized = _describe_field(1, _parse_field("一段话概括：先写这段文本是什么；**单段不超过约 200 字**，信息多就拆段"))
    check("已声明尺寸的概括栏不被叠加默认上限",
          "最多 3 段、每段不超过 400 字" not in sized and "本栏不复述" in sized,
          f"{sized[:90]}")

    # ③ 取材来源句（「从概况与原文提取下一步」）不算概括栏，不给概况规格
    ref = _describe_field(
        2, _parse_field("**从概况与原文提取下一步**（不要因为已写进风险表就不写）：核心交付物、验收标准")
    )
    check("取材来源句不被误判为概括栏",
          "最多 3 段、每段不超过 400 字" not in ref, f"{ref[:80]}")

    # ④ 规则层：装配 system/user、自由渲染、共用形态规则都写了这份口径
    user = build_placeholder_fill_user("内容来源：略。", FILL_TPL)
    for label, text in (
        ("装配 system prompt", fill_system),
        ("装配 user 消息", user),
        ("自由渲染 PLACEHOLDER_RULES", PLACEHOLDER_RULES),
        ("共用形态规则", BODY_FORMAT_RULES),
    ):
        check(f"{label}：概括栏上限口径到位",
              "最多 3 段、每段不超过 400 字" in text or "单段不超过 400 字" in text, "")
    check("装配 system prompt：一栏只写自己的事（结论/速览栏可再现）",
          "一栏只写自己的事" in fill_system
          and "速览栏按各自用途可再次呈现同一事实" in fill_system, "")
    check("装配 user 消息：一栏只写自己的事（结论/速览栏可再现）",
          "一栏只写自己的事" in user
          and "速览栏按各自用途可再次呈现同一事实" in user, "")
    check("篇幅口径只管整篇总量（不再压过单栏上限）",
          "这一条只管整篇总量" in fill_system, "")


def test_section_char_budget_scope() -> None:
    """段落字数上限：栏名要取到（`# [概况]` → 概况）；单条预算不许当整节上限。

    回归背景：栏名用 `re.sub(r"\\[[^\\[\\]]*\\]", "", ...)` 连括号内容一起删掉 →
    拿到「本节」，_overlong_issue 的标题匹配永不命中（模板声明的上限静默失效）；
    而只修标题又会让「每条 30–100 字」被当成整节 100 字上限（合规的 5 条会被判超限返工）。
    """
    from tools.templates.template_eval import parse_section_char_budgets

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
    from domain.meeting.tasks.minutes.prompts import MINUTES_RENDER_TEMPLATE_PROMPT
    from tools.templates.body_rules import BODY_FORMAT_RULES
    from tools.templates.template_prompt import PLACEHOLDER_RULES

    from ._base import _PLACEHOLDER_FILL_SYSTEM as fill_system
    from ._placeholder import build_placeholder_fill_user

    user = build_placeholder_fill_user("内容来源：略。", FILL_TPL)
    for label, text in (
        ("装配 system prompt", fill_system),
        ("装配 user 消息", user),
        ("自由渲染 PLACEHOLDER_RULES", PLACEHOLDER_RULES),
        ("共用形态规则", BODY_FORMAT_RULES),
        ("纪要模板渲染 prompt", MINUTES_RENDER_TEMPLATE_PROMPT),
    ):
        check(
            f"{label}：缺省词按模板约定、通用层只兜底「未提及」",
            "模板没约定" in text or "未约定时写「未提及」" in text,
            "",
        )
    stale = [k for k in ("无则「未明确」", "缺内容直接写「未提及」") if k in fill_system or k in user]
    check("通用层不再强推单一缺省词（旧写法已清除）", not stale, f"残留={stale}")


def test_general_minutes_speedread() -> None:
    """通用纪要：补「分段速览」承载位（按时间/板块维度再现，不算重复），200 字上限统一到 400。

    回归背景（now.xlsx 对比）：同一场 ASR 周会，基线 1628 字里有「段落速览」——按时间段把要点
    再讲一遍（时间维度，不是主题重复）；我们只有 [全文摘要]+[要点梳理] 两栏 → 1061 字且缺时间维度。
    """
    from tools.template_router._base import (
        split_template_meta,
        wrap_template_requirement,
    )
    from tools.template_router._placeholder import plan_placeholder_fill
    from tools.templates.template_eval import parse_section_char_budgets

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
    check("通用纪要：摘要/要点/速览三栏都在", len(plan["scalars"]) >= 3, f"字段数={len(plan['scalars'])}")
    check("通用纪要：新增「分段速览」栏（按推进顺序）",
          any("推进顺序" in h and "时间段" in h for h in hints), f"{hints}")
    budgets = parse_section_char_budgets(tpl)
    check("通用纪要：摘要上限统一到 400 字/段",
          any(b["hi"] == 400 and b.get("scope") == "paragraph" for b in budgets), f"{budgets}")
    leftover = [
        p.stem
        for p in _active_dir().glob("*.md")
        if "单段不超过约 200 字" in p.read_text(encoding="utf-8")
    ]
    check("模板目录不再有「单段不超过约 200 字」", not leftover, f"残留={leftover}")


def test_fallback_text_dedupe() -> None:
    """降级拼装：headline 与文档标题重复时不再重复输出；「；」连接不再出现「。；」。"""
    from domain.meeting.tasks.minutes.contracts import MinutesFallbackRules
    from tools.core.domain_engine_text import fallback_text

    headline = "闲聊出门必带物品与个人习惯"
    state = {
        "objective_perspective": True,
        "lines": {"minutes": {"draft": {
            "headline": headline,
            "executive_summary": ["第一件事结束了。", "第二件事也完成了。"],
            "unresolved_questions": ["还有疑问吗？"],
        }}},
    }
    text, _ = fallback_text(state, "minutes", MinutesFallbackRules, {}, lambda s: "", "", title=headline)
    check("降级文本不再重复文档标题（headline 去重）", text.count(headline) == 0, f"{text[:40]!r}")
    check("多项用「；」连接、不出现「。；」", "。；" not in text and "；" in text, f"{text!r}")
    text2, _ = fallback_text(state, "minutes", MinutesFallbackRules, {}, lambda s: "", "", title="别的标题")
    check("标题不同时仍保留 headline", text2.startswith(headline), f"{text2[:24]!r}")


def test_supervisor_contract_and_unavailable() -> None:
    """审核契约必填/联动说明 + 审核调用失败时的保守放行取值。"""
    from domain.meeting.tasks.minutes.contracts import MINUTES_SUPERVISOR_OUTPUT_CONTRACT as contract
    from domain.meeting.tasks.minutes.contracts import MinutesSupervisorContract
    from tools.core.domain_engine import DomainNodes

    check("契约说明含「所有字段与检查项都必须出现」", "所有字段与检查项都必须出现" in contract, "")
    check("契约说明含 decision 联动规则",
          "decision=approve 时检查项必须全 pass" in contract and "reject 必须至少一个检查项 fail" in contract, "")
    check("feedback 说明不再只说「仅当 revise 时填写」",
          "仅当 decision=revise 时填写" not in contract and "字段必须出现" in contract, "")
    cfg = {"reject_review": {
        "decision": "reject",
        "feedback": [],
        "facts_check": {"status": "fail", "findings": ["x"]},
        "perspective_check": {"status": "pass", "findings": []},
        "consistency_check": {"status": "fail", "findings": ["y"]},
    }}
    payload = DomainNodes._conservative_review(cfg)
    check("审核不可用 → 保守 approve（检查项全 pass、feedback 空）",
          payload["decision"] == "approve" and payload["feedback"] == []
          and all(payload[k] == {"status": "pass", "findings": []}
                  for k in ("facts_check", "perspective_check", "consistency_check")),
          f"{payload}")
    check("契约仍声明 checks 非空（契约类不变量）", bool(MinutesSupervisorContract.checks), "")


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
        test_minutes_chain_consistency()
        test_understanding_trim_lists()
        test_overview_cap_and_column_scope()
        test_general_minutes_speedread()
        test_section_char_budget_scope()
        test_default_word_precedence()
        test_supervisor_unavailable_flow()
        test_advisory_checks()
        test_fallback_text_dedupe()
        test_supervisor_contract_and_unavailable()
    finally:
        logging.getLogger("tools.template_router._gate").removeHandler(handler)

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项：" + "，".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
