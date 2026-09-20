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
        "conversation_transcript": 5, "court_transcript": 3, "debate_forum": 5,
        "decision_review": 4, "exchange_forum": 5, "general_minutes": 3,
        "government_bulletin": 3, "group_seminar": 4, "hiring_report": 3,
        "home_school_liaison": 4, "interview_debrief": 4, "interview_transcript": 3,
        "knowledge_memo": 3, "legal_advisory": 4, "media_briefing": 4,
        "media_qa_session": 4, "personal_memo": 4, "product_launch": 4,
        "admission_briefing": 5,
        "project_progress": 2, "psychological_session": 3, "research_dialogue": 3,
        "retrospective_session": 5, "site_visit_tour": 4, "special_lecture": 4,
        "team_meeting": 5, "workshop_session": 4,
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
    """漏填兜底：字段缺失 → 点名缺栏重试；三轮仍缺 → 补缺省词保结构（不再退回 freeform）。"""
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
    # 不再 return None：三轮重试后给仍空的字段补「未提及」，保住模板结构（原先整篇退回 freeform）
    check("三轮仍缺栏 → 补缺省词保结构（不放半截文档、也不退回 freeform）",
          bool(out1) and "未提及" in (out1 or "") and "# 丙栏" in (out1 or ""), f"out={(out1 or '')[:80]!r}")
    check("仍空字段未被静默丢弃（甲/乙栏内容在）",
          "甲栏内容" in (out1 or "") and "乙栏内容" in (out1 or ""), "")
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
    "`## 名称` 小节之下**必须** `- ` 一条一行",
)


