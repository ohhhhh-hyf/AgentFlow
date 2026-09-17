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
    # v3 的结构优化改了几处栏位形态（general_minutes 由 6 个槽位改成 2 栏），故单独记一份
    "template_v3": {
        "class_transcript": 4, "clinical_advisory": 4, "contract_vetting": 4,
        "conversation_transcript": 4, "court_transcript": 4, "debate_forum": 4,
        "decision_review": 4, "exchange_forum": 4, "general_minutes": 2,
        "government_bulletin": 3, "group_seminar": 4, "hiring_report": 3,
        "home_school_liaison": 4, "interview_debrief": 4, "interview_transcript": 3,
        "knowledge_memo": 3, "legal_advisory": 4, "media_briefing": 4,
        "media_qa_session": 4, "personal_memo": 4, "product_launch": 4,
        "project_progress": 4, "psychological_session": 3, "research_dialogue": 3,
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
    finally:
        logging.getLogger("tools.template_router._gate").removeHandler(handler)

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项：" + "，".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