TEMPLATE_SHAPE_SNIPPETS = {
    "retrospective_session": "不要每条都补「责任人无，时间无」",
    "hiring_report": "本栏明细由下表承载",
    "hiring_report#维度": "不自行发明能力模型",
    "media_briefing": "**一条一个主题**——同一文件、同一板块、同一口径的多项指标或举措**合并成一条**",
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
        blank_line = next(l for l in text.splitlines() if "键名必须保留、值给空数组" in l)
        keep_line = next(l for l in text.splitlines() if "必须照常" in l)
        # 只取名单本体：「仅供 X 线使用」里的线名可能恰好等于字段名（risks）
        blank_part = blank_line.split("空数组 []**：", 1)[-1]
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
    check("首栏（概括·无尺寸）拿到「只写一段」口径与 400 上限",
          "只写一段完整概括" in plain and "不超过 400 字" in plain, f"{plain[:80]}")
    check("首栏（概括·无尺寸）带要素清单（场合/覆盖/结论；数字有则写）",
          all(k in plain for k in ("谁/什么场合", "覆盖哪几块", "结论或基调", "原文有关键数字时")),
          f"{plain[:120]}")
    check("首栏（概括·无尺寸）带「本栏不复述」边界",
          "本栏不复述" in plain and "归各自栏目" in plain, f"{plain[:80]}")
    non_first = _describe_field(2, _parse_field("一段话概括参与方、沟通主题与目的、达成的结果"))
    check("非首栏的概括栏仍按上限口径（不要求下限）",
          "最多 3 段、每段不超过 400 字" in non_first and "1–2 段完整概括" not in non_first,
          f"{non_first[:80]}")
    # 首栏自称"交代…"并已自列要素（就医/宣讲/研讨）：补下限口径，但不套会议专用四要素
    authored = _describe_field(
        1, _parse_field("一段话交代患者基本信息、就诊科室与时间、本次就诊的核心主诉与初步判断")
    )
    check("自述要素的首栏拿到下限口径（只写一段）",
          "只写一段完整概括" in authored and "按本栏说明把要素交代完整" in authored,
          f"{authored[:100]}")
    check("自述要素的首栏不套会议专用四要素（避免语义打架）",
          "以分享为主" not in authored and "谁/什么场合" not in authored, f"{authored[:100]}")

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
    check("篇幅优先级明确（模板栏位上限不被动态预算覆盖）",
          "模板显式栏位上限 > 动态总预算 > 默认形态规则" in fill_system, "")


def test_first_column_min() -> None:
    """总述栏（第 1 栏）下限：按原文规模算（tier 下限的 22%，夹 180–400），写进【篇幅预算】。

    回归背景（2026-09 now.xlsx 实测 56 条）：首栏汉字中位数约 150（最薄 88），
    而通用兜底只给了上限（≤3 段/≤400 字）——上限治不了薄；下限只给第 1 栏，明细栏不逼。
    """
    from tools.templates.length_budget import budget_line, first_column_min

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
    """通用纪要：「分段速览」承载位（按时间/板块维度再现，不算重复）；2026-09-20 改时间轴口径。

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
    # 摘要数字口径：原文有时总量 3–5 个，不是逐板块配额（2026-09-19 实测联播场：摘要 655 字
    # 带 48 个数字、与要点梳理 4-gram 重合 65%——"至少带 1–3 个"被执行成每板块 1–3 个）
    abstract = hints[0]
    check("通用纪要：原文有数字时全段选 3–5 个，没有则不强求",
          "原文有关键数字时选 3–5 个" in abstract and "没有则不强求、不补写" in abstract
          and "不是每个板块都配数字" in abstract and "其余数字归 [要点梳理]" in abstract, abstract[:90])
    check("通用纪要：旧配额口径已清除（至少带 1–3 个 / 一条数字都没有＝不合格）",
          "至少带 1–3 个" not in abstract and "一条数字都没有＝不合格" not in abstract, "")
    check("通用纪要：板块多时按主题打包 + 每板块一句话 ≤40 字",
          "按主题打包概括" in abstract and "每个板块最多一句话" in abstract
          and "单句不超 40 字" in abstract and "禁止逐板块展开数字" in abstract, abstract[:90])
    budgets = parse_section_char_budgets(tpl)
    # 2026-09-20 用户口径：速览从「每段最多 300 字的一段话」改成「时间轴：标题 + 一句主线」，
    # 段落上限随之取消——有上限就会被当成目标（13 段 × 272 字曾占全篇一半）。
    check("通用纪要：摘要为一段 250–400（节级），速览不再声明字数",
          any(b["title"] == "全文摘要" and b["lo"] == 250 and b["hi"] == 400 and b["scope"] == "section" for b in budgets)
          and not any(b["title"] == "分段速览" for b in budgets),
          f"{budgets}")
    seg_spec = next(l.strip() for l in raw.splitlines() if "推进顺序" in l)
    check("通用纪要：速览改为一句话主线（每段至少一句、不铺陈）",
          "每个时间段一行" in seg_spec and "只写一句主线" in seg_spec
          and "每段至少一句" in seg_spec and "单段不超过约 300 字" not in seg_spec
          and "不重复 [要点梳理] 已列的条目与数字" in seg_spec,
          seg_spec[:80])
    from tools.execution.hard_execution import (
        _no_split_sections,
        split_overlong_paragraphs,
    )

    check("通用纪要：速览不再声明「不拆段」（形态由模板的一句话口径约束）",
          "分段速览" not in _no_split_sections(tpl), f"{_no_split_sections(tpl)}")
    long_seg = "这是一段概览文字。" * 55  # ≈440 汉字
    fixed_seg, seg_notes = split_overlong_paragraphs(
        "# 通用纪要\n\n# [分段速览]\n## 08:00-12:30 现场检查\n" + long_seg + "\n", tpl
    )
    check("通用纪要：速览栏已无字数上限 → 程序不再拆行（改由模板约束形态）",
          not seg_notes and len([q for q in fixed_seg.split("\n\n") if "概览文字" in q]) == 1,
          f"notes={seg_notes}")
    leftover = [
        p.stem
        for p in _active_dir().glob("*.md")
        if "单段不超过约 200 字" in p.read_text(encoding="utf-8")
    ]
    check("模板目录不再有「单段不超过约 200 字」", not leftover, f"残留={leftover}")


def test_document_budget_not_misread() -> None:
    """全文预算不许从"段落说明里顺带出现的全文标记"误判出来。

    回归背景（2026-09 性能复盘）：general_minutes 的摘要说明同时写了「（摘要通篇无数字＝不合格）」与
    「每段不超过 400 字」——"通篇"命中全文标记，于是整份纪要（600–2600 字）被判
    「超出全文上限 400 字」：触发压缩返工（多一次整篇 LLM 调用），freeform 路径还会按句界
    截断到 ~420 字（既慢又丢内容）。
    """
    from tools.templates.template_eval import (
        parse_document_char_budget,
        parse_section_char_budgets,
    )

    from ._base import split_template_meta, wrap_template_requirement

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


def test_paragraph_split() -> None:
    """段落字数超限：按句界确定性拆段（零 LLM 调用），拆完不再报「超出段落字数上限」。"""
    from tools.execution.hard_execution import (
        gate_render_output,
        split_overlong_paragraphs,
    )
    from tools.templates.template_eval import parse_section_char_budgets

    from ._base import split_template_meta, wrap_template_requirement

    body, req = split_template_meta(
        "# 甲\n\n<!-- requirement\n客观记录\n-->\n\n"
        "# [摘要]\n[一段话（最多 3 段、每段不超过 400 字）交代要点]\n"
    )
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines = lines[i + 1 :]
            break
    tpl = wrap_template_requirement("\n".join(lines).strip(), req)
    check("拆分用模板：段落上限已识别",
          any(b["hi"] == 400 and b.get("scope") == "paragraph"
              for b in parse_section_char_budgets(tpl)),
          f"{parse_section_char_budgets(tpl)}")

    long_para = "本次会议围绕小区物业服务与业主权益展开专项讨论。" * 30  # ≈690 汉字
    doc = f"# 摘要\n{long_para}\n"
    fixed, _ = split_overlong_paragraphs(doc, tpl)
    body_only = fixed.split("\n", 1)[1] if "\n" in fixed else fixed
    parts = [p for p in body_only.split("\n\n") if p.strip()]
    han_of = lambda s: len(re.findall(r"[\u4e00-\u9fff]", s))
    check("超长段被按句界拆开（≥2 段且每段汉字 ≤ 上限）",
          len(parts) >= 2 and all(han_of(p) <= 400 for p in parts),
          f"段数={len(parts)} 各段汉字={[han_of(p) for p in parts]}")
    check("拆分只加换行、不改文字",
          re.sub(r"\s", "", fixed) == re.sub(r"\s", "", doc), "")
    gate = gate_render_output(tpl, fixed)
    check("拆完不再报「超出段落字数上限」",
          not any("超出段落字数上限" in x for x in gate["issues"]), f"{gate['issues']}")


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
        "class_transcript": "课堂互动与答疑",
    }
    missing: list[str] = []
    old_mandate: list[str] = []
    for stem in qa_templates:
        text = (_active_dir() / f"{stem}.md").read_text(encoding="utf-8")
        if "两方都对应不上人时才写成" not in text:
            missing.append(stem)
        if _re.search(r"[，：]写成「\*\*问\*\*：…」换行", text):  # 旧强制句式；新文是「才写成…」
            old_mandate.append(stem)
    check("5 个问答模板都写清「称呼优先、问/答兜底」", not missing, f"缺={missing}")
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

    from tools.templates.body_rules import BODY_FORMAT_RULES

    check("共用形态规则为对话称呼开了加粗例外",
          "问答/对话的称呼行按模板要求每轮加粗" in BODY_FORMAT_RULES, "")


def test_progress_table_rows() -> None:
    """项目进度会：两张表要"分项成行"、风险含待办型、状态补齐四态——且不许写示例式软引导。

    回归背景（2026-09，now.xlsx 行8）：进度追踪 7 行装了约 31 个分项（一个模块一行），
    风险预警只收"实体缺陷型"，把"尚未开展 / 资料依据不完善"这类待办型漏到别的栏 → 条目偏少。
    """
    text = (_active_dir() / "project_progress.md").read_text(encoding="utf-8")
    for need in (
        "一个分项一行",
        "原文有几个分项就写几行，宁多不漏",
        "⏸未开始",
        "尚未开展或尚未闭合的事项",
        "资料、依据、签字等程序性不完善",
    ):
        check(f"项目进度会：含「{need}」", need in text, "")
    check("项目进度会：不夹带示例式软引导（如「应拆成 … 五行」）",
          "应拆成" not in text and "五行" not in text, "")
    from tools.templates.body_rules import BODY_FORMAT_RULES

    check("共用形态规则的状态集同步四态",
          "⏸未开始" in BODY_FORMAT_RULES, "")


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


def test_knowledge_memo_groups() -> None:
    """知识笔记 [核心结论]：固定三子组 + 缺省写法（治"待澄清"空条与说明句）。

    回归背景（2026-09，now.xlsx 行15）：原文没有"待澄清"信号时模型写了
    「- 原文未提及待澄清问题。」——既是空条，又踩了"禁止缺失说明句"；
    同时"适用条件/前提/边界"这类普遍存在的内容此前被埋进"易混淆点"。
    """
    text = (_active_dir() / "knowledge_memo.md").read_text(encoding="utf-8")
    for need in ("## 核心结论", "## 易混点与适用边界", "## 待澄清问题",
                 "整组没内容就不出现该组", "不要写「原文未提及…」这类说明句"):
        check(f"知识笔记：含「{need}」", need in text, "")
    check("知识笔记：仍保留输出契约的栏名 [核心结论]",
          "# [核心结论]" in text, "")
    # 2026-09-19 now.xlsx 行13 实测：全篇 900 汉字（低于下限 1080），概念栏里出现
    # 「笔记中内容较多，未详细展开」这类模型自我省略。
    check("知识笔记：概述栏给尺寸 250–350（含下限口径）",
          "约 250–350 字" in text and "低于 250 字说明三项没交代清" in text, "")
    check("知识笔记：每个概念 2–4 条（定义/步骤/评点）+ 禁止自我省略说明",
          "每个概念 2–4 条" in text and "不得写「未详细展开」" in text
          and "篇幅所限" in text, "")


def test_clinical_history_column() -> None:
    """就医咨询：4 栏 + 5 列药品表（2026-09-20 按 v2 参考收敛），病史并入 [就诊概况]。

    回归背景（2026-09，now.xlsx 行24）：原文 5 次提到"过敏"，产出一次都没写（基线写了）；
    职业（研究所）等个人史同样丢失——4 栏后这些硬要求挂在 [就诊概况] 上。
    """
    text = (_active_dir() / "clinical_advisory.md").read_text(encoding="utf-8")
    for need in (
        "过敏史、禁忌类信息原文出现就必须写入",
        "原文提到就逐项落条",
        "职业照原文",
        "只有医生或原文明确认定为异常、偏高、偏低或需关注的指标才加粗",
        "不得依据医学常识、参考范围或模型判断自行认定异常",
    ):
        check(f"就医咨询：含「{need}」", need in text, "")
    check("就医咨询：旧口径（病史留给「下面各栏」）已清除",
          "病史与用药细节留给下面各栏" not in text, "")
    check("就医咨询：已收敛为 4 栏（[病史与背景]/[病情说明与沟通] 退场）",
          "# [病史与背景]" not in text and "# [病情说明与沟通]" not in text
          and text.count("\n# [") == 4, "")
    # 药品明细表：5 列（药品名称/剂量/频次/用法/注意事项）；药名不漏记；整表无药只写一行缺省
    # —— 与程序侧「整表缺省保留首行」「占位行按表头列数生成」配套。
    check("就医咨询：有药名就一行一药、缺格写 `—`",
          "原文出现过的药名不得漏记" in text and "有药名而某格缺失的写 `—`" in text, "")
    check("就医咨询：药表五列 = 药品名称 / 剂量 / 频次 / 用法 / 注意事项",
          "| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |" in text
          and "| … | … | … | … | … |" in text
          and "（药名、剂量、频次、用法）" in text
          and "用法用量 | 注意事项" not in text, "")
    check("就医咨询：一条药品信息都没有时整表只写一行缺省（不留空表）",
          "原文一条药品信息都没有时整表只写一行「未提及」并保留该行，不留空表" in text, "")
    check("就医咨询：缺省禁令已收窄到单元格级（旧「原文没写的项不写」已清除）",
          "原文没写的项**不写**" not in text and "不逐格标「未明确」" in text, "")
    # 5 列的格位纪律（2026-09-20 评测：剂量被挂到另一味药名下、非药品项混进表）
    check("就医咨询：格位纪律（每格只写该格内容、同行几格同源）",
          "表格每一格只写该格该写的内容" in text
          and "同一行的几格必须来自同一味药的同一处表述" in text, "")
    check("就医咨询：药名与用法同源 + 非药品项不进表",
          "用法用量必须与药名同源" in text
          and "原文提到的药品、中成药与补充剂可进表" in text
          and "仅作为对比或举例提到、并非该患者用药的不进表" in text, "")
    # 尺寸：带表格的栏（[治疗方案与医嘱]）解析不出节级预算（parser 行为），写进文本即可。
    from tools.templates.template_eval import parse_section_char_budgets

    got = [(b["title"], b["lo"], b["hi"]) for b in parse_section_char_budgets(text)]
    check("就医咨询：概况/诊断/复诊三栏尺寸口径（300–500 / 250–500 / 100–250）",
          ("就诊概况", 300, 500) in got and ("诊断与检查结果", 250, 500) in got
          and ("复诊与预警信号", 100, 250) in got, f"{got}")
    check("就医咨询：概况栏要素密度（主诉照原文写全 + 病史并入 + 未确诊写法）",
          "核心主诉照原文写全" in text
          and "未确诊照原文写「考虑…，需…进一步明确」，不把推测写成确诊" in text, "")
    check("就医咨询：症状叙述不算过程铺陈、不得压缩",
          "症状与病史描述照原文写全" in text
          and "不得当成「过程铺陈」压缩成一句" in text, "")
    check("就医咨询：各栏不再硬要原文没有的项（按实际出现立条 / 有哪几类写哪几类）",
          "按原文实际给出的类别立条" in text
          and "有哪几类写哪几类，没有的类别不立条" in text, "")
    check("就医咨询：复诊栏条件化（原文给了安排才写）+ 预警逐项 + 观察项落点",
          "原文给了复诊/随访安排才写复诊时间" in text
          and "原文提到的预警症状必须逐项写入" in text
          and "需要观察的变化" in text, "")


def test_overview_specs_have_scope() -> None:
    """概况栏要有“要素 + 尺寸 + 边界”：团队例会/辩论会两处已补，防止回退成裸概括。

    回归背景（2026-09，now.xlsx 行23/26）：[例会概况] 说明只有“一段话概括主要内容”，
    结果 308 字吞掉了 [工作进展] 的明细；[辩论内容概述] 把论据写进了概述，
    而 [结辩与评委点评] 只写了 145 字（真的薄）。
    """
    team = (_active_dir() / "team_meeting.md").read_text(encoding="utf-8")
    debate = (_active_dir() / "debate_forum.md").read_text(encoding="utf-8")
    for text, name, size in (
        (team, "团队例会", "约 250–400 字"),
        (debate, "辩论会", "约 250–400 字"),
    ):
        check(f"{name}：概况栏声明尺寸（{size}）", size in text, "")
    check("团队例会：概况栏写明六要素（谁/为什么开/议题及程度/态势/结论/数字锚点）",
          all(k in team for k in (
              "参会成员或部门", "为什么开这次会", "主线议题",
              "已定 / 待定 / 仅同步", "整体态势", "结论与下一步方向",
              "关键数字或时间节点", "原文没有则不强求、不补写",
          )), "")
    check("团队例会：概况栏用归位式边界（只到议题级主线 + 态势，不写任务级明细）",
          "本栏只到「议题级主线 + 态势」" in team and "不写任务级明细" in team
          and "[工作进展]" in team and "[协作需求]" in team, "")
    check("团队例会：概况栏声明下限口径（低于 250 字＝没交代清）",
          "低于 250 字说明没交代清" in team, "")
    from tools.templates.template_eval import parse_section_char_budgets

    ov = [b for b in parse_section_char_budgets(team) if b["title"] == "例会概况"]
    check("团队例会：概况栏仍解析为节级 250–400（尺寸口径未漂）",
          bool(ov) and ov[0]["scope"] == "section" and ov[0]["lo"] == 250 and ov[0]["hi"] == 400,
          f"{ov}")
    check("辩论会：概况栏写明边界（不展开什么、归哪栏）", "不展开" in debate, "")
    check("团队例会：[工作进展] 声明容量引导（并列任务各占一条 + 缩进子条）",
          "并列的多个任务各占一条" in team and "缩进子条" in team, "")
    check("团队例会：[协作需求] 声明去重口径（不复述进展 + 跨人依赖一条不落）",
          "已在 [工作进展] 写过的进展不复述" in team and "跨人依赖一条不落" in team, "")
    # 新增承载位（2026-09-19 now.xlsx 行22）：例会只有 进展/协作 两栏，决定、待办与未决
    # 全挤进 [工作进展]（15 条里混着"下周去洛阳"“招聘20位师傅”“方向可能偏了”）→ 一栏流水账。
    check("团队例会：新增 [决定与待办]（决议 + 行动项：谁/何时前/做什么）",
          "# [决定与待办]" in team and "谁、何时前、做什么" in team
          and "已在 [工作进展] 条目里写过的" in team, "")
    check("团队例会：新增 [待确认与风险]（未决/分歧/阻塞延期 + 不替团队预判）",
          "# [待确认与风险]" in team and "尚未议定或需要再确认的事项" in team
          and "不替团队预判" in team, "")
    check("团队例会：[工作进展] 声明栏间分工（进展 vs 决定与待办不重复）",
          "本栏只写\"已经做了什么、到什么程度\"" in team and "归 [决定与待办]，两栏不重复" in team, "")
    check("团队例会：requirement 覆盖新栏（决议与待办 / 待确认事项）",
          "决议与待办事项" in team and "待确认事项" in team, "")
    # 尺寸口径（2026-09-19 now.xlsx 行22：全篇 1090，工作进展只有 530 且 15 条平铺）
    check("团队例会：工作进展给尺寸与分组（500–900 字 / 每组 2–5 条 / 不写同名标题）",
          "约 500–900 字" in team and "每组 2–5 条" in team
          and "不要在栏内再写一个与栏名同名的" in team, "")
    check("团队例会：协作需求与两个新栏都有尺寸",
          "约 150–300 字" in team and "约 150–350 字" in team and "约 100–250 字" in team, "")
    from tools.templates.template_eval import parse_section_char_budgets as _pscb

    tm_budgets = [(b["title"], b["hi"]) for b in _pscb(team)]
    check("团队例会：五栏尺寸都被解析（概况 400 / 进展 900 / 决定 350 / 协作 300 / 未决 250）",
          tm_budgets == [("例会概况", 400), ("工作进展", 900), ("决定与待办", 350),
                         ("协作需求", 300), ("待确认与风险", 250)], f"{tm_budgets}")
    check("辩论会：结辩栏分三条写",
          "**正方结辩**" in debate and "**反方结辩**" in debate and "**评委点评**" in debate, "")
    check("辩论会：结辩栏给每条尺寸", "每条 60–150 字" in debate, "")


def test_debate_rounds_and_rows() -> None:
    """辩论会：栏目跟原文环节对齐（质询/总结有承载位）+ 论点各自成行 + 归因与引用口径。

    回归背景（2026-09 now.xlsx 行26）：一场 53 分钟、10284 汉字的辩论只出 1249 汉字
    （低于 tier 下限 26%），门禁却全绿——原因是模板按"立论/自由辩论/结辩"设栏，而原文
    里"自由辩论""结辩"**各出现 0 次**（原文说的是"第二个环节（质询）""第三个环节""小节"），
    质询与总结的内容无家可归；表格要求"一行一方" → 论点与论据被压成两行标签串。
    """
    debate = (_active_dir() / "debate_forum.md").read_text(encoding="utf-8")
    check("辩论会：交锋栏改为按原文环节分组（[环节交锋]）",
          "# [环节交锋]" in debate and "# [自由辩论环节]" not in debate, "")
    check("辩论会：交锋栏要求分组并写清攻守",
          "原文实际出现的环节" in debate and "谁攻谁守" in debate, "")
    check("辩论会：无环节线索时不硬分组",
          "不要硬分组" in debate, "")
    check("辩论会：归因兜底（判不准写「一方」）",
          "判不准就写「一方」" in debate, "")
    check("辩论会：每个交锋点尽量带原话引用（可只引不署名）",
          "每个交锋点尽量带 1 句原文引用" in debate and "只引原话、不署名" in debate, "")
    check("辩论会：论点表按原文出现顺序排列、正反交错（不归堆）",
          "按原文出现顺序排列（同一环节内正反交替）" in debate
          and "不要把一方的论点归堆写完再写另一方" in debate, "")
    check("辩论会：论点表行数＝论点数、不要求两方对称",
          "行数＝论点数" in debate and "每方通常 2–4 行" in debate
          and "不要一方一行" in debate and "也不要求两方行数对称" in debate
          and "（一行一方）" not in debate, "")
    check("辩论会：论点表样例行交错示范（正方→反方→正方，4 列无时间列）",
          "| 正方 | … | … | … |" in debate
          and debate.index("| 正方 | …") < debate.index("| 反方 | …")
          and debate.count("| 正方 | … | … | … |") == 2
          and "时间" not in debate.split("# [核心论点]", 1)[1].split("# [环节交锋]", 1)[0], "")
    # 新增承载位（2026-09-19 now.xlsx 行25）：一场 10284 汉字的辩论只出 956 汉字（低于下限
    # 1680）——现有四栏全是"按论点/按环节"维度，缺"按议题"的分歧归纳，质询与总结也无落点。
    check("辩论会：新增 [争议焦点]（按议题归纳双方分歧）",
          "# [争议焦点]" in debate and "按**议题**归纳双方真正的分歧" in debate
          and "3–5 条，原文出现过的焦点都要有" in debate, "")
    check("辩论会：争议焦点只归纳立场不做输赢判断、且不与论点表逐字重复",
          "不做输赢、高下" in debate and "不要与 [核心论点] 的表述逐字重复" in debate, "")
    check("辩论会：requirement 覆盖争议焦点",
          "核心争议焦点" in debate, "")
    check("辩论会：概述栏的反向引用已改名",
          "[核心论点] / [环节交锋]" in debate, "")


def test_exchange_forum_structure() -> None:
    """沟通交流会：宣贯型素材有承载位 + 共识/待协调互斥 + 首栏边界（治信息墙与重复）。

    回归背景（2026-09 now.xlsx 行3/行31）：两条数据都是单向宣贯型（源里"诉求/协调/承诺"
    全是 0 次），结构化介绍内容全倒进 [信息同步] → 3174 汉字、5 个长段（最长 902 字）；
    "夏令营时间待定"被写进 [达成共识] 又在 [待协调事项] 写一遍；首栏与信息同步数字重复。
    """
    text = (_active_dir() / "exchange_forum.md").read_text(encoding="utf-8")
    for col in (
        "# [沟通背景与目的]",
        "# [核心信息与数据]",
        "# [各方立场与诉求]",
        "# [达成共识]",
        "# [待协调事项与后续]",
    ):
        check(f"沟通交流会：栏位存在 {col}", col in text, "")
    check("沟通交流会：旧栏名已退场（[信息同步]/[待协调事项]）",
          "# [信息同步]" not in text and "# [待协调事项]\n" not in text, "")
    check("沟通交流会：新增栏要求分条与数字落地（不压成长段）",
          "每条 30–120 字" in text and "不要压成长段" in text and "数字、年份、比例" in text, "")
    check("沟通交流会：新增栏声明「条数由原文决定」",
          "条数由原文决定" in text, "")
    check("沟通交流会：立场栏收窄（事实清单归上一栏、不复述）",
          "事实与数字清单归 [核心信息与数据]" in text and "本栏不复述" in text, "")
    check("沟通交流会：共识栏与待协调互斥（待定不进共识）",
          "待定、计划、尚未确定的事项一律归 [待协调事项与后续]" in text, "")
    check("沟通交流会：待协调栏分两组（待协调事项 / 后续安排与参与方式）",
          "## 待协调事项" in text and "## 后续安排与参与方式" in text, "")
    check("沟通交流会：待协调栏缺项不写（不逐项标「待定」）",
          "缺的项不写，不要逐项标「待定」" in text, "")
    check("沟通交流会：首栏加边界（不展开明细）+ 尺寸 250–400",
          "不展开发言明细与数字清单" in text and "约 250–400 字" in text, "")
    # 2026-09-19 now.xlsx 行2 实测：首栏 1258 汉字（3 倍超限）——把宣讲的沿革/人数/经费
    # 全搬进概况，与 [核心信息与数据] 串栏。加的是"禁止清单 + 自删"而不是新栏。
    check("沟通交流会：首栏禁止统计数字与专名清单（含反例与自检）",
          "本栏不出现成串的统计数字与专名清单" in text
          and "本科生 1545 人" in text
          and "出现 3 个以上数字就说明串栏了" in text, "")
    check("沟通交流会：首栏超 400 字要求自删（只删数字/专名/介绍性事实）",
          "超过 400 字不合格" in text and "只能删数字、专名与介绍性事实" in text, "")
    check("沟通交流会：旧悬空引用已清除（「各方确认的信息」不存在）",
          "各方确认的信息" not in text, "")
    check("沟通交流会：每栏都有缺省词（空栏不成硬伤）",
          text.count("未提及") >= 5, f"未提及×{text.count('未提及')}")
    check("沟通交流会：引用有上限（3–5 句）",
          "整栏最多引 3–5 句" in text, "")


def test_interview_and_lecture_overview() -> None:
    """采访记录 [访谈概述] / 专题讲座 [讲座概况]：补"结论型"要素 + 锚点 + 尺寸 + 防越栏。

    回归背景（2026-09 now.xlsx）：两栏覆盖度好但只有 78–135 汉字（动态下限 238–370 的
    40% 左右），且要素全是"是什么"型（主题/身份/板块/形式），没有落点——行36 的概述把
    话题列全了却一句结论都没有；行48 的 78 字反而越栏写了 [核心观点与论证] 的内容。
    另：采访记录 [访谈详细记录] 缺容量引导，行36 整篇只有 tier 下限的 67% 即此栏偏小。
    """
    interview = (_active_dir() / "interview_transcript.md").read_text(encoding="utf-8")
    lecture = (_active_dir() / "special_lecture.md").read_text(encoding="utf-8")

    for name, text, anchor in (
        ("采访记录", interview, "受访者最核心的观点与结论 1–3 条"),
        ("专题讲座", lecture, "讲座的核心主张或最有分量的 2–3 个判断"),
    ):
        check(f"{name}：概况栏补了结论型要素", anchor in text, "")
        check(f"{name}：概况栏要求 1–3 个数字/专名锚点",
              "作锚点" in text, "")
        check(f"{name}：概况栏尺寸写进模板（约 250–400 字）", "约 250–400 字" in text, "")
    check("采访记录：概况栏落点要素以受访者原话为限（不做外部比较）",
          "这场访谈的看点" in interview and "以受访者原话为限" in interview, "")
    check("采访记录：结论要素写明粒度（一句话点题 + 可带数字/事例依据）",
          "每条一句话点题，可带原文的关键数字或事例作依据" in interview, "")
    check("采访记录：概况栏边界（不展开论据细节，归 [访谈详细记录]）",
          "不展开受访者的论据与细节（那是 [访谈详细记录] 的事）" in interview, "")
    check("专题讲座：概况栏边界（论证与论据清单归 [核心观点与论证]）",
          "论证过程与论据清单归 [核心观点与论证]" in lecture and "不逐条复述论点" in lecture, "")
    check("专题讲座：概况栏补落点要素（问题意识/由头 + 对听众的意义）",
          "为什么讲这个、面向谁" in lecture and "对听众的意义或适用对象" in lecture, "")
    check("专题讲座：锚点要求解开（原文有则选，案例可作锚点但不展开）",
          "原文有关键数字、案例或专名时选 1–3 个作锚点" in lecture
          and "没有则不强求" in lecture and "不展开细节" in lecture, "")
    # 承载栏「细节落地」：源里的数字/年份/案例/过程此前被压成一条条 60–90 字的主张
    check("专题讲座：[核心观点与论证] 要求多条论据各占一条（不压成一条）",
          "就各占一条，不要压成一条" in lecture, "")
    check("专题讲座：[核心观点与论证] 要求数字/年份/人名/事例落地",
          "数字、年份、人名、地名、事例与过程都要落进对应条目" in lecture, "")
    check("专题讲座：[核心观点与论证] 给单条尺寸（每条 30–120 字）",
          "每条 30–120 字" in lecture, "")
    check("采访记录：[访谈详细记录] 补了容量引导（多条各占一条、不要压成一条）",
          "各自成条，不要压成一条" in interview and "每条 30–120 字" in interview, "")
    check("采访记录：旧表述「只写这是一场什么讲座」已清除（避免只写节目单）",
          "只写\"这是一场什么讲座\"" not in lecture, "")


def test_reject_hardening() -> None:
    """无理由的 reject 不当否决 + 摘录未覆盖 ≠ 捏造（治"误判→返工→无理由 reject→降级"）。

    回归背景（2026-09-18 11:39 实测）：草稿里的《种地吧》细节（十个男孩/农业公司/小月季）
    都在原文里，但审核者拿到的"按草稿事实点摘录"没覆盖那段 → 判"无原文依据" → revise →
    返工没改（草稿 579→584 字）→ 二轮 reject（feedback 按契约为空，日志 findings=null）→
    整线降级成拼接文本，而那段降级文本里恰好又包含这些"无依据"的细节。
    """
    from tools.schema.validation import soften_unreasoned_reject

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
    from domain.meeting.tasks.minutes import prompts as minutes_prompts

    domain_prompt = minutes_prompts.MINUTES_SUPERVISOR_DOMAIN_PROMPT
    check("审核领域提示词：无理由 reject 会被按 approve 处理",
          "没写理由的 reject 会被程序按 approve 处理" in domain_prompt, "")
    check("审核领域提示词：核对不了按未覆盖处理（不是捏造）",
          "写「未能核对：X」并 approve" in domain_prompt, "")
    engine_src = (
        __import__("pathlib").Path("tools/core/domain_engine.py").read_text(encoding="utf-8")
    )
    check("审核证据包：明文写「摘录未覆盖 ≠ 无依据」",
          "摘录未覆盖 ≠ 无依据" in engine_src and "不得据此 revise 或 reject" in engine_src, "")
    check("审核节点：软化的 reject 已接入（approve 后不再走 fallback）",
          "soften_unreasoned_reject(payload)" in engine_src
          and "reject_downgraded" in engine_src, "")
    schema_src = (
        __import__("pathlib").Path("tools/schema/contracts.py").read_text(encoding="utf-8")
    )
    check("审核契约说明：reject 需写明具体理由",
          "该检查项的 findings 要写明具体理由" in schema_src, "")


def test_conversation_and_seminar_enrichment() -> None:
    """对话记录 / 小组讨论：首栏补结论要素+尺寸、新增关键原话、共识栏双侧、细节落地。

    回归背景（2026-09 now.xlsx）：两栏覆盖度好但首栏只有 103–168 汉字（动态下限 238–370）；
    对话记录 2388 字原文只出 722 汉字、[交流内容] 仅 3 条且把原话塞在里面被压成转述；
    小组讨论 [共识形成] 124–197 字、[发言要点] 里源文的"三次/四个/十分钟"未落地。
    末栏（待探讨/延伸话题）的空是源文所致（那些场"下次/待/分工/负责"全为 0 次），
    所以只把口径写清楚（搁置、没聊透也算），不加下限、不逼内容。
    """
    conv = (_active_dir() / "conversation_transcript.md").read_text(encoding="utf-8")
    semi = (_active_dir() / "group_seminar.md").read_text(encoding="utf-8")

    for name, text, lead, anchor, bound in (
        ("对话记录", conv, "倾向与差异对照", "值得记的数字或具体事例", "不逐条复述各方发言"),
        ("小组讨论", semi, "讨论的整体倾向或是否有结论", "作锚点", "不展开各方发言明细"),
    ):
        check(f"{name}：首栏补结论型要素", lead in text, "")
        check(f"{name}：首栏声明尺寸（约 250–400 字）", "约 250–400 字" in text, "")
        check(f"{name}：首栏要素含锚点要求", anchor in text, "")
        check(f"{name}：首栏带防越栏边界", bound in text, "")

    check("对话记录：新增 [关键原话] 栏（最多 8 句、逐字、`> “……”` 金句 / `- 背景：`）",
          "# [关键原话]" in conv and "最多 8 句" in conv and "不改字、不合并" in conv
          and "背景行 `- 背景：……`" in conv, "")
    check("对话记录：新栏声明缺省词（空栏不成硬伤）",
          "原文确实没有可摘的原话就写「未提及」" in conv, "")
    check("对话记录：[交流内容] 不再夹引用（原话归 [关键原话]）",
          "本栏不夹引用" in conv and "原话统一放 [关键原话]" in conv, "")
    check("对话记录：[交流内容] 要求细节落地（不只写主张）",
          "都要落进对应条目，不要只写主张" in conv, "")
    check("对话记录：[交流内容] 每位发言人各占一条缩进子条（合并只限同一次发言）",
          "每位发言人的说法各占一条缩进子条" in conv and "同一次发言的碎片合并成一条" in conv
          and "不要把多位发言人塞进同一条" in conv, "")
    check("对话记录：[共识与分歧] 补尺寸（约 150–300 字）与理由",
          "约 150–300 字" in conv and "各方立场与理由" in conv, "")
    check("对话记录：[共识与分歧] 改为判断层（一致性/分歧性质/倾向与依据）",
          "由事实得出的判断" in conv and "分歧的性质" in conv and "本场的倾向与依据" in conv, "")
    check("对话记录：[共识与分歧] 禁止复述各人事实（明细归 [交流内容]）",
          "不要复述各人分别带什么、认为什么（事实明细归 [交流内容]）" in conv, "")
    check("对话记录：[对话概况] 场合关系只取原文明示，不推断",
          "只写原文明示的角色或关系" in conv and "原文没有身份线索就不补关系、不作推断" in conv
          and "为什么聊起这个话题、话题走向" in conv, "")
    check("对话记录：[对话概况] 差异对照 + 数字/事例 + 不逐条复述",
          "倾向与差异对照" in conv and "值得记的数字或具体事例" in conv
          and "不逐条复述各方发言（明细归 [交流内容]，原话归 [关键原话]）" in conv, "")
    check("小组讨论：[讨论议题与背景] ④ 降级为点题、明细归 [共识形成]（治六成以上重复）",
          "一致与分歧的明细归 [共识形成]，本栏不复述" in semi, "")
    check("小组讨论：[讨论议题与背景] 新增「为什么现在讨论这个」与「讨论怎么推进的」",
          "为什么现在讨论这个" in semi and "讨论怎么推进的" in semi, "")
    check("小组讨论：[共识形成] 扩为双侧（一致意见 + 倾向性认识/主要分歧）",
          "一致意见或产出" in semi and "谁与谁不一致、分歧在哪" in semi
          and "没有统一意见时写本场达成的倾向性认识与主要分歧点" in semi, "")
    check("小组讨论：[共识形成] 补尺寸（约 150–300 字）", "约 150–300 字" in semi, "")
    check("小组讨论：[发言要点] 要求数字/案例落地",
          "具体数字、次数、案例、时间要落进对应条目" in semi, "")
    check("小组讨论：[发言要点] 交锋写实（谁反对、理由与依据）",
          "交锋要写实" in semi and "谁主张什么、谁反对、反对的理由或依据是什么" in semi, "")
    check("小组讨论：交锋按条展开（多条各占一条），合并只限同一次发言",
          "同一议题下的多条交锋各占一条" in semi and "只有同一次发言的碎片才合并" in semi
          and "；同一议题的碎片合并成一条" not in semi, "")
    check("小组讨论：末栏口径写清（搁置/没聊透也算）但不编造分工",
          "没聊透或明确说下次继续的话题都算" in semi and "不要编造分工" in semi, "")
    for name, text in (("对话记录", conv), ("小组讨论", semi)):
        check(f"{name}：旧体例（裸概括首栏）已替换",
              "场景及整体脉络（谈了哪几个话题、以什么为主）" not in text
              and "核心探讨问题（列出谈到的议题范围）" not in text, "")


def test_qa_precision_rules() -> None:
    """问答栏只收真问答（治"陈述句当提问"）：判据写在共用形态规则里，模板侧只留专用口径。

    回归背景（2026-09 now.xlsx）：新闻发布两场对比——提问形式清晰的那场 7 条问句全部合格；
    提问是间接表述的那场 3 条全部写成「主持人周琦提问，…？」这种引导式转述（既不是原文问句、
    也不是纯疑问句），答话还有 230 字的讲稿式搬运。五个问答模板此前都没有"什么算问答"的判据。
    """
    from tools.template_router._placeholder import plan_placeholder_fill
    from tools.templates.body_rules import BODY_FORMAT_RULES

    for need in (
        "问答栏只收真问答",
        "自问自答与讲解式设问",
        "不得写成「XX提问，…？」式引导转述",
        "答话只写回应要点",
        "模板未指定上限时，答话超过约 300 字压到 300 字以内",
        "答话只写回应要点并保持单段，不拆段、不使用列表",
        "压缩只删例子与铺垫",
        "原文没有正式问答就写「未提及」",
    ):
        check(f"共用形态规则含问答精度口径：{need}", need in BODY_FORMAT_RULES, "")
    check("段落上限规则为问答轮次开了例外（再长也不拆段、长答话按要点压缩）",
          "问答/对话的一轮" in BODY_FORMAT_RULES and "再长也不拆段" in BODY_FORMAT_RULES
          and "长答话按要点压缩" in BODY_FORMAT_RULES, "")

    qa_templates = ("media_briefing", "media_qa_session", "admission_briefing", "special_lecture", "class_transcript")
    retired = ("覆盖所有重要提问", "答话可归并但不得改口径", "内容相似的合并成一条")
    from tools.templates.template_eval import parse_section_char_budgets

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
        # 问答长度口径：4 个模板保留可解析的 400/段提示；
        # 课堂答疑（2026-09-18 用户口径）改为**按重要程度收**，全栏不带任何字数门禁
        para = [b for b in parse_section_char_budgets(text) if b.get("scope") == "paragraph"]
        if stem == "class_transcript":
            check("class_transcript：问答栏不带字数门禁（不会触发压缩/返工）",
                  not para, f"{para}")
            check("class_transcript：按重要程度收（读完知识点仍会问 / 澄清纠正限定 / 无损失不收）",
                  all(k in text for k in (
                      "只收「看完知识点栏之后仍会问」的问答",
                      "复述已讲内容的不收",
                      "发生了澄清、纠正或限定的才收",
                      "去掉它对理解有没有损失",
                  )), "")
            check("class_transcript：按知识点配平 + 同题只留一组（数量由内容决定）",
                  "按知识点配平" in text and "同一问题只留信息最全的一组" in text
                  and "最多 8 组" not in text, "")
            check("class_transcript：保留条级字数（问 20–50 / 答 40–150）",
                  "每条 20–50 字" in text and "每条 40–150 字" in text, "")
            check("class_transcript：答话写在同一段里（不分段、不分点）",
                  "写在同一段里" in text and "不分段、不分点" in text, "")
        else:
            check(f"{stem}：问答栏保留可解析的长度口径（400/段，作提示）",
                  any(int(b["hi"]) == 400 for b in para), f"{para}")
            check(f"{stem}：问答栏写明答话可压缩、仍按单段连着写（不拆段）",
                  "答话可压缩、不必逐句照抄" in text and "仍**单段**连着写" in text
                  and "答话超过约 400 字必须分点" not in text, "")

    # 一问一答各占一段：称呼行（对话轮次）不参与段落拆分，普通散文段照旧会被拆
    from tools.execution.hard_execution import split_overlong_paragraphs

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


def test_project_progress_overview() -> None:
    """项目进度会 [项目概况]：删掉不可校验的句数口径，换成可解析的字数区间 + 可执行边界。

    回归背景（2026-09 now.xlsx）：该栏同时挂着"只写 3–6 句"（无程序检查、且句数不是篇幅指标）
    与"每段不超过 400 字"（可解析、超 480 会拆行）——模型只认后者，写成了 6 段 1317 汉字
    （27 句），且与 [进度追踪] 表格的 4-gram 重合 26%（复述明细）。
    """
    text = (_active_dir() / "project_progress.md").read_text(encoding="utf-8")
    specs = [l.strip() for l in text.splitlines() if l.strip().startswith("[") and l.strip().endswith("]")]
    overview = next((s for s in specs if "一段话概览" in s), "")
    check("项目进度会：概况栏改为可解析的字数区间（一段写完，约 250–400 字）",
          "一段写完，约 250–400 字" in overview, f"{overview[:60]}")
    check("项目进度会：旧的句数口径已删除（3–6 句不再出现）",
          "3–6 句" not in text and "句概览" not in text, "")
    check("项目进度会：边界写成可执行的「只写进某两栏 + 本栏不复述」",
          "只写进 [进度追踪] / [风险预警] / [后续计划] 三栏" in overview
          and "本栏不复述" in overview, "")
    # [后续计划] 原来是全模板唯一没有格式要求的栏（其余两栏走表、概况走一段话）→ 实测 4 份
    # 产物里 3 份写成 221–242 汉字的单段、零分点，而源里明明有 6–8 件后续事项。
    plan = next((s for s in specs if "按事项分点写" in s), "")
    check("项目进度会：[后续计划] 要求按事项分点（一条一件事、一条一行）",
          "按事项分点写" in plan and "一条一件事、一条一行" in plan
          and "`- **事项**：做什么 + 责任方 + 时间节点`" in plan, f"{plan[:80]}")
    check("项目进度会：[后续计划] 给分组与条级尺寸（每组 2–5 条 / 每条 40–120 字）",
          "每组 2–5 条" in plan and "每条 40–120 字" in plan
          and "不写与栏名同名的标题" in plan, "")
    check("项目进度会：[后续计划] 保留交付物/依赖提示与套话禁令",
          "核心交付物用 **具体内容** 强调" in plan
          and "依赖前提用 *具体内容* 提示" in plan
          and "无对象的套话" in plan, "")
    check("项目进度会：[后续计划] 旧口径（要素清单式叙述）已清除",
          "从概况与原文提取下一步" not in plan and "验收标准、关键时间节点" not in text, "")
    from tools.templates.template_eval import parse_section_char_budgets

    caps = [b for b in parse_section_char_budgets(text) if b["title"] == "项目概况"]
    check("项目进度会：概况栏预算为节级 250–400（首栏只写一段）",
          bool(caps) and caps[0]["hi"] == 400 and caps[0]["scope"] == "section", f"{caps}")


def test_paragraph_cap_from_explicit_per_para() -> None:
    """单段字数上限以「单段/每段」旁边的数字为准；节级预算的栏也要兜单段。

    回归背景（2026-09-18）：[访谈概述] 只写「约 250–400 字」，解析成**节级**预算 →
    拆段函数（只吃段落级）跳过它，实测 418 字单段静默不拆、517 字只有一条软提示。
    修法：① 栏说明补「单段不超过 300 字」；② 「单段/每段」旁的数成为段落上限
    （区间会盖过它）；③ 节级预算的栏，单段超过整节上限也拆。
    """
    from tools.execution.hard_execution import split_overlong_paragraphs
    from tools.templates.template_eval import parse_section_char_budgets

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
    gm = (_active_dir() / "general_minutes.md").read_text(encoding="utf-8")
    gcaps = [b for b in parse_section_char_budgets(gm) if b["title"] == "分段速览"]
    # 2026-09-20：速览改成「标题 + 一句主线」后不再声明字数 → 该栏不产生段落上限
    check("通用纪要：速览不再有字数预算（改为一句话口径）",
          not gcaps, f"{gcaps}")
    spec_seg = next(l.strip() for l in gm.splitlines() if "推进顺序" in l)
    check("通用纪要：速览改为一句话主线、明细归 [要点梳理]（治炸主判据）",
          "只写一句主线" in spec_seg and "每段至少一句" in spec_seg
          and "具体条目、数字与分工归 [要点梳理]" in spec_seg
          and "不重复 [要点梳理] 已列的条目与数字" in spec_seg,
          spec_seg[:80])
    para_sub = "这是一段概览文字。" * 55  # ≈440 汉字，单段
    for label, doc in (
        ("无子标题", "# 通用纪要\n\n# 分段速览\n" + para_sub + "\n"),
        ("带 ## 时间段", "# 通用纪要\n\n# 分段速览\n## 08:00-12:30 现场检查\n" + para_sub + "\n"),
    ):
        fixed, notes = split_overlong_paragraphs(doc, gm)
        seg_count = len([q for q in fixed.split("\n\n") if "概览文字" in q])
        check(f"通用纪要：速览无上限 → 440 字单段不被程序拆（{label}）",
              not notes and seg_count == 1,
              f"段数={seg_count} {notes}")

    # ③ 声明只作用于本栏：同一文档里其它栏（全文摘要）仍按节级上限拆
    doc4 = (
        "# 通用纪要\n\n# 全文摘要\n" + para_sub
        + "\n\n# 分段速览\n## 08:00-12:30 现场检查\n" + para_sub + "\n"
    )
    fixed4, notes4 = split_overlong_paragraphs(doc4, gm)
    abs_part = fixed4.split("# 全文摘要", 1)[1].split("# 分段速览", 1)[0]
    check("通用纪要：取消上限只作用于速览栏（摘要仍折叠拆段）",
          any("全文摘要" in n for n in notes4)
          and len([q for q in abs_part.split("\n\n") if "概览文字" in q]) >= 2,
          f"{notes4}")

    # ③ 单句超长（句界拆不动）→ 仍必须报「超出段落字数上限」，不能静默
    from tools.execution.hard_execution import _overlong_issue

    one = "这是一句没有任何句号的超长段落" + "持续延伸内容" * 80 + "。"
    doc3 = "# 通用纪要\n\n# 全文摘要\n" + one + "\n"
    over = _overlong_issue(gm, doc3) or ""
    check("通用纪要：摘要栏单句超长仍报超限（不再静默）",
          "超出段落字数上限" in over and "全文摘要" in over, over[:80])


def test_strip_default_only_content() -> None:
    """只有缺省词的内容不展示：表格整行 / 正文整条 / 独立缺省句；整栏缺省则保留一行。

    回归背景（2026-09-18 用户实测）：就医咨询的药表出现整行「未明确」（模板声明的缺省词是
    「未明确」而 `_row_nonempty` 的空集里没有它）→ 被当数据行原样展示；同期还有 3 条
    `- **过敏史**：未提及。` 与 4 处"整栏只有未提及"。用户口径：这类内容不展示，
    但"整栏都没有"要保留一行缺省词（"没有"本身是信息）。
    """
    from tools.execution.hard_execution import (
        _item_default_only,
        _row_nonempty,
        apply_table_row_limits,
        enforce_render_output,
        gate_render_output,
        strip_default_only_content,
    )

    check("全缺省表行判为空（含模板缺省词「未明确」）",
          not _row_nonempty("| 未明确 | 未明确 | 未明确 | 未明确 | 未明确 |"), "")
    check("全未提及表行判为空", not _row_nonempty("| 未提及 | — | — | — | — |"), "")
    check("有内容的表行不算空", _row_nonempty("| 奥美拉唑 | 未明确 | 口服 | 未明确 | 效果不佳 |"), "")
    check("整条只有缺省词（`- **X**：未提及。`）被识别",
          _item_default_only("- **过敏史**：未提及。") and _item_default_only("- **个人史**：未提及"), "")
    check("有内容的条目不算缺省", not _item_default_only("- **现病史**：2023年9月确诊。"), "")

    doc = (
        "# 就医咨询\n\n# 就诊概况\n- **现病史**：2023年9月确诊。\n"
        "- **过敏史**：未提及。\n- **家族史**：未提及。\n\n"
        "# 治疗方案与医嘱\n- **检查安排**：建议做第二次基因检测。\n"
        "- **用药**：系统治疗包括化疗、靶向、免疫。\n\n"
        "| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |\n| --- | --- | --- | --- | --- |\n"
        "| 未明确 | 未明确 | 未明确 | 未明确 | 未明确 |\n\n"
        "# 复诊与预警信号\n未提及。\n"
    )
    out, notes = strip_default_only_content(doc)
    check("整条缺省被删、有内容的条目保留",
          "- **过敏史**" not in out and "- **现病史**" in out and "- **检查安排**" in out, "")
    check("整表全缺省 → 保留首行缺省数据行（不再把表删空）",
          "| 未明确 | 未明确 | 未明确 | 未明确 | 未明确 |" in out and "| 药品名称 |" in out, "")
    check("整节只有缺省词 → 保留标题 + 一行缺省词",
          "# 复诊与预警信号\n未提及" in out, "")
    check("删除有记录（notes 记数）", bool(notes) and "已省略" in notes[0], f"{notes}")

    raw = (_active_dir() / "clinical_advisory.md").read_text(encoding="utf-8")
    gate = gate_render_output(raw, out)
    # 2026-09-19 起反转：整表缺省是**合法形态**（原文本就没有药品明细），保留首行缺省数据行后
    # 不再报「表格无有效数据行」。旧口径让这条硬伤无法修复（源里没有数据可填），
    # 实测 就医咨询 单次渲染 10 次 LLM 调用、整单 115.8s 后仍降级。
    check("整表缺省不再产生「表格无有效数据行」硬伤",
          "表格无有效数据行" not in gate["issues"] and not gate["hard_issues"],
          f"hard={gate['hard_issues']} issues={gate['issues']}")

    blank = (
        "# 就医咨询\n\n# 治疗方案与医嘱\n- **全身系统治疗**：核心是全身系统治疗。\n"
        "| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |\n| --- | --- | --- | --- | --- |\n"
    )
    fixed_t, notes_t, issues_t = enforce_render_output(raw, blank)
    check("空表全流程：写入缺省占位行且零硬伤（原文本就没有药品明细时的出口）",
          not issues_t and "| 未提及 | — | — | — | — |" in fixed_t, f"{issues_t} {notes_t}")
    glued, n_glued = apply_table_row_limits(blank.rstrip("\n"), raw)
    check("表格在文末且无末尾换行时，占位行也独立成行（不粘连分隔行）",
          "| 未提及 | — | — | — | — |" in glued.splitlines(), f"{n_glued} {glued.splitlines()[-1]!r}")

    for stem, bad in (
        ("clinical_advisory", "一律写「未明确」"),
        ("decision_review", "缺项直接写「未明确」"),
        ("project_progress", "缺项直接写「无」"),
        ("contract_vetting", "缺则写「无」"),
    ):
        txt = (_active_dir() / f"{stem}.md").read_text(encoding="utf-8")
        check(f"{stem}：不再要求逐项标缺省词", bad not in txt, "")
    pl = (_active_dir() / "product_launch.md").read_text(encoding="utf-8")
    check("产品发布：缺项不写、整栏才合并成一句",
          "整栏都没有内容时才把缺项**合并成一句**" in pl, "")


def test_enum_normalize_fallback() -> None:
    """形态标签枚举容错：非法值归一到「通用」，不抛错、不触发重试。

    回归背景（2026-09-18 15:24 实测）：理解层 scene 只有 7 个粗粒度形态标签，而真实场景有
    二十多种（产品发布/新闻发布/课堂/讲座/就医…）→ 模型对"海尔洗衣机发布会"填了「产品发布」
    → `_choice` 抛错 → 客户端重试一轮（in 6335→7451、+12s，两次返回内容一字不变）。
    """
    from dataclasses import fields as dc_fields

    from tools.schema.validation import _choice_or_default

    check("_choice_or_default：合法值原样返回",
          _choice_or_default("专项讨论会", {"通用", "专项讨论会"}, "scene", "通用") == "专项讨论会", "")
    check("_choice_or_default：非法值归一到 default",
          _choice_or_default("产品发布", {"通用", "专项讨论会"}, "scene", "通用") == "通用", "")

    # 生成契约确实用了归一路径（而不是 _choice）
    gen = Path("domain/meeting/models_generated.py").read_text(encoding="utf-8")
    check("生成契约：scene 走 _choice_or_default（不再抛错重试）",
          'data["scene"] = _choice_or_default(' in gen and "_choice_or_default," in gen, "")

    # 运行期：非法 scene 被归一，不再异常
    from domain.meeting.models_generated import MeetingUnderstanding

    payload: dict = {}
    for f in dc_fields(MeetingUnderstanding):
        payload[f.name] = "x"
    payload["scene"] = "产品发布"
    for f in dc_fields(MeetingUnderstanding):
        if f.name == "scene":
            continue
        ann = str(f.type)
        if "list" in ann:
            payload[f.name] = []
    inst = MeetingUnderstanding.validate(dict(payload))
    check("理解层：非法场景「产品发布」→ 归一为「通用」（不抛错）", inst.scene == "通用", f"{inst.scene}")

    # 理解 prompt 把话说死
    from domain.meeting.meeting_core import prompts as core_prompts

    text = "\n".join(
        str(getattr(core_prompts, name))
        for name in dir(core_prompts)
        if name.isupper() and isinstance(getattr(core_prompts, name), str)
    )
    check("理解 prompt：写明 scene 只能取这 7 个值", "只能填这 7 个值之一" in text, "")
    check("理解 prompt：给出发布会类映射与禁止自造类别名",
          "对外发布会、宣讲、路演类填「专项讨论会」" in text and "不要自造类别名" in text, "")


def test_scene_hint_from_template() -> None:
    """打通"调用方模板"与"理解层形态标签"：程序按模板映射 7 类形态，模型自选只作兜底。

    回归背景（2026-09-18 15:24 实测）：理解层 scene 只有 7 类，模型对产品发布会填「产品发布」
    → 校验失败白跑一轮；归一后只能落到「通用」骨架（启发式词表里没有"发布/宣讲/路演"）。
    """
    from domain.meeting.scene_hint import (
        TEMPLATE_SCENE_HINTS,
        scene_hint_for_template,
        scene_hint_for_templates,
    )
    from domain.meeting.tasks.minutes_trace.scene import GENERIC_SCENE, SCENE_LABELS

    allowed = set(SCENE_LABELS) | {GENERIC_SCENE}
    check("映射表的标签都在 7 类形态内",
          all(v in allowed for v in TEMPLATE_SCENE_HINTS.values()),
          f"{[v for v in TEMPLATE_SCENE_HINTS.values() if v not in allowed]}")

    # 覆盖率：模板目录里每个模板的中文名都必须登记（新增模板忘登记会静默回退「通用」）
    missing = []
    for md in sorted(_active_dir().glob("*.md")):
        if md.stem.lower() == "readme":
            continue
        name = ""
        for line in md.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("# ") and not s[2:].strip().startswith("["):
                name = s[2:].strip()
                break
        if name not in TEMPLATE_SCENE_HINTS:
            missing.append(md.stem)
    check("映射表覆盖全部模板（新增模板必须登记）", not missing, f"未登记={missing}")

    pl = (_active_dir() / "product_launch.md").read_text(encoding="utf-8")
    tm = (_active_dir() / "team_meeting.md").read_text(encoding="utf-8")
    check("产品发布模板 → 「专项讨论会」（不再落到通用骨架）",
          scene_hint_for_template(pl) == "专项讨论会", scene_hint_for_template(pl))
    check("团队例会模板 → 「团队例会」", scene_hint_for_template(tm) == "团队例会", "")
    check("未知模板 → 空串（调用方回退到模型自选）",
          scene_hint_for_template("# 某新模板\n[说明]") == "", "")
    check("空模板 → 空串（不写死通用）", scene_hint_for_template("") == "", "")
    check("多线请求：优先 minutes 线模板",
          scene_hint_for_templates({"minutes": pl, "trace": tm}) == "专项讨论会", "")
    check("多线请求：无 minutes 时取第一条非空模板",
          scene_hint_for_templates({"trace": "", "actions": tm}) == "团队例会", "")

    # 理解节点确实用程序映射覆盖模型自选值
    src = Path("domain/meeting/orchestrator.py").read_text(encoding="utf-8")
    check("理解节点：用模板映射覆盖 scene（程序优先、模型兜底）",
          "scene_hint_for_templates(state.get(\"templates\"))" in src
          and 'data["scene"] = hint' in src, "")


def test_allow_missing_on_trimmed_fields() -> None:
    """单线裁剪字段允许缺键：模型把"输出 []"理解成"键不用写"时不再白跑一轮重试。

    回归背景（2026-09-18 15:51 实测）：单线 minutes 会裁剪 risk_hints，裁剪指令写的是
    "输出空数组 []"，但模型常把整个键省掉 → 契约要求字段集合完全一致 →
    `结构化校验失败` → 针对性重试一次（+20s，第二次才把键补上）。
    """
    import json
    from dataclasses import fields as dc_fields

    from client.llmclient import LLMClient
    from domain.meeting.meeting_core.meeting_understanding_agent import (
        _trim_instruction,
    )
    from domain.meeting.models_generated import MeetingUnderstanding

    base = {
        f.name: ("一段话" if "list" not in str(f.type) else [])
        for f in dc_fields(MeetingUnderstanding)
    }
    base["scene"] = "通用"
    trimmed = {k: v for k, v in base.items() if k != "risk_hints"}

    out = LLMClient._parse_and_validate(
        json.dumps(trimmed), MeetingUnderstanding, frozenset({"risk_hints"})
    )
    check("裁剪字段缺键时补默认 []（不再抛错重试）", out.risk_hints == [], f"{out.risk_hints}")
    try:
        LLMClient._parse_and_validate(json.dumps(trimmed), MeetingUnderstanding)
        failed = False
    except Exception:  # noqa: BLE001
        failed = True
    check("未声明 allow_missing 时缺键仍严格报错（不放松其它字段）", failed, "")
    unkept = {k: v for k, v in base.items() if k != "topics"}
    try:
        LLMClient._parse_and_validate(
            json.dumps(unkept), MeetingUnderstanding, frozenset({"risk_hints"})
        )
        failed2 = False
    except Exception:  # noqa: BLE001
        failed2 = True
    check("非裁剪字段缺键仍报错（只在裁剪集合内放宽）", failed2, "")

    trim = _trim_instruction("minutes", ("risk_hints",))
    check("裁剪指令写明「键名必须保留、值给空数组 []」",
          "键名必须保留" in trim and "不要省略键名" in trim, trim[:80])

    src = Path("domain/meeting/meeting_core/meeting_understanding_agent.py").read_text(encoding="utf-8")
    check("理解 agent：把裁剪集合 + speakers 传给 allow_missing",
          "allow_missing=missable" in src and 'missable = skipped | {"speakers"}' in src, "")


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


def test_understanding_skip_never_retries() -> None:
    """每条线的理解裁剪字段都允许缺键：模型省略被裁剪字段时不再白跑重试。

    回归背景（2026-09-18）：单线跑 minutes 会裁剪 risk_hints，模型把"输出空数组 []"理解成
    "整个键不用写" → 契约要求字段集合完全一致 → 校验失败 → 针对性重试一次（+20s）。
    用户实测在 讲座概况、对话概况 等场景都出现——**同一处路径**（理解阶段按线裁剪，
    与模板无关），所以修的是线级机制，30 个模板一起覆盖。
    """
    import asyncio
    import json
    from dataclasses import fields as dc_fields

    from client.llmclient import LLMClient
    from domain.meeting.meeting_core.meeting_understanding_agent import (
        MeetingUnderstandingAgent,
    )
    from domain.meeting.models_generated import MeetingUnderstanding
    from domain.meeting.orchestrator import UNDERSTANDING_SKIP_FIELDS

    class _FakeUnderstandingClient:
        """只回一份"省略了裁剪字段"的 JSON；按 structured 的 allow_missing 语义校验。"""

        def __init__(self, skip: set[str]) -> None:
            self.skip = set(skip)
            self.calls = 0

        async def structured(self, system, user, model, contract, *, label="", allow_missing=(), **kw):
            self.calls += 1
            payload = {
                f.name: ("一段话" if "list" not in str(f.type) else [])
                for f in dc_fields(model)
            }
            payload["scene"] = "通用"
            for key in self.skip:  # 模拟模型把被裁剪字段的键整个省掉
                payload.pop(key, None)
            return LLMClient._parse_and_validate(
                json.dumps(payload), model, frozenset(allow_missing)
            )

    list_fields = {
        f.name for f in dc_fields(MeetingUnderstanding) if "list" in str(f.type)
    }
    for line, skip in UNDERSTANDING_SKIP_FIELDS.items():
        fake = _FakeUnderstandingClient(set(skip))
        agent = MeetingUnderstandingAgent(fake)  # type: ignore[arg-type]
        out = asyncio.run(agent.run("会议原文：略。", focus_line=line, skip_fields=skip))
        blanks = [k for k in skip if k in list_fields]
        check(f"裁剪字段缺键不报错、一次调用成功（{line} 线：{sorted(skip)}）",
              all(getattr(out, k) == [] for k in blanks) and fake.calls == 1,
              f"calls={fake.calls}")
    check("裁剪集合覆盖 minutes/actions/risks 三条线",
          set(UNDERSTANDING_SKIP_FIELDS) == {"minutes", "actions", "risks"}, "")

    src = Path("domain/meeting/meeting_core/meeting_understanding_agent.py").read_text(encoding="utf-8")
    check("理解 agent：同一裁剪集合既写进指令也传给 allow_missing（speakers 常空、缺键不算错）",
          "allow_missing=missable" in src and "键名必须保留" in src
          and 'missable = skipped | {"speakers"}' in src, "")
    node_src = Path("domain/meeting/orchestrator.py").read_text(encoding="utf-8")
    check("理解裁剪按选线 + 模板栏位（发布会类不抽用不到的字段）",
          "skip_fields_for_template(template)" in node_src
          and "skip_fields=skip" in node_src, "")


def test_template_aware_understanding_skip() -> None:
    """minutes 单线：理解层再按**模板栏位**裁一次（模板没有风险/未决栏就不抽）。

    回归背景（2026-09-18 耗时复盘）：minutes 的 pack 只取
    brief/purpose/scene/topics/decisions/risks/open_questions——
    action_hints / risk_hints / dependencies 这条线从不消费；risks / open_questions 也只
    在模板真有风险/未决栏时才进正文。而理解层输出是整条链最贵的中间件：它要进草稿、审核、
    装配每一次调用的上下文（实测一篇 6000 字发布会实录抽了 6.2k token / 1.3 万字符）。
    发布会四栏、讲座四栏、课堂四栏、访谈三栏都用不到这两栏，属于纯浪费。
    """
    from domain.meeting.orchestrator import UNDERSTANDING_SKIP_FIELDS, _Nodes
    from domain.meeting.understanding_skip import skip_fields_for_template

    base = set(UNDERSTANDING_SKIP_FIELDS["minutes"])
    check("minutes 基础裁剪带走 action_hints/risk_hints/dependencies",
          {"action_hints", "risk_hints", "dependencies"} <= base, f"{sorted(base)}")

    d = _active_dir()

    def load(name: str) -> str:
        return (d / f"{name}.md").read_text(encoding="utf-8")

    both = frozenset({"risks", "open_questions"})
    mb = load("media_briefing")
    check("新闻发布：无风险/未决栏 → 再跳 risks/open_questions",
          skip_fields_for_template(mb) == both, f"{sorted(skip_fields_for_template(mb))}")
    check("通用纪要：[要点梳理] 含「待确认与风险」→ 一个都不跳",
          skip_fields_for_template(load("general_minutes")) == frozenset(),
          f"{sorted(skip_fields_for_template(load('general_minutes')))}")
    check("团队例会：协作需求提到阻塞 → risks 保留",
          "risks" not in skip_fields_for_template(load("team_meeting")), "")
    check("项目进度：有「风险预警」栏 → risks 保留（open_questions 无落点仍可跳）",
          "risks" not in skip_fields_for_template(load("project_progress")),
          f"{sorted(skip_fields_for_template(load('project_progress')))}")
    check("讲座/访谈/课堂/产品发布：四类都用不到风险与未决 → 全跳",
          all(
              skip_fields_for_template(load(n)) == both
              for n in (
                  "special_lecture",
                  "interview_transcript",
                  "class_transcript",
                  "product_launch",
                  "media_qa_session",
                  "admission_briefing",
              )
          ),
          "",
      )
    check("空模板 → 不裁（宁多不漏）", skip_fields_for_template("") == frozenset(), "")

    # 覆盖率守卫：29 个模板都要得出结论，且只可能跳这两个字段
    allowed = {"risks", "open_questions"}
    out_of_range: list[tuple[str, list[str]]] = []
    trimmed: list[str] = []
    for md in sorted(d.glob("*.md")):
        if md.stem.lower() == "readme":
            continue
        got = skip_fields_for_template(md.read_text(encoding="utf-8"))
        if not got <= allowed:
            out_of_range.append((md.stem, sorted(got)))
        if got == both:
            trimmed.append(md.stem)
    check("每个模板的裁剪结论都落在允许集合内", not out_of_range, f"{out_of_range}")
    check("至少 10 个模板（发布会/讲座/课堂/访谈类）拿到两栏裁剪",
          len(trimmed) >= 10, f"仅 {len(trimmed)} 个：{trimmed}")

    # 节点侧合并：单线 minutes + 模板 → 五项；多线/无模板不裁
    merged = frozenset(base | both)

    def skip_of(names: list[str], tpl: str = "") -> frozenset[str]:
        return _Nodes._understanding_skip(object(), names, tpl)

    check("单线 minutes + 新闻发布模板 → 五项一起跳",
          skip_of(["minutes"], mb) == merged, f"{sorted(skip_of(['minutes'], mb))}")
    check("多线请求不裁（理解还要服务待办/风险线）",
          skip_of(["minutes", "actions"], mb) == frozenset(), "")
    check("未给模板的单线 minutes → 只跳基础三项",
          skip_of(["minutes"]) == frozenset(base), f"{sorted(skip_of(['minutes']))}")
    check("其它线不受模板影响（actions 线模板不给也不改集合）",
          skip_of(["actions"], mb) == UNDERSTANDING_SKIP_FIELDS["actions"], "")

    from domain.meeting.meeting_core.meeting_understanding_agent import (
        _trim_instruction,
    )

    trim = _trim_instruction("minutes", sorted(merged))
    check("裁剪指令把五项都列进「值给空数组 []」",
          "键名必须保留" in trim and all(k in trim for k in merged), trim[:120])
    check("裁剪指令的「必须照常输出」名单里不含被裁字段",
          all(k not in trim.split("其余字段")[1].split("必须照常")[0] for k in merged), "")

    # 节点侧：裁剪集合确实随 state 里的模板变化（不是建节点时定死）
    import asyncio

    class _FakeAgent:
        def __init__(self) -> None:
            self.seen: list[tuple[str, frozenset[str]]] = []

        async def run(self, transcript, *, focus_line="", skip_fields=()):
            self.seen.append((focus_line, frozenset(skip_fields)))

            class _Out:
                @staticmethod
                def model_dump() -> dict:
                    return {"scene": "通用"}

            return _Out()

    fake = _FakeAgent()

    class _Host(_Nodes):
        """只借 _Nodes 的方法与状态读取；不跑父类 __init__（不建 LLM 客户端）。"""

        def __init__(self, agent) -> None:
            self.meeting_understanding_agent = agent

    host = _Host(fake)
    node = _Nodes._make_meeting_understanding_node(host, ["minutes"])
    asyncio.run(node({"transcript": "原文略。", "templates": {"minutes": mb}}))
    asyncio.run(
        node(
            {
                "transcript": "原文略。",
                "templates": {"minutes": load("general_minutes")},
            }
        )
    )
    asyncio.run(node({"transcript": "原文略。"}))
    check("节点按 state 模板定裁剪：新闻发布五项 / 通用纪要三项 / 无模板三项",
          [frozenset(s) for _, s in fake.seen] == [merged, frozenset(base), frozenset(base)],
          f"{[(f, sorted(s)) for f, s in fake.seen]}")
    check("节点只在裁剪非空时报线名（无裁剪则不给 focus）",
          [f for f, _ in fake.seen] == ["minutes", "minutes", "minutes"], "")


def test_long_generation_output_cap() -> None:
    """长生成调用必须有输出上限：本地端点没有隐含上限，一次退化 = 49k token / 9 分钟。

    回归背景（2026-09-18 实测）：装配退化成"写不完"——49,074 token / 86,447 字符 / 551 秒，
    被 max_tokens 截断后 JSON 不可解析 → 四栏全空 → 整篇重填，一条纪要跑满 10 分钟。
    """
    from tools.templates.length_budget import (
        OUTPUT_CAP_MAX,
        OUTPUT_CAP_MIN,
        effective_doc_budget,
        output_token_cap,
        target_han,
    )

    check("原文过短（<300 汉字）不给档位预算", effective_doc_budget(200) is None, "")
    check("8k–20k 档：预算 1680–5500",
          effective_doc_budget(12000) == (1680, 5500), f"{effective_doc_budget(12000)}")
    check("模板声明优先于档位（当前 30 个模板都没声明 → 全走档位）",
          effective_doc_budget(12000, "# [栏]\n[说明]") == (1680, 5500), "")
    caps = [output_token_cap(h) for h in (200, 12000, 60000)]
    check("输出上限随原文规模递增且夹在 1200–12000",
          OUTPUT_CAP_MIN <= caps[0] <= caps[1] <= caps[2] <= OUTPUT_CAP_MAX, f"{caps}")
    check("失控量级：8k–20k 原文 → 6600 token（本地约 1 分钟，原来 49k/9 分钟）",
          output_token_cap(12000) == 6600, f"{output_token_cap(12000)}")
    check("无预算的短原文给中性目标 4000", target_han(None, "") == 4000, "")

    # 模板说明里的「短语 20 字内」曾被解析成 hi=20 的小节上限（讲座 [核心观点与论证]，
    # 2026-09-19 实测）：每跑一次都报软提示，且该栏一旦出现散文段会被切成 20 字碎块。
    # 这里钉住"不存在可疑的小节预算"（正常栏级尺寸都在 80 字以上），防止同类写法再犯。
    from tools.templates.template_eval import parse_section_char_budgets as _psb

    suspicious = []
    for md in sorted(_active_dir().glob("*.md")):
        for b in _psb(md.read_text(encoding="utf-8")):
            if (b.get("hi") or 10**9) < 80:
                suspicious.append((md.stem, b["title"], b["hi"]))
    check("没有 <80 字的「可疑小节预算」（数字+字 的说明性写法已清除）",
          not suspicious, f"{suspicious}")

    placeholder_src = Path("tools/template_router/_placeholder.py").read_text(encoding="utf-8")
    check("装配：max_tokens 来自目标字数换算并写进两个路径",
          "max_tokens=cap" in placeholder_src
          and "output_token_cap(source_han, template)" in placeholder_src, "")
    render_src = Path("tools/runtime/render.py").read_text(encoding="utf-8")
    check("渲染/压缩/展开/返工四处都经 _render_run 带上限",
          render_src.count("_render_run(") >= 5
          and "source_han=_doc_han(state)" in render_src, "")
    # 装配路径的下限兑现（2026-09-19 实测：55 次运行全走 assemble，"低于下限" 6 次静默通过）
    check("装配路径补一轮「低于下限 15% → 扩写」（无硬伤且更长才采用）",
          'fill_mode == "assemble"' in render_src
          and "assemble too short" in render_src
          and "han < int(lo_i * 0.85)" in render_src
          and "_EXPAND_REVISION.format(han=han, lo=lo_i, hi=hi_i)" in render_src, "")
    minutes_src = Path(
        "domain/meeting/tasks/minutes/steps/minutes_render.py"
    ).read_text(encoding="utf-8")
    check("纪要渲染步接受并透传 max_tokens",
          "max_tokens=max_tokens" in minutes_src and "max_tokens: int | None = None" in minutes_src, "")
    budget_src = Path("tools/templates/length_budget.py").read_text(encoding="utf-8")
    check("【篇幅预算】写明超上限会被截断", "超过上限的输出会被截断" in budget_src, "")


def test_column_fill_concurrency_and_early_stop() -> None:
    """逐栏填充：一栏一次调用、栏间并发、失败只重试该栏；退化（重复/超长）流式早停。

    回归背景（2026-09-18 实测）：整篇 JSON 装配退化时写出 49,074 token / 86,447 字符，
    551 秒后才被 max_tokens 截断，JSON 不可解析 → 四栏全空 → 整篇重填。逐栏后爆炸半径
    只有一栏，流式下发现重复/超长立刻放弃，只重试那一栏。
    """
    import asyncio
    import re as _re

    from tools.template_router._placeholder import (
        _degenerate_reason,
        fill_placeholder_by_columns,
        plan_placeholder_fill,
    )

    mb = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    plan = plan_placeholder_fill(mb)
    check("新闻发布：4 个标量栏、无表格（走逐栏路径）",
          len(plan["scalars"]) == 4 and not plan["row_templates"],
          f"{len(plan['scalars'])}/{len(plan['row_templates'])}")

    class _FakeStream:
        """脚本化流式客户端：按「第 N/M 栏」分派分块，并统计并发与每栏调用次数。"""

        def __init__(self, scripts: dict) -> None:
            self.scripts = scripts
            self.users: list[str] = []
            self.counts: dict[int, int] = {}
            self.caps: list[int] = []
            self.in_flight = 0
            self.max_in_flight = 0

        async def stream_text(self, system, user, *, max_tokens=None, label="", **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.users.append(user)
            self.counts[idx] = self.counts.get(idx, 0) + 1
            self.caps.append(max_tokens)
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            try:
                chunks = self.scripts[idx]
                if callable(chunks):
                    chunks = chunks(self.counts[idx])
                for chunk in chunks:
                    await asyncio.sleep(0)
                    yield chunk
            finally:
                self.in_flight -= 1

    good = {
        1: ["发布会概况：主办方、三块板块与整体基调。"],
        2: ["- **要点**：核心信息一条。"],
        3: ["**表态**：官方口径。"],
        4: ["**主持人**：问题？\n**发言人**：回应。"],
    }
    client = _FakeStream(dict(good))
    text = asyncio.run(
        fill_placeholder_by_columns(client, "内容来源略。", mb, plan, source_han=12000)
    )
    check("逐栏填充：四栏各一次调用", client.counts == {1: 1, 2: 1, 3: 1, 4: 1}, f"{client.counts}")
    check("逐栏填充：栏间并发（同时在飞 ≥2）", client.max_in_flight >= 2, f"{client.max_in_flight}")
    check("逐栏填充：输出上限透传到每次调用（6600）",
          bool(client.caps) and all(c == 6600 for c in client.caps), f"{client.caps}")
    check("逐栏填充：拼装出四栏正文、标题由程序生成、无残留占位符",
          bool(text)
          and "# 发布会概况" in text
          and "[发布会概况]" not in text
          and all(chunks[0] in text for chunks in good.values()),
          (text or "")[:80])
    check("逐栏填充：每栏只拿自己的说明 + 其它栏名（防越栏）",
          all("【本栏说明】" in u for u in client.users)
          and "只写第 1/4 栏（发布会概况）" in client.users[0]
          and "[核心信息]" in client.users[0], "")
    check("逐栏填充：带上【本篇目标】（目标长度写进指令区）",
          all("【本篇目标】" in u for u in client.users), "")

    para = "同一段话反复出现，这段特意写长一点以触发退化判据，并确保累计长度越过检查阈值。" * 3
    scripts = dict(good)
    scripts[2] = lambda attempt: (
        [para + "\n\n"] * 3 if attempt == 1 else ["- **要点**：重试后的内容。"]
    )
    client2 = _FakeStream(scripts)
    text2 = asyncio.run(
        fill_placeholder_by_columns(client2, "内容来源略。", mb, plan, source_han=12000)
    )
    check("退化早停：重复段落被中止，且只重试该栏（其它栏一次）",
          client2.counts == {1: 1, 2: 2, 3: 1, 4: 1}, f"{client2.counts}")
    check("退化早停：最终用重试后的内容", bool(text2) and "重试后的内容" in text2, (text2 or "")[:60])

    scripts3 = dict(good)
    scripts3[3] = lambda attempt: (
        ["这是一段用来把输出撑到上限之外的填充文字。" * 600]
        if attempt == 1
        else ["**表态**：重试内容。"]
    )
    client3 = _FakeStream(scripts3)
    text3 = asyncio.run(
        fill_placeholder_by_columns(client3, "内容来源略。", mb, plan, source_han=12000)
    )
    check("超长早停：输出超上限即中止并只重试该栏",
          client3.counts == {1: 1, 2: 1, 3: 2, 4: 1} and bool(text3) and "重试内容" in text3,
          f"{client3.counts}")

    long_para = "这是一段足够长的重复段落文本内容，长度要超过判据下限。"  # ≥24 字才参与判据
    check("退化判据：同段重复 3 次命中、2 次不命中",
          "重复" in _degenerate_reason("\n\n".join([long_para] * 3))
          and _degenerate_reason("\n\n".join([long_para] * 2)) == ""
          and _degenerate_reason("短句。\n\n短句。\n\n短句。") == "", "")

    pp = (_active_dir() / "project_progress.md").read_text(encoding="utf-8")
    check("有表格的模板不走逐栏路径（返回 None，交给整篇 JSON）",
          asyncio.run(
              fill_placeholder_by_columns(
                  _FakeStream({}), "略", pp, plan_placeholder_fill(pp)
              )
          )
          is None,
          "")


def test_media_overview_scope() -> None:
    """新闻发布 [发布会概况]：要素去掉与 [核心信息] 同名的词 + 可解析段上限 + 归位边界。

    回归背景（2026-09-18 实测周会）：概况写了 1264 汉字、212 个数字、单段，
    与 [核心信息] 栏 4-gram 重合 82%——因为它 ① 没有可解析尺寸（程序不拆段不报超限）
    ② 要素里写着"核心信息"，与下面那栏同名（引导复述）。
    """
    from tools.execution.hard_execution import split_overlong_paragraphs
    from tools.templates.template_eval import parse_section_char_budgets

    text = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    spec = next(l.strip() for l in text.splitlines() if l.strip().startswith("[一段话概括发布会"))
    check("发布会概况：一段写完（约 300–400 字，不再写 3 段×300）",
          "一段写完，约 300–400 字" in spec and "最多 3 段" not in spec, spec[:80])
    elements = spec.split("；", 1)[0]   # 要素部分（不含尾部的"归哪栏"边界句）
    check("发布会概况：要素不再出现与 [核心信息] 同名的词（边界句里保留指引）",
          "核心信息" not in elements and "发布单位与整体基调" in spec, spec[:80])
    check("发布会概况：写明归位边界（数据归 [核心信息]、立场归 [官方表态]、问答归 [Q&A环节]）",
          "[核心信息]" in spec and "[官方表态]" in spec and "[Q&A环节]" in spec
          and "本栏不复述" in spec, "")
    check("发布会概况：① 含时间地点/主办与参与（日期、地点、发言人身份、到会媒体）",
          "时间地点与主办/参与" in spec and "发布时间、地点、主办与发布单位、发言人身份、到会媒体" in spec
          and "没有的不编" in spec, "")
    # 2026-09-19 用户口径：概况偏薄（实测 148 汉字）——放宽可写内容而不是允许注水：
    # ② 单一讲话没有板块时列分点主张名；④ 允许 1–3 个数字锚点；⑤ 问答议题与后续安排。
    check("发布会概况：② 单一讲话没有板块时列出分点主张名",
          "有发布板块就列板块名；单一讲话没有板块时列讲话的分点主张名" in spec, "")
    check("发布会概况：④ 允许 1–3 个关键数字锚点（只报数字、不铺开数据）",
          "关键数字锚点 1–3 个" in spec and "只报数字、不铺开数据" in spec, "")
    check("发布会概况：⑤ 问答涉及的议题与后续安排（原文有才写）",
          "问答环节涉及的议题与会议后续安排" in spec and "原文有才写" in spec, "")
    caps = [b for b in parse_section_char_budgets(text) if b["title"] == "发布会概况"]
    check("发布会概况：解析出节级预算 300–400（首栏只写一段）",
          bool(caps) and caps[0]["scope"] == "section" and caps[0]["lo"] == 300
          and caps[0]["hi"] == 400, f"{caps}")

    han = lambda s: len(re.findall(r"[\u4e00-\u9fff]", s))
    para = "宏观方面，主讲人解读法案要点，测算关税收入可覆盖新增支出，赤字率维持合理区间。" * 18
    doc = "# 新闻发布\n\n# 发布会概况\n" + para + "\n\n# 核心信息\n- **要点**：略。\n"
    fixed, notes = split_overlong_paragraphs(doc, (_active_dir() / "media_briefing.md").read_text(encoding="utf-8"))
    seg = fixed.split("# 发布会概况", 1)[1].split("# 核心信息", 1)[0]
    parts = [q.strip() for q in seg.split("\n\n") if q.strip()]
    check("发布会概况：超长单段按句界拆开（节级 ≤400/段）",
          len(parts) >= 2 and max(han(q) for q in parts) <= 400,
          f"段长={[han(q) for q in parts]} {notes}")


def test_class_transcript_task_groups() -> None:
    """课堂记录 [课后任务与学习建议]：类目做小标题、其下分点（条内不再重复类目名）。

    回归背景（2026-09-18 实测）：该栏把类目写进每一条的前缀——「- **课堂练习**：完成讲义第20题…」
    连着 5 条、「- **复习重点**：…」「- **学习建议**：…」各若干条，还混着「**建议**：」单独一行
    再挂二级标签的第二种结构；类目名重复 10+ 次、两套结构并存，读起来是标签堆而不是清单。
    改成 `## 类目` + `- ` 条目后，类目只说一次、条目只写内容。
    """
    from tools.templates.template_eval import parse_section_char_budgets

    text = (_active_dir() / "class_transcript.md").read_text(encoding="utf-8")
    spec = next(l for l in text.splitlines() if "按类目分组" in l)

    check("三个类目小标题齐全（课堂练习/复习重点/学习建议）",
          all(k in spec for k in ("`## 课堂练习`", "`## 复习重点`", "`## 学习建议`")), spec[:80])
    check("类目有内容才出现、其下 `- ` 一条一行、条内不重复类目名",
          "有内容才出现" in spec and "`- ` 一条一行" in spec
          and "条内不再以类目名开头" in spec, "")
    check("每类写什么有口径（题号/考点、概念/定律、做法/器材）",
          "题号＋考点/方法＋结论要点" in spec and "概念/定律/结论＋适用条件" in spec
          and "可操作做法（器材、步骤）" in spec, "")
    check("保留条级尺寸与并列不合并（每条 30–120 字）",
          "每条 30–120 字" in spec and "各占一条" in spec, "")
    # 2026-09-19 实测：[核心知识点梳理] 1413 字（5 知识点 × 26 条）——优先收束重复表达，但不删关键事实
    kn = next(l for l in text.splitlines() if "按教学逻辑分层" in l)
    check("知识点梳理：优先 3–4 条，关键事实超出时继续保留",
          "每个知识点优先用 3–4 条" in kn and "关键事实超过 4 项时继续逐条保留" in kn, kn[:90])
    check("旧的行内标签形态已清除（不再每条挂「**任务**：」）",
          "**任务**：" not in text and "分别成条" not in text, "")

    seg = next(s for s in plan_placeholder_fill(text)["scalars"] if "按类目分组" in (s.get("hint") or ""))
    check("该栏保留缺省词语义（原文没布置作业 → 「未提及」）", seg.get("missing") is True, "")
    budgets = [(b["title"], b["hi"], b["scope"]) for b in parse_section_char_budgets(text)]
    # 2026-09-19：首栏补了「一段写完，约 250–400 字」→ 课程概况成为该模板唯一预算（节级）；
    # 问答栏仍不带字数门禁（按重要程度收）
    check("课堂记录：只有首栏预算（课程概况 400/节），问答栏无字数门禁",
          budgets == [("课程概况", 400, "section")], f"{budgets}")


def test_quote_columns_have_background() -> None:
    """金句/引语类栏：每条引用下带一句背景说明（治"脱离上下文的孤立金句"）。

    用户口径（2026-09-18）：金句下面要加一句"当前金句的出现背景"，一句话即可——
    引语没有背景就读不出分量，也无法核对它是否被断章取义。
    """
    from tools.template_router._placeholder import plan_placeholder_fill

    expectations = {
        "special_lecture": ("金句总结", ("讲到哪个话题/论证到哪一步", "`- 背景：未提及`")),
        "interview_transcript": ("关键引语与金句", ("回应什么问题/谈到什么话题", "`- 背景：未提及`")),
        "conversation_transcript": ("关键原话", ("谁对谁说的", "`- 背景：未提及`")),
    }
    for stem, (col, needles) in expectations.items():
        text = (_active_dir() / f"{stem}.md").read_text(encoding="utf-8")
        lines = text.splitlines()
        head_idx = next(i for i, l in enumerate(lines) if f"# [{col}]" in l)
        spec = lines[head_idx + 1]  # 栏名下的说明行
        for k in needles:
            check(f"{stem} [{col}]：背景说明口径（{k[:14]}…）", k in spec, spec[:80])
        # 2026-09-19 用户口径：金句行要加引号（`> “……”`）、背景行加 `背景：` 前缀
        check(f"{stem} [{col}]：格式固定（金句行 `> “……”`、背景行 `- 背景：……`）",
              "金句行用 `>` 引用并加引号" in spec and '`> “……”`' in spec
              and "背景行 `- 背景：……`" in spec, spec[:90])
        check(f"{stem} [{col}]：旧写法（无引号 / 背景行只写 `-`）已清除",
              "背景行用 `-`" not in spec and "「- 背景未提及」" not in spec, "")
        check(f"{stem} [{col}]：无 3 句下限（最多 8 句、有几句写几句，不硬凑）",
              "最多 8 句" in spec and "有几句写几句" in spec and "3–8 句" not in spec, "")
        check(f"{stem} [{col}]：背景限定一句话（不展开复述）",
              "一句话即可" in spec, "")
        quote_fields = [s for s in plan_placeholder_fill(text)["scalars"] if "逐字" in (s.get("hint") or "")]
        check(f"{stem} [{col}]：保留缺省词语义",
              bool(quote_fields) and quote_fields[0].get("missing") is True,
              f"{[s.get('missing') for s in quote_fields]}")


def test_ellipsis_table_row_template_recognized() -> None:
    """省略号样例行（`| … |`）也要被认成表格行模板——否则空表/缺表/行数检查整体失效。

    回归背景（2026-09-18 第27条实测）：就医咨询药品表只有表头没有数据行，但
    extract_template_table_constraints 只认 `[...]` 占位 → constraints=[] →
    「表格无有效数据行」对这类模板永不触发，空表静默落盘。
    """
    from tools.templates.template_eval import (
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
    from tools.templates.template_eval import parse_row_hint

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


def test_lecture_evidence_cap() -> None:
    """讲座 [核心观点与论证]：优先 3–4 条代表性论据，但不删除关键论据。

    回归背景（2026-09-19 实测）：陈廷敬讲座场该栏 2277 字（5 论点 × 29 条论据），
    每个论点下 6–8 条论据角度重复——"都要落进对应条目"只有下量没有取舍。
    """
    from tools.templates.template_eval import parse_section_char_budgets

    text = (_active_dir() / "special_lecture.md").read_text(encoding="utf-8")
    spec = next(l for l in text.splitlines() if "两级结构" in l and "## 论点" in l)
    check("讲座：两级结构 + 论点标题短语化（20 个汉字内，不写成会解析成预算的「20 字」）",
          "两级结构" in spec and "20 个汉字内" in spec and "20 字内" not in spec, spec[:80])
    check("讲座：同一论点优先 3–4 条，关键论据超出时继续保留",
          "同一论点优先用 3–4 条" in spec and "关键论据超过 4 项时继续逐条保留" in spec, spec[:80])
    check("讲座：直接数据/典型事例优先、重复表达可合并",
          "直接数据或典型事例" in spec and "重复表达可以合并" in spec, "")
    check("讲座：条级尺寸与下量口径保留（每条 30–120 字、细节落进条目）",
          "每条 30–120 字" in spec and "都要落进对应条目" in spec, "")
    got = [(b["title"], b["hi"], b["scope"]) for b in parse_section_char_budgets(text)]
    check("讲座：预算未漂（概况/问答照旧）",
          ("讲座概况", 400, "section") in got and ("Q&A 环节", 400, "paragraph") in got, f"{got}")



def test_court_claims_table_both_sides() -> None:
    """庭审 [原告诉称与被告辩称]：双方都要有成行承载（"各占一行"不再是 1 行上限）。

    回归背景（2026-09-19 now.xlsx 实测）：「原告、被告各占一行」被 parse_row_hint 误读成
    "全表最多 1 行"——装配截断 + 模型侧双通道都指向一行，二审场（上诉人国开行 vs 被上诉人
    东源等）被告行整行消失，而概况栏明明写全了当事人。
    """
    from tools.execution.hard_execution import apply_table_row_limits
    from tools.templates.template_eval import (
        extract_template_table_constraints,
        parse_row_hint,
    )

    text = (_active_dir() / "court_transcript.md").read_text(encoding="utf-8")
    check("庭审模板：样例行含原告与被告两行",
          "| 原告（或上诉人） | … |" in text and "| 被告（或被上诉人） | … |" in text, "")
    cons = extract_template_table_constraints(text)
    check("庭审：诉辩表不再有 1 行上限（row_limit=None）",
          bool(cons) and cons[0]["row_limit"] is None, f"{cons}")
    check("parse_row_hint：「各占一行」是形态不是上限",
          parse_row_hint("原告、被告各占一行（原文有第三人、反诉方的照此增行）") is None, "")
    check("parse_row_hint：数字行数仍有效（最多 3 行）",
          parse_row_hint("最多 3 行") == 3, "")

    # 端到端：两行诉辩数据不再被截成一行
    doc = (
        "# 庭审记录\n\n"
        "# 庭审概况\n本案系金融借款合同纠纷上诉案。\n\n"
        "# 原告诉称与被告辩称\n\n"
        "| 方 | 诉讼请求/答辩意见 | 事实与理由 |\n| --- | --- | --- |\n"
        "| 上诉人（国开行） | 请求改判 | 主张善意取得 |\n"
        "| 被上诉人（东源） | 请求驳回 | 一审判决正确 |\n\n"
        "# 举证与法庭调查\n- **证据**：略。\n\n"
        "# 庭审结果\n未提及。\n"
    )
    fixed, notes = apply_table_row_limits(doc, text)
    check("两行诉辩数据不再被截断", not notes and "被上诉人（东源）" in fixed, f"{notes}")


def test_output_volume_and_hierarchy() -> None:
    """总量天花板 + 理解层限流 + 两级层级标准（治"太平、太碎、超原文"）。

    用户指出（2026-09-19）：① 纪要超原文；② 挖得太细太碎、耗时长；③ 层级太平难浏览。
    根因：理解层"宁多不漏"全量抽取 → 草稿"把细节写开" → 渲染"每一项写足"，
    装配规则还允许"与原文同量级 90%–110%"。
    """
    import pathlib

    from tools.templates.length_budget import capped_budget

    check("天花板：原文 ×70% 与档位取小（3500 字原文 → 上限 2450）",
          capped_budget(3500) == (1080, 2450), f"{capped_budget(3500)}")
    check("天花板：30000 字原文仍受档位上限约束（8000）",
          capped_budget(30000) == (2400, 8000), f"{capped_budget(30000)}")
    bl = __import__("tools.templates.length_budget", fromlist=["budget_line"]).budget_line(3500)
    check("【篇幅预算】写明不超过原文 70%",
          "任何情况下不超过原文的 70%" in bl, bl[:120])
    check("【篇幅预算】下限口径收窄（补关键事实，不扩写寒暄与过程）",
          "不扩写寒暄与过程铺陈" in bl, "")

    u = pathlib.Path("domain/meeting/meeting_core/prompts.py").read_text(encoding="utf-8")
    check("理解层：key_points 每议题 ≤8 条、全篇 ≤30 条（按支撑力取舍）",
          "每议题最多 8 条、全篇最多 30 条" in u, "")
    check("理解层：寒暄/程序性发言不进索引",
          "过程性重复、寒暄、程序性发言不进索引" in u, "")
    check("理解层：同一事实重复表述只留信息最全的一条",
          "同一事实的多次重复表述只留信息最全的一条" in u, "")

    br = pathlib.Path("tools/templates/body_rules.py").read_text(encoding="utf-8")
    check("层级标准：栏内条目超 6 条必须归组（每组 2–5 条）",
          "超过 6 条时必须归组" in br and "每组 2–5 条" in br, "")
    mp = pathlib.Path("domain/meeting/tasks/minutes/prompts.py").read_text(encoding="utf-8")
    check("渲染：两级结构是默认形态（旧的分组禁令已反转）",
          "两级结构是默认形态" in mp and "纪要正文一律不用" not in mp, "")
    check("渲染：写清结论/关键数字/责任人/时限（过程铺陈压缩）",
          "结论、关键数字、责任人、时限" in mp and "过程铺陈压缩" in mp, "")
    check("草稿：写开对象收窄（过程铺陈与背景默认压缩）",
          "过程铺陈与背景默认压缩成半句" in mp, "")


def test_subjective_judgment_guardrails() -> None:
    """主观判断以原文明示为准：采访"看点"内化、辩论占优/获胜限源、hiring 评级不代打。

    用户指出（2026-09-19）：① 采访"讲了什么别人讲不出的"需要外部比较，越界；
    ② 辩论"转折/占优方/获胜方"在无主持人或评委结论时属主观裁判；
    ③ 面试官没给评级时模型会自行打分、"潜在风险点"会代面试官预判风险。
    """
    d = _active_dir()
    itv = (d / "interview_transcript.md").read_text(encoding="utf-8")
    check("采访：看点以受访者原话为限（不做外部比较）",
          "以受访者原话为限" in itv and "不做外部比较" in itv, "")

    deb = (d / "debate_forum.md").read_text(encoding="utf-8")
    check("辩论：转折/占优只在原文明示时写",
          "转折或占优只在原文明示时写" in deb and "不自判" in deb, "")
    check("辩论：获胜方原文明示才标注，未明示不写",
          "原文明示获胜方时才标注" in deb and "未明示不写" in deb, "")

    hir = (d / "hiring_report.md").read_text(encoding="utf-8")
    # 2026-09-19 用户口径：栏与表都**保留**，只去掉表里的「推荐评级」列（评级是模型主观判断，
    # 实测 7/7 全是「未评」零信息量）；维度名锚回原文的考察要素，行数随原文。
    check("面试：[能力评估] 栏与表保留，表头两列（无「推荐评级」）",
          "# [能力评估]" in hir and "| 评估维度 | 评估依据（具体事例） |" in hir
          and "推荐评级" not in hir and "评估维度 | 推荐评级" not in hir, "")
    check("面试：维度名取原文考察要素/评价口径、不自行发明能力模型",
          "取原文的考察要素或评价口径" in hir and "不自行发明能力模型" in hir
          and "岗位匹配度、问题解决能力、思维逻辑性、应变能力" not in hir, "")
    check("面试：行数随原文 + 依据必须有事例支撑",
          "行数随原文，原文提到几个维度就写几行" in hir
          and "每条都要有事例支撑，不做原文以外的推断" in hir, "")
    check("面试：评级/评分口径整体清除（不自行评价、打分或评级）",
          "不自行评价、打分或评级" in hir
          and "不自行给候选人评分、评级或下结论" in hir, "")
    check("面试：亮点/风险/建议三条都只写原文表达过的（不代面试官预判）",
          "三条都只写面试官或候选人原文表达过的内容" in hir
          and "不代面试官预判风险" in hir, "")

    # 完整性总原则：课堂/讲座 requirement 明确取舍边界
    cls = (d / "class_transcript.md").read_text(encoding="utf-8")
    lec = (d / "special_lecture.md").read_text(encoding="utf-8")
    check("课堂 requirement：取舍只作用于重复/同角度/次要内容",
          "取舍只作用于重复、同角度或次要内容" in cls, "")
    check("讲座 requirement：关键论点/直接数据/典型事例必须保留",
          "取舍只作用于重复、同角度或次要论据" in lec
          and "关键论点、直接数据与典型事例**必须保留" in lec, "")


def test_media_briefing_evidence_and_depth() -> None:
    """新闻发布会：核心信息要有依据、官方表态要能归属（主体/引语/第三方落点）。

    回归背景（2026-09-18 实测两篇）：[核心信息] 那句"数据注明来源或背景"没有落点——
    慕安会篇 9 条里带依据 0 条、带数字口径 0 条；[官方表态] 8 条 0 主体（同一篇 Q&A 每轮
    反而都有 `**王毅**：`，差别只在模板有没有称呼规则），引语 3 条平均 13 字且无归属，
    现场还出现"同一句两种措辞、其中一条被标成引语"。深挖与保真都以"谁说的、依什么"为前提。

    2026-09-19 用户口径：覆盖度已达标但**太细太碎**——"一条一件事、一条不落"把条目钉在
    单指标粒度上。改法：分两层（`## 板块名` 分组 + 每组 3–5 条）、条目单位上提（一条一个
    主题、同类合并）、覆盖度口径从"条"上移到"板块/主题"；依据/口径/时间表要求保持不变。
    """
    from tools.templates.template_eval import parse_section_char_budgets

    text = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    core = next(l for l in text.splitlines() if l.strip().startswith("[提炼官方发布"))
    stance = next(l for l in text.splitlines() if l.strip().startswith("[只写发言人"))

    check("核心信息：依据三样（依据/口径与范围/时间表）",
          all(k in core for k in ("依据", "口径与范围", "时间表")), core[:60])
    check("核心信息：覆盖度口径上移到板块/主题（不再是「一条一指标」）",
          "覆盖度以板块/主题为单位保证" in core and "每组数据都要有落点" in core
          and "数字、时间表、适用范围与对象、执行方式不落项" in core, "")
    check("核心信息：两级结构（`## 板块名` 分组 + 每组 3–5 条）",
          "分两层写" in core and "`## 板块名`" in core and "每组 3–5 条" in core, core[:80])
    check("核心信息：准确性（不换算不估算 + 时间分写 + 两栏分工）",
          "不换算、不估算、不自行加总" in core
          and "发布时间与生效/执行时间分开写" in core
          and "立场与主张归 [官方表态]" in core, "")
    check("核心信息：不逐条写人名（不写「某某表示/强调」前缀）",
          "本栏不逐条写人名" in core and "这类前缀" in core, "")
    check("核心信息：条目单位上提（一条一个主题、同类合并、一条一行）",
          "一条一个主题" in core and "合并成一条" in core
          and "不要拆成一指标一条、一举措一条" in core and "`- **要点**：内容`" in core, "")
    check("核心信息：旧口径已清除（一条一件事 / 原文有的都要列一条不落）",
          "一条一件事" not in core and "原文有的都要列、一条不落" not in core, "")
    check("核心信息：合并同类后仍保留多组取值对照（不要只留一侧）",
          "多组取值" in core and "不要只留一侧" in core, "")
    check("核心信息：数字/结论要与原文对得上、禁模糊来源、没有的不编",
          "与原文对得上" in core and "据悉/有关方面" in core and "原文没有的不编" in core, "")
    check("核心信息：保留加粗与 `具体内容` 标注口径",
          "关键数据加粗" in core and "`具体内容`" in core, "")

    check("官方表态：不写身份行（身份见概况、多人由组标题承担）",
          "不写身份行" in stance and "发言人身份见 [发布会概况]" in stance
          and "多位发言人由每组标题的机构或职务承担" in stance
          and "单一发言人不另标" in stance, "")
    check("官方表态：旧的身份行写法已清除（括号行/「交代一次」都不再出现）",
          "发言人身份在栏首交代一次" not in stance
          and "只写机构或职务、不写姓名" not in stance
          and "（外交部发言人）" not in stance, "")
    check("官方表态：条目不逐条写人名、不带「某某强调/指出」前缀",
          "不逐条写人名" in stance and "这类前缀" in stance, "")
    check("官方表态：不重复栏名、不把会议背景写成导语（背景归概况）",
          "不重复栏名、不把会议背景或议程写成导语" in stance
          and "背景归 [发布会概况]" in stance, "")
    check("官方表态：分组标题按 机构/职务＋议题；单一发言人只写议题",
          "`## 机构或职务｜议题`" in stance and "单一发言人时组名只写议题" in stance
          and "姓名｜议题" not in stance, "")
    check("官方表态：深挖粒度（一次表态多个承诺/条件分别列条）",
          "一次表态含多个承诺或条件时分别列条" in stance, "")
    check("官方表态：准确性（照原文保留限定语与程度 + 引用名称写全）",
          "照原文保留限定语与程度" in stance
          and "力争/有望/原则上/除" in stance
          and "会议名称照原文写全" in stance, "")
    check("官方表态：多发言人的身份由每组标题承担（不写姓名）",
          "多位发言人由每组标题的机构或职务承担" in stance, "")
    check("官方表态：四层深挖（主张/针对什么/条件与前提/承诺或边界）",
          all(k in stance for k in ("主张", "针对什么", "条件与前提", "承诺或边界")),
          stance[:60])
    check("官方表态：引语必须是连续原话、逐字照抄（概括/拼接句不算引语）",
          "连续原话" in stance and "逐字照抄" in stance and "不算引语" in stance, "")
    check("官方表态：第三方表态另起条目标来源，不与官方口径混写",
          "第三方表态另起条目标来源" in stance and "不与官方口径混写" in stance, "")
    check("官方表态：与提问对应的回应归 Q&A，同一内容不两栏都写",
          "Q&A环节" in stance and "同一内容不要两栏都写" in stance, "")

    # 预算守卫：说明里的裸「数字+字」会被解析成节级上限（parser 接受 `\d+\s*字`）。
    # Q&A 栏故意不声明字数（一旦写进去就变成"40 字上限"式误判并触发整篇返工）；
    # [官方表态] 的 800 是 2026-09-19 有意加的**栏级天花板**（now.xlsx 行8 实测 1174 汉字），
    # 该栏是 `- ` 分点行、不是散文段，超限只记 advisory、不会被拆段。
    got = [(s["title"], s["hi"], s["scope"]) for s in parse_section_char_budgets(text)]
    check("新闻发布：预算仍是 概况 400 / 官方表态 800 / Q&A 400 三条（无杂散解析）",
          got == [("发布会概况", 400, "section"), ("官方表态", 800, "section"),
                  ("Q&A环节", 400, "paragraph")], f"{got}")


def test_understanding_speakers_field() -> None:
    """理解层 speakers：姓名↔角色的结构化落点（Q&A/表态/概况的人名绑定不再靠每栏重推）。

    回归背景（2026-09-18 实测）：发布会 Q&A 的回应方写不出姓名，退化成 `**答**：`（甚至空白），
    提问方也出现「主持人（慕尼黑安全会议）」这种"机构凑身份位"的写法。根因不是规则，而是
    **姓名与角色的绑定没有落点**——理解层只有 topics[].participants（语义是"谁参与该议题"），
    渲染时每栏都得从几万字原文里重新推一次"这段是谁在说"，原文标签是角色时就直接放弃。
    """
    from dataclasses import fields as dc_fields

    from domain.meeting.meeting_core.contracts import (
        MeetingUnderstandingGenerationContract,
    )
    from domain.meeting.meeting_core.prompts import MEETING_UNDERSTANDING_SYSTEM_PROMPT
    from domain.meeting.models_generated import MeetingUnderstanding
    from domain.meeting.orchestrator import (
        _EMPTY_MEETING_UNDERSTANDING,
        UNDERSTANDING_SKIP_FIELDS,
        _Nodes,
    )

    spec = MeetingUnderstandingGenerationContract.to_json_template()
    check("契约含 speakers 字段（name/role/org）",
          "speakers" in spec and all(k in spec for k in ("name", "role", "org")), spec[:60])
    check("生成模型有 speakers 且按数组校验",
          "speakers" in {f.name for f in dc_fields(MeetingUnderstanding)}
          and "speakers 必须是数组" in Path("domain/meeting/models_generated.py").read_text(encoding="utf-8"),
          "")
    check("空结构常量带 speakers（降级路径不炸）", _EMPTY_MEETING_UNDERSTANDING.get("speakers") == [], "")

    prompt = MEETING_UNDERSTANDING_SYSTEM_PROMPT
    check("理解 prompt：称呼按姓名、角色、原始编号回退，不猜姓名",
          "发言人与角色对照" in prompt and "姓名 > 原文明确角色 > 原始编号" in prompt
          and "只有编号时保留原始编号" in prompt and "不猜姓名、不新编编号" in prompt, "")
    check("理解 prompt：姓名不再从 participants 语义里挤（单列字段）",
          "speakers：" in prompt, "")

    check("speakers 不在任何线的裁剪集合里（人名所有线都要）",
          all("speakers" not in skip for skip in UNDERSTANDING_SKIP_FIELDS.values()), "")
    for line in ("minutes", "minutes_trace"):
        keep = _Nodes._understanding_needle_keep.get(line)  # 类属性，不用实例
        check(f"{line}：审核摘录白名单含 speakers", bool(keep) and "speakers" in keep, f"{sorted(keep or [])}")

    # pack 侧：所有线都能拿到对照表（实测渲染退化的直接原因就是它不在包里）
    state = {
        "meeting_understanding": {
            "meeting_brief": "略", "meeting_purpose": "略", "scene": "专项讨论会",
            "speakers": [{"name": "王毅", "role": "发言人", "org": "外交部"}],
            "topics": [], "decisions": [], "risks": [], "open_questions": [],
        }
    }
    for line in ("minutes", "minutes_trace", "actions", "risks", "mindmap"):
        pack = _Nodes._meeting_pack(object(), state, line)
        names = [s.get("name") for s in pack.get("speakers") or []]
        check(f"{line} 的 pack 带 speakers（{names}）", names == ["王毅"], f"{pack.get('speakers')}")

    draft_prompt = Path("domain/meeting/tasks/minutes/prompts.py").read_text(encoding="utf-8")
    check("草稿 prompt 指明人名绑定看 speakers、不猜姓名",
          "`speakers` 字段" in draft_prompt and "不要凭称号猜姓名" in draft_prompt, "")


def test_qa_name_priority() -> None:
    """新闻发布会/媒体问答：能确定是谁就用姓名，不得用「主持人」「发言人」顶替已知姓名。

    回归背景（2026-09-18 实测）：两栏原口径是"能对应到人就用称呼（姓名优先，其次角色）"，
    示例又写成 ``**主持人**：…`` 换行 ``**发言人**：…`` → 提问方清一色落到角色上
    （同一篇里答方能用上姓名、提问方仍是「主持人」）。发布会的专业写法是"媒体名＋记者/姓名"，
    所以这里把"姓名优先"改成硬口径，并去掉纯角色示例的锚定。
    """
    d = _active_dir()
    brief = (d / "media_briefing.md").read_text(encoding="utf-8")
    qa = (d / "media_qa_session.md").read_text(encoding="utf-8")
    for text, name, role in (
        (brief, "新闻发布", "「主持人」「发言人」"),
        (qa, "媒体问答", "「记者」「发言人」"),
    ):
        spec = next(l for l in text.splitlines() if "一条问答独立成段" in l)
        check(f"{name}：一问一答＝一条记录 + 逐条编号（示例答方写姓名）",
              "一问一答＝一条记录" in spec and "逐条编号" in spec
              and "`**1. 记者（人民日报 张宇）**：…`" in spec
              and "`**陈立**：…`（答方写姓名" in spec, spec[:70])
        check(f"{name}：回应方能确定姓名就写姓名（「答」只作无姓名兜底）",
              "回应方能确定姓名就写姓名" in spec and "只有确实没有姓名时才写" in spec
              and "全篇统一用同一个称呼" in spec
              and "首次写全" not in spec, "")
        check(f"{name}：称呼只写姓名/媒体名，机构不得单独充当身份",
              "机构只能跟在人名/媒体名后" in spec and "不得单独充当身份" in spec, "")
        check(f"{name}：提问方姓名优先写成硬口径（原文出现过就必须用）",
              "原文任何位置出现过姓名就必须用" in spec, "")
        check(f"{name}：禁止用角色顶替已知姓名（{role}）",
              f"不得用{role}顶替已知姓名" in spec, "")
        check(f"{name}：保留问/答兜底与加粗、未提及兜底",
              "两方都对应不上人时才写成" in spec and "每轮称呼都加粗" in spec
              and "未提及" in spec, "")
        check(f"{name}：旧的软口径与纯角色示例已清除",
              "姓名优先，其次角色" not in spec
              and "`**主持人**：…` 换行" not in spec
              and "`**记者**：…` 换行" not in spec, "")

    from tools.templates.body_rules import BODY_FORMAT_RULES

    rule = next(l for l in BODY_FORMAT_RULES.splitlines() if "成员称呼" in l)
    check("全局称呼规则：文中出现过姓名就用姓名（已知姓名不得退回角色）",
          "原文任何位置出现过该人的姓名就用姓名" in rule
          and "已知姓名时不得退回角色" in rule, rule[:80])
    check("全局称呼规则：角色与编号仍是后手，并禁止张冠李戴",
          "确实没有姓名才用角色" in rule and "沿用原文编号" in rule
          and "张冠李戴" in rule, "")
    # 2026-09-19 实测（肖楠场）：提问方被写成"张楠"——问答段之外出现 0 次，属无支撑造名。
    check("全局称呼规则：问答用名必须有问答段之外的支撑（无支撑退角色）",
          "问答/对话中使用的姓名必须有支撑" in rule
          and "在问答段之外的原文里出现过" in rule
          and "没有支撑的一律按上述顺序回退" in rule, rule[-140:])
    check("全局称呼规则：同音/近音变体取主流写法、全篇统一",
          "同音/近音变体" in rule and "取全场主流写法" in rule and "全篇统一" in rule, "")

    asr = next(l for l in BODY_FORMAT_RULES.splitlines() if "语音识别错" in l)
    check("语音识别规则补人名三条：变体统一 / 外文名用职务 / 禁止造名",
          "人名另加三条" in asr
          and "取全场主流写法、全篇统一" in asr
          and "外文/音译人名没把握写全就用职务或角色称呼" in asr
          and "禁止造名" in asr and "对称联想" in asr, asr[-160:])

    understanding = Path("domain/meeting/meeting_core/prompts.py").read_text(encoding="utf-8")
    check("理解层：原文出现姓名时统一用姓名、不推断不编造",
          "原文任何位置出现姓名就统一用姓名" in understanding
          and "不推断、不编造" in understanding, "")


def test_product_launch_overview() -> None:
    """产品发布：概况要素归位（Slogan/主体/背景）+ 卖点不越栏 + 缺项合并成一句。

    回归背景（2026-09，now.xlsx 行28）：原文 5 次出现核心 Slogan 与研发主体、5 次出现
    地域对比背景，产出全丢；概况 137 字写成了"痛点+卖点清单"（167 厘米/60 厘米嵌入/无水盒），
    与 [市场定位]/[核心卖点] 重复；[定价与发售信息] 有 3 行"未提及"各占一行。
    另注：基线表里的"减少 39% 残留泡沫""拦截 99% 毛絮"原文并无，属于编造——不学。
    """
    text = (_active_dir() / "product_launch.md").read_text(encoding="utf-8")
    for need in (
        "核心 Slogan（原文有则逐字写）",
        "不展开痛点清单与卖点细节",
        "约 250–400 字",
        "原文给出的地域或人群差异背景",
        "原文给出的定价策略或价值口径按其原话一并写",
        "合并成一句",
    ):
        check(f"产品发布：含「{need}」", need in text, "")
    # 概况边界补到价格与参数（治"价格写进概况、[定价与发售信息] 只剩未提及"）
    for need in (
        "价格归 [定价与发售信息]",
        "参数与代际对比归 [核心卖点与技术参数]",
        "本栏不复述",
        "目标人群与一句话定位",
        "与发布场合",
    ):
        check(f"产品发布：概况栏边界/要素含「{need}」", need in text, "")

    # 首栏尺寸抬到 ≥动态下限（238）：这两栏首句是"一段话交代…"，进不了首栏四要素分支，
    # 只能靠模板自述的尺寸；写 120 会让它们成为唯一低于下限的一档。
    lecture = (_active_dir() / "special_lecture.md").read_text(encoding="utf-8")
    check("专题讲座：概况栏尺寸已抬到 250–400 字", "约 250–400 字" in lecture, "")
    leftovers = [
        p.stem
        for p in _active_dir().glob("*.md")
        if "约 120–250 字" in p.read_text(encoding="utf-8")
    ]
    check("首栏尺寸统一到 250–400（旧的 120–250 已清除）", not leftovers, f"残留={leftovers}")


def test_retro_annual_groups() -> None:
    """复盘会 [结果与关键成果]：按实际内容分组，年度栏目仅在原文存在时出现。

    回归背景（2026-09 实测）：该栏约 1500 字／31 条里 13 条是逐人评价（占半壁），
    组织数据与个人评价混排成流水账；逐人评价又与 [亮点事项]/[不足事项] 分工不清。
    """
    text = (_active_dir() / "retrospective_session.md").read_text(encoding="utf-8")
    for need in (
        "# [结果与关键成果]",
        "按原文实际内容分组，不预设年度场景",
        "只有原文明示年度总结、奖项、表彰或福利时",
        "人员评价有内容时按人分节",
        "### 姓名",
        "只有结论没有依据的条目不合格",
        "原文有几组写几组，没有的组不出现",
    ):
        check(f"复盘会：含「{need}」", need in text, "")
    check("复盘会：旧年度专用栏名与固定五分组已移除",
          "# [全年结果与表彰]" not in text and "固定五分组" not in text, "")


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
    # 2026-09-19 now.xlsx 行6 实测：该场没有证人/鉴定，[举证与法庭调查] 里出现
    # `## 证人/鉴定陈述` → 「未提及」的空标题；部分名也太窄，第三方材料无处安放。
    check("庭审记录：第三方陈述部分改为通用口径（证人、鉴定与其他来源陈述）",
          "## 证人、鉴定与其他来源陈述" in court
          and "凡不是当事人/代理人自己作出的陈述都归这里" in court
          and "## 证人/鉴定陈述" not in court, "")
    check("庭审记录：没有记载的部分整段不出现（不再逐部分写「未提及」）",
          "没有记载的部分整段不出现" in court and "四个部分都没有才写「未提及」" in court, "")
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
    understanding = Path("domain/meeting/meeting_core/prompts.py").read_text(encoding="utf-8")
    check("会议理解：有立场的陈述必须保留归属，不升级成事实",
          "陈述归属不得丢" in understanding and "不得把一方说法改写成客观事实" in understanding
          and "才能写成已认定事实" in understanding, "")


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


def test_first_column_single_paragraph_merge() -> None:
    """总述栏「一段写完」的程序保证：多段合并成一段 + 首栏豁免拆段（两条规则不打架）。

    回归背景（2026-09-19 now.xlsx 实测）：项目概况 862 字/3 段、沟通背景 974 字/3 段、
    课程概况 734 字/4 段——"一段写完"只有 prompt 约束；节级预算只管"单段超上限才拆"，
    模型拆成 3 段每段 ≤400 时任何检查都不触发；_overlong_issue 报了又被 repair 豁免。
    """
    from tools.execution.hard_execution import (
        _merge_first_column_paragraphs,
        enforce_render_output,
    )
    from tools.templates.template_eval import parse_section_char_budgets

    d = _active_dir()
    # ① 三个此前无尺寸的模板现在可解析出节级预算
    for stem, col in (
        ("retrospective_session", "复盘目标与结果概况"),
        ("class_transcript", "课程概况"),
        ("site_visit_tour", "参观概况"),
    ):
        text = (d / f"{stem}.md").read_text(encoding="utf-8")
        caps = [b for b in parse_section_char_budgets(text) if b["title"] == col]
        check(f"{stem}：首栏补齐尺寸（{col} 250–400/节）",
              bool(caps) and caps[0]["lo"] == 250 and caps[0]["hi"] == 400
              and caps[0]["scope"] == "section", f"{caps}")

    # ② 合并函数：多段散文 → 一段（用真实产物形态）
    tpl = (d / "project_progress.md").read_text(encoding="utf-8")
    doc = (
        "# 项目进度会\n\n"
        "# 项目概况\n第一段总述。" * 40 + "\n\n第二段总述。" * 30 + "\n\n第三段收尾。" * 10 + "\n\n"
        "# 进度追踪\n\n| 模块 | 进展 |\n| --- | --- |\n| 模块A | 正常 |\n"
    )
    merged, note = _merge_first_column_paragraphs(doc, tpl)
    seg = merged.split("# 项目概况")[1].split("\n# 进度追踪")[0]
    blocks = [b for b in seg.split("\n\n") if b.strip()]
    check("总述栏 3 段合并成 1 段（文字未丢）",
          note is not None and len(blocks) == 1
          and merged.replace("\n", "").replace(" ", "") == doc.replace("\n", "").replace(" ", ""),
          f"{note} 段块={len(blocks)}")
    check("其余栏（表格）不被合并触碰", "| 模块A | 正常 |" in merged, "")
    # 已是一段 → 不动
    _same, note2 = _merge_first_column_paragraphs(
        "# 项目进度会\n\n# 项目概况\n" + "总述。" * 100 + "\n", tpl
    )
    check("已是一段的栏不产生合并记录", note2 is None, f"{note2}")

    # ③ enforce 全链路：合并后首栏不被拆段（两条规则不打架）
    text, notes, _ = enforce_render_output(tpl, doc)
    seg = text.split("# 项目概况")[1].split("\n# 进度追踪")[0]
    check("enforce 后总述栏仍是一段（拆段跳过首栏）",
          len([b for b in seg.split("\n\n") if b.strip()]) == 1
          and any("合并成一段" in n for n in notes)
          and not any("项目概况」超长段" in n for n in notes),
          f"{notes}")

    # ④ 免疫检查：非「一段写完」的模板（如 debate_forum 旧场）不受影响
    other = (d / "media_qa_session.md").read_text(encoding="utf-8")
    check("media_qa_session 无「一段写完」标记 → 合并函数不生效",
          _merge_first_column_paragraphs(doc, other)[1] is None, "")


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
        test_first_column_min()
        test_general_minutes_speedread()
        test_document_budget_not_misread()
        test_paragraph_split()
        test_qa_speaker_labels()
        test_progress_table_rows()
        test_section_char_budget_scope()
        test_default_word_precedence()
        test_supervisor_unavailable_flow()
        test_advisory_checks()
        test_no_test_corpus_leak()
        test_knowledge_memo_groups()
        test_clinical_history_column()
        test_overview_specs_have_scope()
        test_debate_rounds_and_rows()
        test_exchange_forum_structure()
        test_interview_and_lecture_overview()
        test_reject_hardening()
        test_conversation_and_seminar_enrichment()
        test_qa_precision_rules()
        test_project_progress_overview()
        test_paragraph_cap_from_explicit_per_para()
        test_strip_default_only_content()
        test_enum_normalize_fallback()
        test_scene_hint_from_template()
        test_allow_missing_on_trimmed_fields()
        test_default_minutes_template()
        test_understanding_skip_never_retries()
        test_template_aware_understanding_skip()
        test_long_generation_output_cap()
        test_column_fill_concurrency_and_early_stop()
        test_media_overview_scope()
        test_class_transcript_task_groups()
        test_quote_columns_have_background()
        test_ellipsis_table_row_template_recognized()
        test_lecture_evidence_cap()
        test_first_column_single_paragraph_merge()
        test_court_claims_table_both_sides()
        test_output_volume_and_hierarchy()
        test_subjective_judgment_guardrails()
        test_media_briefing_evidence_and_depth()
        test_qa_name_priority()
        test_understanding_speakers_field()
        test_product_launch_overview()
        test_retro_annual_groups()
        test_domain_specific_accuracy_rules()
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
