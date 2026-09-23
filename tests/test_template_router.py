"""模板路由的零 LLM 守卫：占位识别（含方括号字面）、门禁方向、模板结构不变量。

用法::

    python -m tests.test_template_router      # 全绿退出码 0，有失败退出码 1

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

from tools.templates.router._base import iter_placeholders, split_template_meta
from tools.templates.router._detect import parse_placeholder_template
from tools.templates.router._gate import scan_fixed_bracket_literals, validate_rendered_output
from tools.templates.router._placeholder import plan_placeholder_fill

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
        "personal_minutes": 4,
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
        "class_transcript": 4, "clinical_advisory": 5, "contract_vetting": 4,
        "conversation_transcript": 5, "court_transcript": 3, "debate_forum": 5,
        "decision_review": 4, "exchange_forum": 5, "general_minutes": 3,
        "personal_minutes": 4,
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
    from tools.templates.router._placeholder import _line_placeholders

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
    from tools.templates.router._base import _PLACEHOLDER_FILL_SYSTEM as prompt

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
        with caplog.at_level(logging.WARNING, logger="tools.templates.router._gate"):
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

    from tools.templates.router._placeholder import fill_placeholder_template

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
    # 不再 return None：最后一轮（或与上一轮输出相同的那一轮）给仍空的字段补缺省词，保住模板结构。
    check("多轮仍缺栏 → 补缺省词保结构（不放半截文档、也不退回 freeform）",
          bool(out1) and "未提及" in (out1 or "") and "# 丙栏" in (out1 or ""), f"out={(out1 or '')[:80]!r}")
    check("仍空字段未被静默丢弃（甲/乙栏内容在）",
          "甲栏内容" in (out1 or "") and "乙栏内容" in (out1 or ""), "")
    check("连续两轮输出相同 ⇒ 提前收尾，不空跑第三轮", c1.calls == 2, f"calls={c1.calls}")
    check("重试指令点名缺哪一栏",
          len(c1.users) > 1 and "字段3" in c1.users[1],
          f"{c1.users[1][:100] if len(c1.users) > 1 else ''!r}")

    partial2 = '{"fields": {"1": "甲栏内容v2。", "2": "乙栏内容。"}, "tables": []}'
    partial3 = '{"fields": {"1": "甲栏内容v3。", "2": "乙栏内容。"}, "tables": []}'
    c3 = _FakeFillClient([partial, partial2, partial3])
    out3 = asyncio.run(fill_placeholder_template(c3, "内容来源：甲乙丙。", FILL_TPL))
    check("三轮输出各不相同 ⇒ 仍按上限重试 3 轮（原路径保留）",
          c3.calls == 3 and "甲栏内容v3" in (out3 or ""), f"calls={c3.calls}")

    c2 = _FakeFillClient([partial, full])
    out2 = asyncio.run(fill_placeholder_template(c2, "内容来源：甲乙丙。", FILL_TPL))
    check("重试补齐后按完整字段拼装",
          bool(out2) and "丙栏内容" in (out2 or ""), f"out={(out2 or '')[:60]!r}")
    check("补齐即停（不无谓多调一次）", c2.calls == 2, f"calls={c2.calls}")


def test_table_carried_column_allows_blank() -> None:
    """表格承载栏允许为空：不按"漏填"重试、不强填缺省词（hiring_report 实测，2026-09-22）。

    背景：hiring_report 第 3 栏说明写着「本栏明细由下表承载（本栏不再另写说明文字、
    不要写「未提及」）」——该栏正文本就该为空。旧判定把"任一栏为空"当漏填 ⇒ 每轮重试
    （~19s/轮）且最后强填「未提及」（与模板声明冲突），稳定复现。
    """
    import asyncio

    from tools.templates.router._placeholder import fill_placeholder_template

    tpl = (
        "# [候选人概况]\n[一段话概括候选人]\n\n"
        "# [能力评估]\n[**本栏明细由下表承载**（本栏不再另写说明文字、不要写「未提及」）]\n"
        "| 评估维度 | 评级 |\n| --- | --- |\n| [维度] | [评级] |\n"
    )

    class _Fake:
        def __init__(self, payload: str) -> None:
            self.payload = payload
            self.calls = 0

        async def text(self, system: str, user: str, **_kw) -> str:
            self.calls += 1
            return self.payload

    payload = (
        '{"fields": {"1": "候选人概况内容。", "2": ""}, '
        '"tables": [[["综合分析", "良"]]]}'
    )
    client = _Fake(payload)
    out = asyncio.run(fill_placeholder_template(client, "内容来源：略。", tpl))
    check("表格承载栏为空 ⇒ 一次调用即收尾（不按漏填重试）",
          client.calls == 1, f"calls={client.calls}")
    check("表格承载栏为空 ⇒ 终稿不含「未提及」",
          bool(out) and "未提及" not in (out or ""), (out or "")[:100])
    check("表格内容照常装配", "综合分析" in (out or ""), (out or "")[:140])


def test_fill_prompt_requires_all_keys() -> None:
    """提示层：输出约定与字段清单都点明「键必须齐全」（缺键＝漏填）。"""
    from tools.templates.router._base import _PLACEHOLDER_FILL_SYSTEM as system
    from tools.templates.router._placeholder import build_placeholder_fill_user

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
    from tools.templates.router._base import is_table_caption, table_caption_lines
    from tools.templates.router._placeholder import assemble_placeholder_output, plan_placeholder_fill

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

    from tools.templates.router._base import _PLACEHOLDER_FILL_SYSTEM as fill_system
    from tools.templates.router._placeholder import build_placeholder_fill_user

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
    from tools.execution.hard_execution import (
        advisory_issues,
        gate_render_output,
        overlong_items,
    )

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
    check("超长条判据单点函数：与 advisory 报的逐字相同（逐栏填充共用同一实现）",
          overlong_items(long_item) == [h for h in hits_item if "一条" in h],
          f"{overlong_items(long_item)}")
    check("超长条判据：短条不误报、条数上限生效",
          overlong_items("- **乙**：正常一条。") == []
          and len(overlong_items("\n".join([long_item] * 3), limit=2)) == 2,
          "")


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

    from tools.templates.router._base import _PLACEHOLDER_FILL_SYSTEM as fill_system
    from tools.templates.router._placeholder import build_placeholder_fill_user

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
    check("形态单点：人分组用 `**姓名**：` 独占行、本人那组叫「与我相关」、不把人名写成 `##`",
          "「人」不是板块" in BODY_FORMAT_RULES
          and "（本人那一组写 `**与我相关**：`）" in BODY_FORMAT_RULES
          and "不得把人名或「与我相关」写成 `##` 标题" in BODY_FORMAT_RULES, "")
    stale = ["每栏至少 2 个分类标签", "每条 20–80 字", "每条 2–3 处（分类标签"]
    hit = [k for k in stale if any(k in t for t in (fill_system, user, PLACEHOLDER_RULES, draft, render))]
    check("旧形态口径已从全部路径清除", not hit, f"残留={hit}")

    # ② 摘要分段：三处同一套（段数按内容、单段 ≤约 200 字——**只按字数口径**），旧数字已清除
    check("草稿 prompt / 契约都不再设固定段数上限",
          "≤4 段" not in draft and "≤4 段" not in gen_contract, "")
    check("草稿 prompt / 契约同写「不超过约 200 字」（单一维度，句数只作写法建议）",
          "不超过约 200 字" in draft and "不超过约 200 字" in gen_contract
          and "3 句或约" not in draft and "3 句或约" not in gen_contract, "")

    # ④ 篇幅口径三层同源（2026-09-22）：要求线（进 prompt）→ 拆分线（×1.2）→ 检查线（×1.5）
    # 兜底（重写/按句界截断）在动作层，不再有硬编码的 320/200。
    from tools.execution.hard_execution import (
        _CHECK_RATIO,
        _ITEM_CHECK_HAN,
        _ITEM_REQUIRE_HAN,
        _PARA_CHECK_HAN,
        _PARA_REQUIRE_HAN,
        _PARA_SPLIT_HAN,
        _SPLIT_RATIO,
    )
    check("三层数字有序：要求线 < 拆分线 ≤ 检查线（段落）／要求线 < 检查线（条目）",
          _PARA_REQUIRE_HAN < _PARA_SPLIT_HAN <= _PARA_CHECK_HAN
          and _ITEM_REQUIRE_HAN < _ITEM_CHECK_HAN,
          f"段落 {_PARA_REQUIRE_HAN}/{_PARA_SPLIT_HAN}/{_PARA_CHECK_HAN}，条目 {_ITEM_REQUIRE_HAN}/{_ITEM_CHECK_HAN}")
    check("检查线/拆分线由要求线派生（不再硬编码 320/200）",
          _PARA_CHECK_HAN == int(_PARA_REQUIRE_HAN * _CHECK_RATIO)
          and _PARA_SPLIT_HAN == int(_PARA_REQUIRE_HAN * _SPLIT_RATIO)
          and _ITEM_CHECK_HAN == int(_ITEM_REQUIRE_HAN * _CHECK_RATIO), "")
    check("prompt 里的要求线与代码常量一致（单一来源，必须同时改）",
          f"不超过约 {_PARA_REQUIRE_HAN} 字" in BODY_FORMAT_RULES
          and f"单条不超过约 {_ITEM_REQUIRE_HAN} 字" in BODY_FORMAT_RULES, "")
    from tools.execution.hard_execution import advisory_issues as _adv
    check("advisory 阈值取自派生常量（默认值不再硬编码）",
          _adv.__kwdefaults__.get("para_han") == _PARA_CHECK_HAN
          and _adv.__kwdefaults__.get("long_han") == _ITEM_CHECK_HAN, "")
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
    from tools.templates.router._base import _describe_field
    from tools.templates.body_rules import BODY_FORMAT_RULES
    from tools.templates.template_prompt import PLACEHOLDER_RULES

    from tools.templates.router._base import _PLACEHOLDER_FILL_SYSTEM as fill_system
    from tools.templates.router._detect import _parse_field
    from tools.templates.router._placeholder import build_placeholder_fill_user

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

    from tools.templates.router._base import _PLACEHOLDER_FILL_SYSTEM as fill_system
    from tools.templates.router._placeholder import build_placeholder_fill_user

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
    from tools.templates.router._base import (
        split_template_meta,
        wrap_template_requirement,
    )
    from tools.templates.router._placeholder import plan_placeholder_fill
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
    # 2026-09-20 用户口径（方案1）：段数最多 8 段（按议题/阶段分段）+ 每段一段话最多 150 字。
    # 上限与段数上限成对写，避免只压单段上限时"上限被当目标"（曾 13 段 ×272 字占全篇一半）。
    check("通用纪要：摘要为一段 250–400（节级），速览为一段 200–250（段落级）",
          any(b["title"] == "全文摘要" and b["lo"] == 250 and b["hi"] == 400 and b["scope"] == "section" for b in budgets)
          and any(b["title"] == "分段速览" and b["hi"] == 250 and b["scope"] == "paragraph" for b in budgets),
          f"{budgets}")
    seg_spec = next(l.strip() for l in raw.splitlines() if "推进顺序" in l)
    check("通用纪要：速览按议题分段 + 段数最多 8 段 + 每段一段话 ≤250 字",
          "每个时间段一行" in seg_spec and "按议题或阶段分段，不按每一个时间戳切" in seg_spec
          and "段数最多 8 段" in seg_spec and "一段话描述该段" in seg_spec
          and "每段最多 250 字" in seg_spec and "每段至少一句" in seg_spec
          and "单段不超过约 300 字" not in seg_spec
          and "不重复 [要点梳理] 已列的条目与数字" in seg_spec,
          seg_spec[:80])
    from tools.execution.hard_execution import (
        _no_split_sections,
        split_overlong_paragraphs,
    )

    check("通用纪要：速览不声明「不拆段」（超长段由 250 字上限按句界拆分）",
          "分段速览" not in _no_split_sections(tpl), f"{_no_split_sections(tpl)}")
    long_seg = "这是一段概览文字。" * 55  # ≈440 汉字，远超 250×1.2
    fixed_seg, seg_notes = split_overlong_paragraphs(
        "# 通用纪要\n\n# [分段速览]\n## 08:00-12:30 现场检查\n" + long_seg + "\n", tpl
    )
    seg_parts = [q for q in fixed_seg.split("\n\n") if "概览文字" in q]
    check("通用纪要：速览超 300 字的段被程序按句界拆分（250 字上限生效）",
          bool(seg_notes) and len(seg_parts) >= 2 and max(sum(1 for c in q if "一" <= c <= "鿿") for q in seg_parts) <= 260,
          f"段数={len(seg_parts)} {seg_notes}")
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

    from tools.templates.router._base import split_template_meta, wrap_template_requirement

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
        enforce_render_output,
        gate_render_output,
        split_overlong_paragraphs,
        split_overlong_paragraphs_except_first,
    )
    from tools.templates.template_eval import parse_section_char_budgets

    from tools.templates.router._base import split_template_meta, wrap_template_requirement

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

    # 段边界丢换行曾把 `# 栏名` 粘到上一栏末尾：渲染层对同一文本跑两次 enforce，
    # 第一遍把空行削成单换行、第二遍直接粘连（2026-09-22 真链路实测）。
    gm = (_active_dir() / "general_minutes.md").read_text(encoding="utf-8")
    two = "# 分段速览\n" + long_para + "\n\n# 要点梳理\n- 乙\n"
    once, n_once = split_overlong_paragraphs_except_first(two, gm)
    twice, _ = split_overlong_paragraphs_except_first(once, gm)
    check("段边界换行保留（跑两次也不把 `# 要点梳理` 粘上去）",
          n_once and "\n\n# 要点梳理" in once and "\n\n# 要点梳理" in twice,
          f"once={once[-26:]!r} twice={twice[-26:]!r}")
    glued_doc, gnotes, _ = enforce_render_output(gm, "# 分段速览\n正文结束。# 要点梳理\n- 乙\n")
    check("已粘连的栏名由兜底步骤提回独立行",
          "\n# 要点梳理" in glued_doc and any("粘连" in n for n in gnotes),
          f"{gnotes} {glued_doc[-34:]!r}")

    # 回归（2026-09-22）：`## 栏名` 曾被误判为「粘在正文里的栏名」⇒ 改写成 `#` 裸行 +
    # 重复标题（knowledge_memo 的 `## 核心结论` 稳定复现）。合法子标题必须原样保留。
    keep_doc, keep_notes, _ = enforce_render_output(
        gm, "# 分段速览\n正文结束。\n\n## 分段速览\n- 乙\n"
    )
    check("合法的 ## 子标题（与栏名同名）保持原样、不改写",
          "## 分段速览" in keep_doc
          and not re.search(r"(?m)^#\s*$", keep_doc)
          and not keep_notes,
          f"{keep_notes} {keep_doc[-46:]!r}")
    keep2, keep2_notes, _ = enforce_render_output(
        gm, "# 分段速览\n正文结束。\n\n### 分段速览\n- 乙\n"
    )
    check("合法的 ### 子标题同样不改写",
          "### 分段速览" in keep2 and not keep2_notes, "")

    # 标题形态加固（2026-09-22）：裸标题确定性删除；同级别同名标题重复判硬伤。
    bare_doc, bare_notes, _ = enforce_render_output(
        gm, "# 分段速览\n正文结束。\n\n#\n\n# 分段速览\n- 乙\n"
    )
    check("裸标题行（只有 # 没有文字）被确定性删除并记 note",
          not re.search(r"(?m)^#\s*$", bare_doc)
          and any("裸标题" in n for n in bare_notes),
          f"{bare_notes} {bare_doc[-40:]!r}")


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
        "未开始",
        "尚未开展或尚未闭合的事项",
        "资料、依据、签字等程序性不完善",
    ):
        check(f"项目进度会：含「{need}」", need in text, "")
    check("项目进度会：不夹带示例式软引导（如「应拆成 … 五行」）",
          "应拆成" not in text and "五行" not in text, "")
    from tools.templates.body_rules import BODY_FORMAT_RULES

    check("共用形态规则的状态集同步四态",
          "未开始" in BODY_FORMAT_RULES, "")


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


def test_group_headings_need_body() -> None:
    """`## 组 + - 条` 型栏目：标题下必须有正文；空标题是门禁硬伤（2026-09-20）。

    回归背景：讲座那条 199.6s 的请求在渲染阶段「只重写 [核心观点与论证]」→ 单栏重写后仍不过
    → 整篇回退重填（46s + 63s + 49s）。最可能的硬伤是「只有标题没有正文（空栏）」——
    模型只写了 `## 论点` 而没落 `- ` 条目。故在各组标题型栏目统一声明「标题必带正文」。
    """
    clause = "**标题下必须至少一条正文（`- ` 条目或一段），不得只有标题"
    cols = (
        ("special_lecture.md", "核心观点与论证"),
        ("class_transcript.md", "核心知识点梳理"),
        ("group_seminar.md", "发言要点"),
        ("interview_transcript.md", "访谈详细记录"),
        ("general_minutes.md", "要点梳理"),
        ("media_briefing.md", "核心信息"),
        ("media_briefing.md", "官方表态"),
        ("exchange_forum.md", "核心信息与数据"),
        ("debate_forum.md", "环节交锋"),
        ("government_bulletin.md", "重点工作"),
        ("knowledge_memo.md", "核心概念"),
        ("research_dialogue.md", "核心反馈"),
        ("hiring_report.md", "面试问答纪要"),
        ("psychological_session.md", "咨询详情"),
        ("product_launch.md", "核心卖点与技术参数"),
        ("team_meeting.md", "工作进展"),
        ("retrospective_session.md", "结果与关键成果"),
    )
    missing: list[str] = []
    for fn, col in cols:
        text = (_active_dir() / fn).read_text(encoding="utf-8")
        spec = ""
        cur = None
        for seg in parse_placeholder_template(text):
            if seg["kind"] == "title":
                cur = seg["raw"]
            elif seg["kind"] == "field" and cur == col:
                spec = str(seg["hint"])
                break
        if clause not in spec:
            missing.append(f"{fn}#{col}")
    check("组标题必须带正文（标题下至少一条 `- ` 条目或一段）", not missing, f"缺={missing}")
    lec = (_active_dir() / "special_lecture.md").read_text(encoding="utf-8")
    check("讲座：子论点作为条目＋缩进子条，不单独立标题",
          "**子论点作为该论点下的一条" in lec and "不单独立标题**" in lec, "")


def test_home_school_feedback_groups() -> None:
    """家校沟通 [家长反馈]：按组按点（两组固定名）+ 原话组带背景行（2026-09-20 用户口径）。

    回归背景：原说明把「原话用 `> ` 引用」与「问题与关注点用 `- ` 列表」并列，没写从属关系 →
    实测产物出现「2 条条目 + 3 条裸引用 + 4 条缩进子条」，子条挂到最后一条引用下面（层级错位）。
    """
    text = (_active_dir() / "home_school_liaison.md").read_text(encoding="utf-8")
    check("家校沟通：[家长反馈] 按组、按点写（两组固定名，有内容才出现）",
          "**按组、按点写**" in text and "`## 家长关注的问题与诉求`" in text
          and "`## 家长原话`" in text and "有内容才写该组，原文没有的组不出现" in text, "")
    check("家校沟通：[家长反馈] 原话组带背景行（与全库引语栏一致，最多 2–3 条）",
          "**最多 2–3 条**" in text and "逐字引用、不省字、不改写" in text
          and "金句行 `> “……”`、背景行 `- 背景：……`" in text
          and "原文没线索就写 `- 背景：未提及`，不编" in text, "")
    check("家校沟通：[家长反馈] 两组都没有才写缺省 + 与 [沟通内容] 不重复",
          "两组都没有就写「未提及」" in text
          and "**本栏与 [沟通内容] 不重复（同一件事只在一栏写）**" in text, "")
    # 只在本栏范围内查示例（避免误伤其它栏的正当措辞）
    spec = next(l for l in text.splitlines() if l.startswith("[") and "家长原话" in l)
    check("家校沟通：[家长反馈] 不再出现示例式软引导（项别名与示范清单已清除）",
          "如费用" not in spec and "如手机" not in spec and "例如" not in spec
          and "（照原文）" not in spec, spec[:60])


def test_clinical_history_column() -> None:
    """就医咨询：4 栏 + 5 列药品表（2026-09-20 按 v2 参考收敛），病史并入 [就诊概况]。

    回归背景（2026-09，now.xlsx 行24）：原文 5 次提到"过敏"，产出一次都没写（基线写了）；
    职业（研究所）等个人史同样丢失——4 栏后这些硬要求挂在 [就诊概况] 上。
    """
    text = (_active_dir() / "clinical_advisory.md").read_text(encoding="utf-8")
    for need in (
        "过敏史、禁忌类信息原文出现就必须逐项写入，不得省略",
        "原文提到就逐项落条",
        "职业照原文",
        "只有医生或原文明确认定为异常、偏高、偏低或需关注的指标才加粗",
        "不得依据医学常识、参考范围或模型判断自行认定异常",
    ):
        check(f"就医咨询：含「{need}」", need in text, "")
    check("就医咨询：旧口径（病史留给「下面各栏」）已清除",
          "病史与用药细节留给下面各栏" not in text, "")
    # 2026-09-20 用户口径：病史背景从 [就诊概况] 拆出，单开一栏按点总结（5 栏）。
    check("就医咨询：5 栏（病史背景单开 [病史与背景]；[病情说明与沟通] 仍不退场）",
          (("# [病史与背景]" in text or "## [病史与背景]" in text) and "# [病情说明与沟通]" not in text
          and (text.count("\n# [") == 5 or text.count("\n## [") == 5)), "")
    check("就医咨询：[病史与背景] 按点总结（一条一个事实 + 原文明说才写缺省）",
          "**一条一个事实**（`- **项别**：内容`）" in text
          and "原文说到哪几项就写哪几项，不要为凑清单把没有的项写成「未提及」" in text
          and "过敏史、禁忌类信息原文出现就必须逐项写入" in text
          and "个人史与生活史原文提到就逐项落条" in text, "")
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
    check("就医咨询：四栏尺寸口径（概况 250–400 / 病史 250–450 / 诊断 250–500 / 复诊 100–250）",
          ("就诊概况", 250, 400) in got and ("病史与背景", 250, 450) in got
          and ("诊断与检查结果", 250, 500) in got
          and ("复诊与预警信号", 100, 250) in got, f"{got}")
    check("就医咨询：概况栏要素密度（主诉照原文写全 + 归位句 + 未确诊写法）",
          "核心主诉照原文写全" in text
          and "**病史与个人史明细归 [病史与背景]**" in text
          and "未确诊照原文写「考虑…，需…进一步明确」，不把推测写成确诊" in text, "")
    check("就医咨询：症状叙述不算过程铺陈、不得压缩（[病史与背景]）",
          "症状与病史的描述本身就是核心事实" in text
          and "不得当成「过程铺陈」压缩成一句" in text, "")
    check("就医咨询：各栏不再硬要原文没有的项（按实际出现立条 / 有哪几类写哪几类）",
          "按原文实际给出的类别立条" in text
          and "有哪几类写哪几类，没有的类别不立条" in text, "")
    check("就医咨询：复诊栏条件化（原文给了安排才写）+ 预警逐项 + 观察项落点",
          "原文给了复诊/随访安排才写复诊时间" in text
          and "原文提到的预警症状必须逐项写入" in text
          and "需要观察的变化" in text, "")
    check("就医咨询：[复诊与预警信号] 按组、按点总结（三组固定 + 组内分点）",
          "**按组、按点写**" in text and "`## 复诊与随访安排`" in text
          and "`## 预警信号`" in text and "`## 需要观察的变化`" in text
          and "有内容才写该组，原文没有的组不出现" in text, "")


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
    check("辩论会：论点表样例行交错示范（一方/立场A→对方/立场B→一方/立场A，4 列无时间列）",
          "| [一方/立场A] | … | … | … |" in debate
          and debate.index("| [一方/立场A] | …") < debate.index("| [对方/立场B] | …")
          and debate.count("| [一方/立场A] | … | … | … |") == 2
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
    from tools.templates.router._placeholder import plan_placeholder_fill
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
        # 问答长度口径：各模板保留可解析的「每段上限」提示（media_briefing 于 2026-09-22 有意收紧到 350）；
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
            expect_hi = 350 if stem == "media_briefing" else 400
            check(f"{stem}：问答栏保留可解析的长度口径（{expect_hi}/段，作提示）",
                  any(int(b["hi"]) == expect_hi for b in para), f"{para}")
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
    check("项目进度会：概况栏改为可解析的字数区间（一段写完，约 250–350 字）",
          "一段写完，约 250–350 字" in overview, f"{overview[:60]}")
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
    check("项目进度会：概况栏预算为节级 250–350（首栏只写一段）",
          bool(caps) and caps[0]["hi"] == 350 and caps[0]["scope"] == "section", f"{caps}")


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
    # 2026-09-20：速览改为「一段话 ≤250 字」，段落级预算生效（超 300 字＝250×1.2 按句界拆）
    check("通用纪要：速览段落级预算 (200,250) 生效",
          bool(gcaps) and gcaps[0]["hi"] == 250 and gcaps[0]["scope"] == "paragraph", f"{gcaps}")
    spec_seg = next(l.strip() for l in gm.splitlines() if "推进顺序" in l)
    check("通用纪要：速览一段话 ≤250 字、段数最多 8 段、明细归 [要点梳理]",
          "一段话描述该段" in spec_seg and "每段最多 250 字" in spec_seg
          and "段数最多 8 段" in spec_seg and "每段至少一句" in spec_seg
          and "具体条目、数字与分工归 [要点梳理]" in spec_seg
          and "不重复 [要点梳理] 已列的条目与数字" in spec_seg,
          spec_seg[:80])
    para_sub = "这是一段概览文字。" * 55  # ≈440 汉字，单段
    for label, doc in (
        ("无子标题", "# 通用纪要\n\n# 分段速览\n" + para_sub + "\n"),
        ("带 ## 时间段", "# 通用纪要\n\n# 分段速览\n## 08:00-12:30 现场检查\n" + para_sub + "\n"),
    ):
        fixed, notes = split_overlong_paragraphs(doc, gm)
        seg_parts = [q for q in fixed.split("\n\n") if "概览文字" in q]
        check(f"通用纪要：速览 440 字段按 250 字上限拆分（{label}）",
              bool(notes) and len(seg_parts) >= 2
              and max(sum(1 for c in q if "一" <= c <= "鿿") for q in seg_parts) <= 260,
              f"段数={len(seg_parts)} {notes}")

    # ③ 声明只作用于本栏：同一文档里其它栏（全文摘要）仍按节级上限拆
    doc4 = (
        "# 通用纪要\n\n# 全文摘要\n" + para_sub
        + "\n\n# 分段速览\n## 08:00-12:30 现场检查\n" + para_sub + "\n"
    )
    fixed4, notes4 = split_overlong_paragraphs(doc4, gm)
    abs_part = fixed4.split("# 全文摘要", 1)[1].split("# 分段速览", 1)[0]
    check("通用纪要：两栏各自按自己的上限拆（摘要节级 400 / 速览段落级 250）",
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
          _choice_or_default("专项讨论会", {"通用", "专项讨论会"}, "通用") == "专项讨论会", "")
    check("_choice_or_default：非法值归一到 default",
          _choice_or_default("产品发布", {"通用", "专项讨论会"}, "通用") == "通用", "")

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
            if s.startswith("# "):
                title_part = s[2:].strip().strip("[]").strip()
                for k in TEMPLATE_SCENE_HINTS:
                    if k == title_part or title_part.startswith(k) or k in title_part:
                        name = k
                        break
                if name:
                    break
                if not s[2:].strip().startswith("["):
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

    from tools.llm.llmclient import LLMClient
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

    from tools.llm.llmclient import LLMClient
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
            self.channel = None

        async def run(self, transcript, *, focus_line="", skip_fields=(), user_channel=""):
            self.seen.append((focus_line, frozenset(skip_fields)))
            self.channel = user_channel

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

    # 本用户称呼表由节点按 state 画像现算（客观/无画像 → 空串，不注入）
    asyncio.run(node({"transcript": "原文略。", "user": {"name": "赵衡", "name_aliases": ["小赵"]}}))
    check("节点把称呼表传给理解层",
          "赵衡（全称）" in (fake.channel or "") and "小赵" in (fake.channel or ""), str(fake.channel))
    asyncio.run(node({"transcript": "原文略。", "user": {"perspective": "objective", "name": "赵衡"}}))
    check("客观视角不传称呼表", not fake.channel, str(fake.channel))


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

    placeholder_src = Path("tools/templates/router/_placeholder.py").read_text(encoding="utf-8")
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

    from tools.templates.router._placeholder import (
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


def test_column_fill_overlong_item_rewrite() -> None:
    """逐栏填充：单条超长（`- ` 条目 >200 汉字）当硬问题 → 只重写中招那一栏，并下发具体修法。

    回归背景（2026-09-22 实测「端侧待办与现网推测问题」转写，同一输入相邻两次运行）：
    要点梳理栏把 12 条待确认 + 20 条风险各用「；」压成一条（233 字 / 519 字）原样落盘——
    审核在渲染之前（看不到栏内文字）、渲染层只把它当 advisory 记账，于是无人拦。
    现在这一栏会被定位、重写一次（一次单栏调用），渲染层行为不变。
    """
    import asyncio
    import re as _re

    from tools.execution.hard_execution import overlong_items
    from tools.templates.router._placeholder import (
        fill_placeholder_by_columns,
        plan_placeholder_fill,
    )

    mb = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    plan = plan_placeholder_fill(mb)
    long_bullet = "- **表态**：" + "官方口径说明" * 45 + "。"
    good = {
        1: "发布会概况：主办方、三块板块与整体基调。",
        2: "- **要点**：核心信息一条。",
        4: "**主持人**：问题？\n**发言人**：回应。",
    }

    class _FakeStream:
        """脚本化流式客户端：第 3 栏首轮给一条超长条，重写轮给分条版本。"""

        def __init__(self) -> None:
            self.users: list[str] = []
            self.counts: dict[int, int] = {}

        async def stream_text(self, system, user, *, max_tokens=None, label="", **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.users.append(user)
            self.counts[idx] = self.counts.get(idx, 0) + 1
            if idx == 3:
                yield long_bullet if self.counts[idx] == 1 else (
                    "- **表态**：官方口径一条。\n- **口径**：另一条。"
                )
            else:
                yield good[idx]

    client = _FakeStream()
    text = asyncio.run(
        fill_placeholder_by_columns(client, "内容来源略。", mb, plan, source_han=12000)
    )
    check("超长条：判据命中（>200 汉字的一条）", bool(overlong_items(long_bullet)), "")
    check("超长条：只重写中招那一栏（其余栏各一次）",
          client.counts == {1: 1, 2: 1, 3: 2, 4: 1}, f"{client.counts}")
    check("超长条：重写时下发具体修法（拆成多条 `- `、一条一个事项）",
          "拆成多条" in client.users[-1] and "一条一个事项" in client.users[-1],
          client.users[-1][-160:] if client.users else "")
    check("超长条：重写后的内容进了正文", "官方口径一条" in (text or ""), (text or "")[:60])
    check("超长条：最终正文不再有超长条", bool(text) and overlong_items(text) == [], "")


def test_personal_risk_attribution_in_pack() -> None:
    """真人模式：分钟线 pack 的风险/未决按原文补出归属（「姓名：」前缀）；客观零外溢。"""
    from domain.meeting.orchestrator import MeetingAgentSystem

    transcript = (
        "申家坤 00:00:05\n今天过长文本线。\n"
        "徐玥 00:00:20\n我这边还有一个风险：合规材料还没批下来，审批拖着会影响你的报告交付。\n"
        "武思华 00:00:45\n我的风险是接口权限没批，可能影响我这边的测试进度。\n"
    )
    understanding = {
        "speakers": [{"name": "申家坤"}, {"name": "徐玥"}, {"name": "武思华"}],
        "topics": [],
        "decisions": [],
        "risks": [
            "合规材料还没批下来，审批拖着会影响你的报告交付",
            "接口权限没批，可能影响测试进度",  # 轻度改写：靠 12 字探针对上原文
            "930 窗口期不多了",
        ],
        "open_questions": ["合规材料审批何时批下来"],
    }
    host = object.__new__(MeetingAgentSystem)  # 不跑 __init__（会建 LLM client）
    state = {
        "transcript": transcript,
        "user": {"name": "申家坤", "name_aliases": ["家坤"]},
        "objective_perspective": False,
        "meeting_understanding": understanding,
    }
    pack = host._meeting_pack(state, "minutes")
    risks = list(pack["risks"])
    check("真人 pack：有归属的风险条目带「姓名：」前缀",
          risks[0].startswith("徐玥：") and risks[1].startswith("武思华："), str(risks))
    check("真人 pack：看不出归属的全局风险不加前缀",
          risks[2] == "930 窗口期不多了", str(risks))
    check("真人 pack：派生问句（原文没有逐字表述）不硬归人",
          pack["open_questions"] == ["合规材料审批何时批下来"], str(pack["open_questions"]))
    obj = host._meeting_pack({**state, "objective_perspective": True}, "minutes")
    check("客观 pack：不加任何前缀（零外溢）",
          obj["risks"] == understanding["risks"]
          and obj["open_questions"] == understanding["open_questions"], str(obj["risks"]))


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
    from tools.templates.router._placeholder import plan_placeholder_fill

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


def test_table_row_bracket_not_split_as_field() -> None:
    """表格数据行内的方括号（如 `| [一方/立场A] | … |`）不应被拆解为正文占位字段。

    回归背景（2026-09-23 辩论会实测）：辩论会论点表使用了 `| [一方/立场A] | … | … | … |` 示范，
    parse_placeholder_template 误将其拆为字段，导致表格被腰斩成断头残片，门禁 100% 误报
    「模板表格结构不符」并触发 repair 重试。
    """
    from tools.templates.router._detect import parse_placeholder_template
    from tools.templates.router._gate import validate_rendered_output

    deb_tmpl = (_active_dir() / "debate_forum.md").read_text(encoding="utf-8")
    segs = parse_placeholder_template(deb_tmpl)
    table_segs = [s for s in segs if s.get("kind") == "table_rows"]
    check("辩论会：论点表被完整解析为 3 行 table_rows（未被括号割裂）", len(table_segs) == 3, f"{len(table_segs)}")

    rendered = (
        "# 辩论会\n\n"
        "## 辩论内容概述\n一段话概括辩题与走势。\n\n"
        "## 核心论点\n双方整体格局与立论框架。\n\n"
        "| 阵营 / 立场方 | 立论框架 | 核心论点 | 支撑论据 |\n"
        "| --- | --- | --- | --- |\n"
        "| 正方 | 框架一 | 论点一 | 支撑论据数据与原话 |\n"
        "| 反方 | 框架二 | 论点二 | 支撑论据事实依据 |\n\n"
        "## 争议焦点\n1. **【争议焦点】核心矛盾**\n   - **分歧本质**：取舍\n\n"
        "## 环节交锋\n### 自由辩论：【攻防】\n- **正方（张三）**：发言\n> **反方（李四）**：回应\n\n"
        "## 结辩与评委点评\n1. **正方结辩**：陈词\n2. **反方结辩**：陈词\n3. **评委点评**：点评\n"
    )
    errs = validate_rendered_output(rendered, deb_tmpl)
    check("辩论会：正常输出表格门禁 0 报错（彻底杜绝表格结构不符误判）", len(errs) == 0, f"{errs}")


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
    # 2026-09-19 曾按用户口径删掉「推荐评级」列（模型自行打分、7/7 全是「未评」）；
    # 2026-09-20 用户要求恢复：表头三列，并配「评级只依据原文 + 与同行依据同源、无依据写 —」。
    check("面试：[能力评估] 表头三列（评估维度 / 推荐评级 / 评估依据）",
          "# [能力评估]" in hir
          and "| 评估维度 | 推荐评级 | 评估依据（具体事例） |" in hir
          and "| … | … | … |" in hir, "")
    check("面试：维度名取原文考察要素/评价口径、不自行发明能力模型",
          "取原文的考察要素或评价口径" in hir and "不自行发明能力模型" in hir
          and "岗位匹配度、问题解决能力、思维逻辑性、应变能力" not in hir, "")
    check("面试：行数随原文 + 依据必须有事例支撑",
          "行数随原文，原文提到几个维度就写几行" in hir
          and "每条都要有事例支撑，不做原文以外的推断" in hir, "")
    # 2026-09-20 实测（now.xlsx 行19）：原口径「评级只依据原文」被读成「原文没写评分 → 全列 `—`」；
    # 改成「判据是本行依据、有依据必须给评级、只有无点评无事实才写 `—`」。
    check("面试：评级纪律（判据是本行依据、有依据必须给评级、无依据才写 `—`）",
          "**评级的判据是本行的依据**" in hir and "依据栏写了事例的维度**必须给出评级**" in hir
          and "**只有该维度既无点评也无作答事实时评级才写 `—`**" in hir
          and "评级不得与依据矛盾、不得出现录用结论" in hir
          and "不自行给候选人评分、评级或下结论" in hir, "")
    check("面试：[综合素质] 分组分点（三组固定名 + 组内一条一个观察）",
          "**按组、按点写**" in hir and "`## 突出亮点`" in hir
          and "`## 潜在风险点`" in hir and "`## 推进建议`" in hir
          and "有内容才写该组，原文没有的组不出现" in hir, "")
    check("面试：突出亮点/风险点/推进建议三组都只写原文表达过的（不代面试官预判）",
          "只写面试官或候选人原文表达过的内容" in hir
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
    check("核心信息：两级结构（`## 板块名` 分组 + 每组 1–4 条）",
          "分两层写" in core and "`## 板块名`" in core and "每组 1–4 条" in core, core[:80])
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
    # [官方表态] 的栏级天花板 2026-09-19 定为 800（now.xlsx 行8 实测 1174 汉字）、
    # 2026-09-22 有意收紧到 700；
    # 该栏是 `- ` 分点行、不是散文段，超限只记 advisory、不会被拆段。
    got = [(s["title"], s["hi"], s["scope"]) for s in parse_section_char_budgets(text)]
    check("新闻发布：预算仍是 概况 400 / 官方表态 700 / Q&A 350 三条（无杂散解析）",
          got == [("发布会概况", 400, "section"), ("官方表态", 700, "section"),
                  ("Q&A环节", 350, "paragraph")], f"{got}")


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
        # 2026-09-20：新闻发布单方面改成「逐条输出、不带编号前缀」，媒体问答仍是「逐条编号」，
        # 两者并存 → 按各自写法容忍；口径要不要统一由用户定。
        check(f"{name}：一问一答＝一条记录（逐条呈现，示例答方写姓名）",
              "一问一答＝一条记录" in spec
              and ("逐条编号" in spec or "逐条输出" in spec)
              and ("`**1. 记者（人民日报 张宇）**：…`" in spec
                   or "`**记者（人民日报 张宇）**：…`" in spec)
              and "`**陈立**：…`（答方写姓名" in spec, spec[:70])
        check(f"{name}：回应方能确定姓名才写姓名（「答」只作无姓名兜底）",
              "回应方能确定姓名才写姓名" in spec and "不能确定就写「**答**」" in spec
              and "全篇统一用同一个称呼" in spec
              and "首次写全" not in spec, "")
        check(f"{name}：称呼只写姓名/媒体名，机构不得单独充当身份",
              "机构只能跟在人名/媒体名后" in spec and "不得单独充当身份" in spec, "")
        check(f"{name}：提问方按确定度回退（不确定就不写名字）",
              "**提问方按确定度回退**" in spec
              and "都不确定就不写名字、写成「问」" in spec
              and "不得把原文别处出现过的姓名安到本次提问上" in spec, "")
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
    check("全局称呼规则：还要能确定对应的就是本次提问/回应的人（不确定不得用）",
          "还要能确定对应的就是本次提问或回应的人" in rule
          and "但无法确定对应关系的，**不得使用**" in rule, "")
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
    """总述栏「一段写完」的程序保证：多段合并成一段 + 总述栏豁免拆段（两条规则不打架）。

    回归背景（2026-09-19 now.xlsx 实测）：项目概况 862 字/3 段、沟通背景 974 字/3 段、
    课程概况 734 字/4 段——"一段写完"只有 prompt 约束；节级预算只管"单段超上限才拆"，
    模型拆成 3 段每段 ≤400 时任何检查都不触发；_overlong_issue 报了又被 repair 豁免。

    补记（2026-09-21 通用纪要实测）：规则按"位置"认总述栏会认错——首栏按规范只写一段
    时定位滑到下一栏（[分段速览]）并把它合并、`##` 子标题一起删；⑤⑥⑦ 就是这次的口径。
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
    #    「首栏 3 段」＝一个 [项目概况] 栏里三个散文段；写法上必须让 `* 40` 只作用于整句，
    #    否则字面量隐式拼接（优先级高于 `*`）会把 `# 项目进度会`/`# 项目概况` 复制 40 遍，
    #    42 个一级栏的畸形稿会让断言测不到首栏（2026-09-21 修）
    tpl = (d / "project_progress.md").read_text(encoding="utf-8")
    doc = (
        "# 项目进度会\n\n# 项目概况\n"
        + "第一段总述。" * 40
        + "\n\n第二段总述。" * 30
        + "\n\n第三段收尾。" * 10
        + "\n\n# 进度追踪\n\n| 模块 | 进展 |\n| --- | --- |\n| 模块A | 正常 |\n"
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

    # ⑤ 2026-09-21 通用纪要实测：首栏按规范只写一段（1 段 < 2）时定位不能滑到下一栏。
    #    旧位置口径取"第一个含 ≥2 散文段的栏"，[全文摘要] 一段被跳过 → [分段速览]
    #    （时间轴恰好 2 段）被当总述栏合并成一段，`## 时间段` 子标题随正文一起消失，
    #    门禁仍 pass（日志只有一行 INFO：「分段速览」为总述栏（一段写完））。
    gm = (d / "general_minutes.md").read_text(encoding="utf-8")
    gm_head = "# 通用纪要\n\n# 全文摘要\n本次例会围绕端侧待办与回流展开。（一段写完）\n\n"
    gm_seg = (
        "# 分段速览\n"
        "## 08:00-12:30 现场检查\n\n第一段时间段的一段话。\n\n"
        "## 12:30-17:00 讨论\n\n第二段时间段的一段话。\n\n"
        "# 要点梳理\n\n- 条目一。\n"
    )
    same, gm_note = _merge_first_column_paragraphs(gm_head + gm_seg, gm)
    check("通用纪要：首栏已是一段 → 不拿下一栏顶替总述栏（2026-09-21 实测）",
          gm_note is None and same == gm_head + gm_seg, f"{gm_note}")
    # 首栏多段时仍合并，且合的是 [全文摘要]、不碰 [分段速览] 的时间轴子标题
    gm_multi = gm_head + "第二段摘要。\n\n" + gm_seg
    merged_gm, note_gm = _merge_first_column_paragraphs(gm_multi, gm)
    check("通用纪要：首栏多段 → 合并 [全文摘要]（时间轴栏与子标题不动）",
          note_gm is not None and "全文摘要" in note_gm
          and "## 08:00-12:30 现场检查" in merged_gm
          and "## 12:30-17:00 讨论" in merged_gm, f"{note_gm}")
    gm_text, gm_notes, _ = enforce_render_output(gm, gm_multi)
    check("通用纪要：enforce 全链路后 [分段速览] 两个时间段子标题仍在",
          "## 08:00-12:30 现场检查" in gm_text.split("# 分段速览")[1]
          and "## 12:30-17:00 讨论" in gm_text.split("# 分段速览")[1],
          f"{gm_notes}")

    # ⑥ 文档标题以 `# 一级栏` 出现时（装配稿常见），总述栏仍豁免拆段——
    #    旧实现只跳"首个一级栏"，真正的总述栏落到第二位、合并完又被拆回多段。
    titled = (
        "# 项目进度会\n\n# 项目概况\n"
        + "总述。" * 200
        + "\n\n# 进度追踪\n\n| 模块 | 进展 |\n| --- | --- |\n| 模块A | 正常 |\n"
    )
    t_text, t_notes, _ = enforce_render_output(tpl, titled)
    t_seg = t_text.split("# 项目概况")[1].split("# 进度追踪")[0]
    check("文档标题在场时总述栏仍不被拆段（600 字一段原样保留）",
          len([b for b in t_seg.split("\n\n") if b.strip()]) == 1
          and not any("项目概况」超长段" in n for n in t_notes),
          f"{t_notes}")

    # ⑦ 模板栏名解析不出（标记写在序言里）→ 退回位置口径：只认第一个有散文段的栏，
    #    且首栏已是一段时不得再往后找（否则就是 ⑤ 的老毛病）
    raw_tpl = "（一段写完，约 250–400 字）\n\n# [概况]\n[概述]\n\n# [其它]\n[明细]\n"
    _r, r_note = _merge_first_column_paragraphs(
        "# 标题\n\n# 概况\n第一段。\n\n第二段。\n\n# 其它\n明细一。\n", raw_tpl
    )
    check("栏名解析不出：退回位置口径仍能合并首栏", r_note is not None and "概况" in r_note, f"{r_note}")
    _r2, r_note2 = _merge_first_column_paragraphs(
        "# 标题\n\n# 概况\n一段。\n\n# 其它\n明细一。\n\n明细二。\n", raw_tpl
    )
    check("栏名解析不出：首栏一段时不滑到后面的多段栏", r_note2 is None, f"{r_note2}")


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


def test_understanding_user_channel() -> None:
    """理解层「本用户称呼表」：别称归全称、编号发言人不绑、客观/职业模板不注入。

    回归背景（P0-A 2026-09-21）：下游（视角裁剪、待办 owner、跨场记忆、审核）只认理解层
    写下的那个名字字符串——实测同一个人在三场里被写成「发言者1 / 小赵 / 赵工」，状态里
    他的三条待办漂在三个"名字"下，个人模式分工栏因对不上姓名而选空、程序又回退全量。
    视角建模那轮连原文都看不到，治不了人名；只有理解层能统一（零新增调用，约百字输入）。
    """
    import asyncio

    from domain.meeting.meeting_core.meeting_understanding_agent import (
        MeetingUnderstandingAgent,
    )
    from domain.meeting.meeting_core.prompts import MEETING_UNDERSTANDING_SYSTEM_PROMPT
    from perspective import build_user_channel

    prompt = MEETING_UNDERSTANDING_SYSTEM_PROMPT
    check("理解 prompt：称呼表把别称归全称、编号发言人不绑",
          "【本用户称呼】" in prompt and "永远不等于本用户" in prompt
          and "归到全称那一个写法" in prompt,
          "")
    check("理解 prompt：仍是「不猜姓名」的口径（只统一既有称呼）",
          "不猜姓名" in prompt and "不要拿用户姓名去替换别人" in prompt, "")

    block = build_user_channel(
        {"name": "赵衡", "name_aliases": ["小赵", "赵工"], "role": "后端工程师"}
    )
    check("称呼表含全称与别称", "赵衡（全称）" in block and "小赵、赵工" in block, block)
    check("称呼表写明统一写法与不猜编号",
          "统一写成「赵衡」" in block and "发言者1" in block, block)
    check("客观视角不注入", build_user_channel({"perspective": "objective", "name": "赵衡"}) == "", "")
    check("职业模板不注入（姓名是职业通称，不能当人名）",
          build_user_channel({"name": "开发人员", "persona_type": "role_template"}) == "", "")
    check("没有姓名不注入", build_user_channel({"name": "  "}) == "", "")

    class _Stub:
        """只记录用户消息，不真的调模型。"""

        def __init__(self) -> None:
            self.user = ""

        async def structured(self, system, user, model_cls, contract, **kw):
            self.user = user
            return {"_stub": True}

    stub = _Stub()
    agent = MeetingUnderstandingAgent(stub)
    asyncio.run(
        agent.run(
            "发言者1：这周我把接口联调完。小赵：行，我下午提单。",
            focus_line="minutes",
            skip_fields={"risks"},
            user_channel=block,
        )
    )
    check("称呼表拼在裁剪指令之后、会议原文之前",
          stub.user.index("【本次输出裁剪】")
          < stub.user.index("本用户称呼")
          < stub.user.index("会议原文："),
          stub.user[:120])
    asyncio.run(agent.run("原文", user_channel=""))
    check("无称呼表时不注入空块（用户消息仍以会议原文开头）",
          "本用户称呼" not in stub.user and stub.user.startswith("会议原文："), stub.user[:60])


def test_perspective_skip_for_personal() -> None:
    """P1-C：真人命中非空时跳过视角建模（省一轮核心调用），改用程序合成。

    回归背景：视角建模那轮看不到原文（输入只有理解 JSON + 画像），"他是谁"由理解层的
    称呼表 + 命中表决定；有命中时它的产出字段（attention_points / responsibilities /
    possible_actions / evidence）程序都能算，再跑一轮只是复述。唯一保留 LLM 的是
    "真人 + 完全没命中 + 挂 role_template"。
    """
    import asyncio

    from domain.meeting.orchestrator import _Nodes
    from perspective import PerspectiveModeling

    class _Spy:
        def __init__(self, behave: str = "raise") -> None:
            self.calls = 0
            self.behave = behave

        async def run(self, input_context, user_json):
            self.calls += 1
            if self.behave == "raise":
                raise AssertionError("这一路不该调用视角建模 LLM")

            class _Out:
                @staticmethod
                def model_dump() -> dict:
                    return {"confidence": "high", "name": "赵衡", "inferred_role": "后端工程师"}

            return _Out()

    class _Host(_Nodes):
        """只借 _Nodes 的方法；不跑父类 __init__（不建 LLM 客户端）。"""

        def __init__(self, agent) -> None:
            self.perspective_modeling_agent = agent

        def _understanding(self, state):
            return state.get("meeting_understanding") or {}

    user = {"name": "赵衡", "name_aliases": ["小赵", "赵工"], "role": "后端工程师"}
    understanding = {
        "speakers": [{"name": "赵衡"}],
        "action_hints": [{"text": "接口联调周五前给测试", "owner": "赵衡", "timing": "周五前"}],
        "decisions": [],
        "risks": [],
        "open_questions": [],
        "topics": [],
    }
    empty_understanding = {"speakers": [], "action_hints": [], "decisions": [], "risks": [],
                           "open_questions": [], "topics": []}

    spy = _Spy()
    out = asyncio.run(
        _Host(spy)._make_perspective_node(["minutes"])(
            {"user": user, "meeting_understanding": understanding, "objective_perspective": False}
        )
    )
    check("命中非空（单线）：没有调用视角建模 LLM", spy.calls == 0, f"calls={spy.calls}")
    PerspectiveModeling.validate(out["perspective_profile"])  # 合成必须过 schema（全字段必填）
    check("命中非空：合成模型过 schema，且要点/依据来自命中",
          out["perspective_profile"]["name"] == "赵衡"
          and "接口联调周五前给测试" in out["perspective_profile"]["attention_points"]
          and bool(out["perspective_profile"]["evidence"]),
          str(out["perspective_profile"])[:120])
    check("命中表写进 state（供草稿/审核）",
          (out.get("user_hits") or {}).get("confidence") == "high"
          and "本用户命中" in (out.get("user_hits_block") or ""),
          str(out.get("user_hits_block"))[:70])

    spy2 = _Spy("ok")
    asyncio.run(
        _Host(spy2)._make_perspective_node(["minutes"])(
            {
                "user": dict(user, role_template="developer"),
                "meeting_understanding": empty_understanding,
                "objective_perspective": False,
            }
        )
    )
    check("未命中 + 有职业底：仍然跑建模（唯一保留）", spy2.calls == 1, f"calls={spy2.calls}")

    spy3 = _Spy("ok")
    asyncio.run(
        _Host(spy3)._make_perspective_node(["minutes", "actions"])(
            {"user": user, "meeting_understanding": understanding, "objective_perspective": False}
        )
    )
    check("多线请求：不跳（保待办/风险线的视角模型）", spy3.calls == 1, f"calls={spy3.calls}")

    # 保守口径（2026-09-21 定）：画像里有可扫关注域（挂职业底 / 自写 focus_areas 等）→ 一律走建模。
    # 理由：命中表只按姓名查，"没点名但落在他关注域"的条目只有建模能捞；只有极简画像才允许跳过。
    spy5 = _Spy("ok")
    asyncio.run(
        _Host(spy5)._make_perspective_node(["minutes"])(
            {
                "user": dict(user, focus_areas=["接口契约与依赖", "排期节点"]),
                "meeting_understanding": understanding,
                "objective_perspective": False,
            }
        )
    )
    check("自写关注域 + 命中非空：仍走建模（保守口径）", spy5.calls == 1, f"calls={spy5.calls}")

    spy4 = _Spy("ok")
    out4 = asyncio.run(
        _Host(spy4)._make_perspective_node(["minutes"])(
            {
                "user": {k: v for k, v in user.items()},
                "meeting_understanding": empty_understanding,
                "objective_perspective": False,
            }
        )
    )
    check("未命中 + 无职业底：跳过并合成「本场未点到」（不跑 LLM）",
          spy4.calls == 0 and "未点到" in out4["perspective_profile"]["personal_summary"],
          f"calls={spy4.calls} {out4['perspective_profile']['personal_summary']}")


def test_personal_no_full_fallback() -> None:
    """P1-10 真人不再"裁空回退全量" + P2-F 命中表进审核上下文与三条检查。

    回归背景：命中块告诉草稿"哪些是他的"、模型照做裁成空（本场确实没他的事），
    但程序 ``subset_upstream_items`` 会把**全员条目**塞回他的视角——"赵衡视角"输出
    全员待办就是这么来的。职业模板保留回退（它更容易整类漏），真人必须选空即空。
    """
    from tools.execution.hard_execution import enforce_minutes_draft, subset_upstream_items

    upstream = ["接口联调周五前给测试", "端侧版本下周带上", "数据标注这周归档"]
    check("真人：选空 → 空（不再回退全量）",
          subset_upstream_items(upstream, [], fallback_full=False) == [], "")
    check("职业模板：选空 → 仍回退全量（行为不变）",
          subset_upstream_items(upstream, [], fallback_full=True) == upstream, "")
    check("真人：选中能对上的 → 只留对上的（上游原序原文）",
          subset_upstream_items(upstream, ["端侧版本下周带上"], fallback_full=False)
          == ["端侧版本下周带上"], "")
    check("真人：一条都对不上 → 空（不回退全量）",
          subset_upstream_items(upstream, ["完全无关的一句"], fallback_full=False) == [], "")
    check("默认参数仍是回退全量（老调用不静默改行为）",
          subset_upstream_items(upstream, []) == upstream, "")

    draft = {
        "headline": "进展同步",
        "key_decisions": [],
        "risks_and_blockers": [],
        "unresolved_questions": ["端侧版本下周带上"],
    }
    understanding = {"meeting_purpose": "进展同步", "decisions": ["引擎并发先借资源"],
                     "risks": ["双录还没确认"], "open_questions": ["端侧版本下周带上"]}
    personal = enforce_minutes_draft(dict(draft), understanding, mode="personal")
    check("enforce（真人）：选空的两项是空、选中的对齐上游原文",
          personal["key_decisions"] == [] and personal["risks_and_blockers"] == []
          and personal["unresolved_questions"] == ["端侧版本下周带上"], str(personal))
    role = enforce_minutes_draft(dict(draft), understanding, mode="role_template")
    check("enforce（职业模板）：选空的两项回退全量",
          role["key_decisions"] == ["引擎并发先借资源"] and role["risks_and_blockers"] == ["双录还没确认"],
          str(role))
    objective = enforce_minutes_draft(dict(draft), understanding, mode="objective")
    check("enforce（客观）：三项全量拷贝（与模式判定无关）",
          objective["key_decisions"] == ["引擎并发先借资源"] and len(objective["risks_and_blockers"]) == 1, "")

    # P2-F：审核上下文带命中块 + 审核提示词三条
    from domain.meeting.tasks.minutes.prompts import MINUTES_SUPERVISOR_DOMAIN_PROMPT as MINUTES_SUPERVISOR_PROMPT

    # 注：提示词里有 ** 加粗标记，断言别跨标记取串
    check("审核提示词含命中表三条检查",
          "命中表三条" in MINUTES_SUPERVISOR_PROMPT
          and "在命中表内" in MINUTES_SUPERVISOR_PROMPT
          and "不得当负责人或发言人" in MINUTES_SUPERVISOR_PROMPT
          and "至少用上一条命中条目" in MINUTES_SUPERVISOR_PROMPT, "")
    check("审核提示词允许「命中表未命中 → 分工为空」",
          "分工栏为空是允许的" in MINUTES_SUPERVISOR_PROMPT, "")


def test_person_reference_rules() -> None:
    """人名口径（方案③，2026-09-21 定）：本人动作省主语、他人动作写真名、
    待办/提醒/被点名才用「你」，分工与引语一律真名，同句与相邻两句不混用；
    客观与职业模板仍是第三人称、不许出现「你」「您」。

    口径演进：① 起初三处（草稿硬规则 / 渲染纪律 / 审核视角偏差）一律禁止「你」「您」
    → 个人视角读起来与他无关；② 改成"真人正文用第二人称「你」" → 实测同一上下文两次跑
    出来一次「你」37 次、另一次 11 次且与真名混排，读着别扭（本 session 用户反馈）；
    ③ 现在按"中文允许省主语"的口径——叙述本人动作省主语，他人动作写名，只在需要点明
    归属时用「你」。审校三条都同步：允许省主语、拦他人动作缺主语、拦同句混用。
    """
    from domain.meeting.tasks.minutes.prompts import (
        MINUTES_GENERATION_SYSTEM_PROMPT as GEN,
        MINUTES_RENDER_PROMPT as RENDER,
        MINUTES_SUPERVISOR_DOMAIN_PROMPT as REVIEW,
    )

    check("草稿：真人模式本人动作省主语 + 他人动作写真名",
          "本人动作**省主语**" in GEN and "他人动作写真名" in GEN, "")
    check("草稿：不再无条件禁止「你」「您」", "禁止正文「你」「您」" not in GEN, "")
    check("草稿：真人口径段同步（省主语 / 只在该用时用「你」/ 人名照写）",
          "只保留与该姓名直接相关内容" in GEN and "照原文写真名" in GEN
          and "不混用" in GEN, "")
    check("渲染：人名口径四条齐备（省主语 / 真名 / 你 / 不混用）",
          "本人动作省主语" in RENDER and "他人动作写真名" in RENDER
          and "只有待办/提醒/被点名才用「你」" in RENDER
          and "同一句与相邻两句不混用" in RENDER, "")
    check("渲染：不再写「正文用第二人称「你」指代本人」那种全篇「你」的口径",
          "正文用第二人称「你」指代本人" not in RENDER, "")
    check("通顺性：给本人动作省主语开口子（否则被判半截句）",
          "真人模式叙述本人动作时主语可省" in RENDER, "")
    check("审核：客观/职业模板出现「你」「您」仍要拦",
          "**客观/职业模板**正文出现「你」「您」" in REVIEW, "")
    check("审核：真人模式把分工/责任人写成「你」要拦",
          "真人模式把分工/责任人/引语里的人名写成「你」" in REVIEW
          and "真名要保真" in REVIEW, "")
    check("审核：新增两条——他人动作缺主语、同句混用都要拦",
          "真人模式他人动作缺主语" in REVIEW and "混用「你」与真名" in REVIEW, "")


def test_assignment_scope_rules() -> None:
    """分工范围：真人档只列他的条目，客观/职业模板仍按分工条数（2026-09-21 收紧）。

    根因（实测分工栏里带出武思华/范炳杰/盛晋珲的条目）：不是模型不听话，是契约就这么写的——
    ``personally_relevant_points`` 的字段说明与提示词都写「条数 = 有明确责任人 + 明确职责的
    分工数」，通篇没限定本人；草稿照契约列了全场分工，渲染只是照抄。所以四处一起收：
    ① 契约字段说明 ② 提示词字段小节 ③ 草稿真人视角段 ④ 审核一条（渲染后没有审核环节，
    那一侧只能靠纪律，见 test_render_view_directive）。
    """
    from domain.meeting.tasks.minutes.contracts import MINUTES_GENERATION_OUTPUT_CONTRACT
    from domain.meeting.tasks.minutes.prompts import (
        MINUTES_GENERATION_SYSTEM_PROMPT as GEN,
        MINUTES_SUPERVISOR_DOMAIN_PROMPT as REVIEW,
    )

    check("契约：真人模式草稿即产出组名行（与我相关 / 每位他人一行）；客观口径不变",
          "先给一个组名元素 `**与我相关**：`" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "他人每位各给一个组名元素 `**姓名**：`" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "条目不重复姓名" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "确需他配合的合并成一句" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "客观/职业模板按有明确责任人的分工条数写" in MINUTES_GENERATION_OUTPUT_CONTRACT,
          "")
    check("契约：结论与决定同口径分组（本人「与我相关」/ 他人「姓名」/ 无归属平铺）",
          "key_decisions" in MINUTES_GENERATION_OUTPUT_CONTRACT  # 字段名在契约里
          and "**上游 decisions 是纯文本、没有归属，要对照会议原文补出归属**"
          in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "归属本人的先写一行 `**与我相关**：` 再列其条目" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "归属他人的写一行 `**姓名**：` 再列其条目" in MINUTES_GENERATION_OUTPUT_CONTRACT,
          "")
    check("契约：同为决策的写法不再用「我的事项」旧名（三栏统一组名）",
          "我的事项" not in MINUTES_GENERATION_OUTPUT_CONTRACT,
          "")
    # 旧组名漂移守护：组名只在「与我相关」一处口径里——任何一份 prompt 源文件残留
    # 「我的事项」都会让模型在旧名/新名之间二选一（上次的教训：两处口径打架，模型照旧的写）。
    stale_group = [
        str(path)
        for path in (
            Path("domain/meeting/tasks/minutes/contracts.py"),
            Path("domain/meeting/tasks/minutes/prompts.py"),
            Path("perspective/preferences.py"),
            Path("perspective/hits.py"),
            Path("tools/templates/body_rules.py"),
        )
        if "我的事项" in path.read_text(encoding="utf-8")
    ]
    check("旧组名「我的事项」已在全部 prompt 源文件清除", not stale_group, f"残留={stale_group}")
    check("契约：风险/未决「有明确归属才分组」，分组写法自述；客观口径保留",
          "风险（客观全量" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "**有明确归属才分组**" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "**分组写法**：" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "看不出归属的不写姓名、平铺在最前" in MINUTES_GENERATION_OUTPUT_CONTRACT,
          "")
    check("契约：不再用「与某栏一致」的交叉引用（换模板/改栏名也不会被带偏）",
          "与行动项一致" not in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "与风险栏一致" not in MINUTES_GENERATION_OUTPUT_CONTRACT,
          "")
    check("提示词字段小节：条数口径分档（客观/职业=分工数；真人=命中表里他的待办数）",
          "条数 = 有明确责任人 + 明确职责的分工数**（客观/职业模板）" in GEN
          and "条数 = 命中表里他的待办数）" in GEN
          and "**不写自己的姓名**" in GEN
          and "按姓名分组" in GEN,
          "")
    check("草稿真人视角段：自己的在前不写姓名、他人的带姓名前缀，未命中写 []",
          "不写自己的姓名**" in GEN and "命中表没给他派活时自己的部分写 []" in GEN, "")
    check("审核：两种归属形态都接受，但归属必须可核、组名行须与条目对应",
          "末尾三栏（结论与决定 / 行动项与分工 / 待确认与风险）必须**按人分块**" in REVIEW
          and "组名与组内条目必须对应" in REVIEW
          and "他自己的条目**不得写自己的姓名**" in REVIEW,
          "")
    check("审核：有明确归属却未标出要拦、无归属不加姓名不算缺陷（条件句）",
          "**分工归属（真人模式）**" in REVIEW
          and "有明确归属却未标出" in REVIEW
          and "无归属的全局项不加姓名是允许的" in REVIEW
          and "客观/职业模板按有明确责任人的分工条数写，不按本条拦" in REVIEW,
          "")
    check("审核：正当依赖不算（避免误拦）", "上游出包后才能联调」这类正当依赖不算" in REVIEW, "")
    check("提示词里不留任何真实人名示例（全局提示词不得锚定到某个用户）",
          all(name not in MINUTES_GENERATION_OUTPUT_CONTRACT + GEN + REVIEW
              for name in ("申家坤", "徐玥", "武思华", "陈贺")),
          "")


def test_render_context_personal_injection() -> None:
    """装配那一轮也要拿到命中块/偏好块 + 渲染提示词的"真人聚焦"口径。

    回归背景（2026-09-21 用户实测）：草稿那轮有命中块/偏好块，但**逐栏填充（真正写正文
    的地方）**没有——它看不到"他是谁、他关心什么"，于是把个人视角摊回整场，读起来与
    客观没区别。这里锁住：命中块进所有非客观线、偏好块只进纪要线；渲染提示词写明聚焦口径。
    """
    from domain.meeting.orchestrator import _Nodes
    from domain.meeting.tasks.minutes.prompts import MINUTES_RENDER_PROMPT

    class _Host(_Nodes):
        """只借方法；用真实 _render_context，其余依赖最小化。"""

        def __init__(self) -> None:
            pass

        def _meeting_pack(self, state, line_name):
            return {"meeting_purpose": "进展"}

        def _compact_user(self, user):
            return dict(user)

        def _compact_perspective(self, profile):
            return dict(profile or {})

        def _length_budget_line(self, state, line_name):
            return ""

        def _mode_label(self, state):
            return "objective" if state.get("objective_perspective") else "personal"

    hits = "【本用户命中（程序判定，带依据）】申家坤：命中 1 处。\n- [强] action_hints[0].owner：细对口径"
    state = {
        "transcript": "申家坤：我下来找他们细对一下。",
        "meeting_understanding": {"meeting_purpose": "进展"},
        "user": {"name": "申家坤", "preferences": ["先写我负责的待办"]},
        "user_hits_block": hits,
        "perspective_profile": {"personal_summary": "与本场相关：口径细对。"},
        "objective_perspective": False,
        "line_extra": {},
        "lines": {"minutes": {"draft": {"headline": "进展"}, "review": {}}},
    }
    host = _Host()
    for line, want_pref in (("minutes", True), ("minutes_styles", True), ("actions", False), ("risks", False)):
        text = host._render_context(state, line)
        check(f"渲染上下文（{line}）：命中块（非客观线都有）",
              "本用户命中" in text, text[-160:])
        check(f"渲染上下文（{line}）：偏好块 {'有' if want_pref else '不注入'}",
              ("本用户偏好" in text) is want_pref, text[-160:])
    objective = host._render_context({**state, "objective_perspective": True, "user": {"perspective": "objective"}}, "minutes")
    check("渲染上下文（客观）：命中块与偏好块都不注入",
          "本用户命中" not in objective and "本用户偏好" not in objective, "")

    check("渲染提示词：真人模式以本人为叙事主线（非相关板块可压缩）",
          "真人模式聚焦" in MINUTES_RENDER_PROMPT
          and "以本人为叙事主线" in MINUTES_RENDER_PROMPT
          and "可压缩成一句带过" in MINUTES_RENDER_PROMPT, "")
    check("渲染提示词：真人聚焦不得漏全局结论（与审核口径对齐）",
          "影响全局的结论、范围纳入/排除、关键数字仍不得漏" in MINUTES_RENDER_PROMPT, "")
    check("渲染提示词：给了命中表就以它为准",
          "以它为准" in MINUTES_RENDER_PROMPT
          and "未命中的条目不要写成他的事" in MINUTES_RENDER_PROMPT, "")


def test_render_view_directive() -> None:
    """装配那一轮的「本视角纪律」：模板路径正文是通用填充器逐栏写的，纪律必须随栏下发。

    回归背景（2026-09-21 用户第二轮实测「还是整体输出」）：上一版把聚焦规则写进
    ``MINUTES_RENDER_PROMPT``，但**带模板时那条路根本不执行**——逐栏填充的 system 只有
    「你只写本栏正文」，正文只按模板栏名（全文摘要 / 分段速览）走，于是真人模式照样写成
    整场纪要（实测 8172 字、超本篇参考上限 48%，与客观版看不出区别）。这里锁住：
    纪律进每一栏的用户消息、经领域钩子只在真人纪要线生效、客观与其它线一字不变。
    """
    import asyncio

    from domain.meeting.orchestrator import _Nodes
    from perspective import PERSONAL_VIEW_DIRECTIVE, VIEW_DIRECTIVE_TITLE
    from tools.templates.router import fill_placeholder_template
    from tools.templates.router._placeholder import _column_fill_user

    template = "# 通用纪要\n\n# [全文摘要]\n[一段话概括]\n\n# [要点梳理]\n[分点列具体事实]\n"
    mark = f"【{VIEW_DIRECTIVE_TITLE}】"

    class _Stub:
        """只记 (system, user)，不调 LLM。"""

        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def stream_text(self, system_prompt, user_prompt, **kwargs):
            self.calls.append((system_prompt, user_prompt))
            yield "本栏正文（占位）。"

        async def text(self, system_prompt, user_prompt, **kwargs):
            self.calls.append((system_prompt, user_prompt))
            return '{"fields": {"1": "x", "2": "y"}, "tables": []}'

    class _Host(_Nodes):
        def __init__(self) -> None:
            pass

    stub = _Stub()
    asyncio.run(
        fill_placeholder_template(
            stub, "来源", template, source_han=9000, directives=PERSONAL_VIEW_DIRECTIVE
        )
    )
    check("逐栏填充：每一栏的用户消息都带本视角纪律",
          bool(stub.calls) and all(mark in user for _, user in stub.calls),
          str([user.splitlines()[0] for _, user in stub.calls]))
    check("逐栏填充：system 里没有领域渲染提示词（这正是要向用户消息下发纪律的原因）",
          all("真人模式聚焦" not in system for system, _ in stub.calls), "")

    host = _Host()
    personal = {"user": {"name": "申家坤"}}
    check("钩子：真人纪要线（minutes / minutes_styles）→ 有纪律",
          mark in host._render_directives(personal, "minutes")
          and mark in host._render_directives(personal, "minutes_styles"), "")
    check("钩子：客观、非纪要线、职业模板 → 都不注入",
          host._render_directives({**personal, "objective_perspective": True}, "minutes") == ""
          and host._render_directives(personal, "actions") == ""
          and host._render_directives(
              {"user": {"persona_type": "role_template", "name": "开发人员"}}, "minutes"
          ) == "",
          "")

    from perspective import PERSONAL_TEMPLATE_VIEW_DIRECTIVE
    personal_custom = {
        "user": {"name": "申家坤"},
        "templates": {"minutes": "# [本场概况与本人定调]\n[说明]\n"},
    }
    check(
        "钩子：真人模式 + 专属个人模板 → 注入 PERSONAL_TEMPLATE_VIEW_DIRECTIVE",
        host._render_directives(personal_custom, "minutes") == PERSONAL_TEMPLATE_VIEW_DIRECTIVE,
        host._render_directives(personal_custom, "minutes")[:60],
    )
    check(
        "钩子：真人模式 + 通用模板 → 注入通用纪律 PERSONAL_VIEW_DIRECTIVE",
        host._render_directives(personal, "minutes") == PERSONAL_VIEW_DIRECTIVE,
        "",
    )
    check(
        "钩子：客观模式 + 专属个人模板 → 绝不注入（客观纪要 100% 零影响）",
        host._render_directives({**personal_custom, "objective_perspective": True}, "minutes") == "",
        "",
    )

    user = _column_fill_user(
        "来源", template, index=1, total=2, hint="一段话概括", title="全文摘要",
        others=["要点梳理"], directives=PERSONAL_VIEW_DIRECTIVE,
    )
    check("纪律排在【本栏说明】之后、【内容来源】之前",
          user.index("【本栏说明】") < user.index(mark) < user.index("【内容来源】"), "")
    check("纪律为空 → 不出现该段（客观路径一字不变）",
          mark not in _column_fill_user(
              "来源", template, index=1, total=2, hint="一段话概括", title="全文摘要",
              others=["要点梳理"], directives="",
          ),
          "")
    check("纪律自带优先级：模板写「客观、非人格化」时人称与取舍以纪律为准",
          "人称与取舍以本纪律为准" in PERSONAL_VIEW_DIRECTIVE
          and "栏名、结构与事实口径照模板不变" in PERSONAL_VIEW_DIRECTIVE, "")
    check("纪律含六条硬口径（相关=点名 / 聚焦 / 不漏全局 / 人名口径 / 命中表为准 / 不留空栏）",
          all(
              clause in PERSONAL_VIEW_DIRECTIVE
              for clause in (
                  "相关＝点名，不是「属于他的关注领域」",
                  "以本人为叙事主线",
                  "别人主讲、且与他无关的板块压成一句带过",
                  "关键数字仍**不得漏**",
                  "本人动作省主语",
                  "他人动作写真名",
                  "同一句与相邻两句不混用",
                  "以它为准",
                  "不要留空栏",
                  "已按人裁剪",
              )
          ),
          "")


def test_render_context_person_transcript() -> None:
    """真人模式的渲染上下文：会议原文按人裁剪（别人发言折叠），客观路径原样整篇。

    为什么非裁不可（2026-09-21 实测）：纪律写进消息开头（691 字）也压不过眼前的整场原文，
    真人模式照样输出整场（提及他的段落只占 12%、正文 9082 字）。裁掉别人的发言后同一份输入
    降到 6266 字，全文摘要出现「与你直接相关的是…」，且 930 节点/单卡四路等全局结论仍在。
    """
    from domain.meeting.orchestrator import _Nodes

    transcript = (
        "项目会\n"
        "申家坤 00:00:01\n" + "我们先过接口这块的对齐情况，把上周遗留的两条也一起带上。" * 4 + "\n"
        "武思华 00:00:10\n" + "这个问题由我来跟，细节我明天说清楚。" * 6 + "\n"
        "申家坤 00:00:40\n" + "小坤这边的权限单我提了，回流数据表也要一起加上。" * 4 + "\n"
        "武思华 00:00:50\n" + "另外引擎那部分我一起讲一下大概情况。" * 6 + "\n"
        "李梦甜 00:01:10\n申家坤那边的双录还没确认。\n"
    )

    class _Host(_Nodes):
        def __init__(self) -> None:
            pass

        def _meeting_pack(self, state, line_name):
            return {}

        def _compact_user(self, user):
            return dict(user)

        def _compact_perspective(self, profile):
            return {}

        def _length_budget_line(self, state, line_name):
            return ""

    host = _Host()
    state = {
        "transcript": transcript,
        "user": {"name": "申家坤", "name_aliases": ["小坤"]},
        "meeting_understanding": {},
        "perspective_profile": {},
        "objective_perspective": False,
        "line_extra": {},
        "lines": {"minutes": {"draft": {}, "review": {}}},
    }
    sliced = host._render_context(state, "minutes")
    check("真人：原文块改标为「已按人裁剪」", "会议原文（真人模式·已按人裁剪）" in sliced, "")
    check("真人：别人的段被折叠（原文里那些长段不见了）",
          "另外引擎那部分我一起讲一下大概情况" not in sliced
          and "这个问题由我来跟，细节我明天说清楚。" not in sliced, "")
    check("真人：他自己的段留下且块首改称「你」",
          "你 00:00:01" in sliced and "我们先过接口这块的对齐情况" in sliced, sliced[:120])
    check("真人：提到他的别人的段也留（引述保真名）",
          "李梦甜 00:01:10" in sliced and "双录还没确认" in sliced, "")
    check("真人：非纪要线（trace/mindmap）不动原文",
          "已按人裁剪" not in host._render_context(state, "minutes_trace"), "")

    objective = host._render_context({**state, "objective_perspective": True}, "minutes")
    check("客观：整篇原文原样、无裁剪标记",
          "已按人裁剪" not in objective and "另外引擎那部分我一起讲一下大概情况" in objective, "")

    # 分组骨架块（2026-09-22）：把「要出现哪些组名行」变成可照抄的清单——模型只复制、不重排。
    grid = {**state, "user_action_groups_block": "【本用户分栏分组骨架】\n**与我相关**："}
    check("真人渲染上下文注入「分栏分组骨架」块",
          "**与我相关**：" in host._render_context(grid, "minutes"), "")
    check("客观不注入骨架块（零外溢）",
          "**与我相关**：" not in host._render_context(
              {**grid, "objective_perspective": True}, "minutes"
          ),
          "")
    # 状态通道守护（2026-09-22 真链路事故）：LangGraph 只传 MeetingState 里声明过的 key，
    # 未声明的写入被静默丢掉——骨架块写了，草稿/审核/渲染全程收不到（单元测试注入 dict 掩盖了）。
    from domain.meeting.models import MeetingState

    check("状态通道：视角节点写的两个块都在 MeetingState 里声明（否则被 LangGraph 丢掉）",
          "user_action_groups_block" in MeetingState.__annotations__
          and "user_hits_block" in MeetingState.__annotations__,
          "")
    check("状态通道：视角节点确实写入骨架 key",
          "user_action_groups_block" in Path("domain/meeting/orchestrator.py").read_text(
              encoding="utf-8"
          ),
          "")

    # 素材裁剪（2026-09-21 追加）：理解包里"别人为主语"的条目在真人装配轮去掉——
    # 实测「行动项与分工」栏会把 key_points 直接变成条目（157 条里 49 条以别人为主语），
    # 纪律压不住素材；裁完同一份输入的分工栏 8/8 都是他的条目（原来 5/8）。
    pack = {
        "meeting_brief": "进展",
        "topics": [
            {
                "title": "长文本",
                "discussion": "武思华提出先测接口，徐玥要求本周出结论，讨论集中在人力上",  # 别人为主 → 裁
                "key_points": [
                    "长文本实测 8~9 万字不行，手头最大 40 多秒",   # 无人称全局事实 → 留
                    "申家坤回去改配置，明天给结论",                  # 点名他 → 留
                    "武思华明天找他们要数据，看能不能要到",          # 别人为主语 → 裁
                    "徐玥要求 930 前至少单卡四路",                   # 别人为主语 → 裁
                ],
            },
            {
                "title": "引擎并发",
                "discussion": "申家坤讲了长文本实测情况，其他人补充",  # 提到他 → 留
                "key_points": ["申家坤负责压测"],
            },
        ],
        "decisions": ["930 前至少单卡四路"],
        "risks": ["武思华找对方批权限一直不批"],
    }
    pack_state = {
        **state,
        "meeting_understanding": {
            "speakers": [{"name": "申家坤"}, {"name": "武思华"}, {"name": "徐玥"}]
        },
    }
    trimmed_pack = host._person_pack(pack, pack_state)
    check("素材裁剪：别人为主语的条目去掉，他的与无人称全局事实都留",
          len(trimmed_pack["topics"][0]["key_points"]) == 2
          and "长文本实测 8~9 万字不行" in trimmed_pack["topics"][0]["key_points"][0]
          and "申家坤回去改配置" in trimmed_pack["topics"][0]["key_points"][1],
          str(trimmed_pack["topics"][0]["key_points"]))
    check("素材裁剪：decisions / risks 不动（全局结论与风险仍进上下文）",
          trimmed_pack["decisions"] == ["930 前至少单卡四路"]
          and trimmed_pack["risks"] == ["武思华找对方批权限一直不批"], "")
    check("素材裁剪：别人为主的「议题讨论经过」同样去掉（2026-09-22 追加）",
          trimmed_pack["topics"][0]["discussion"] == ""
          and trimmed_pack["topics"][1]["discussion"] == "申家坤讲了长文本实测情况，其他人补充",
          f"{[tp.get('discussion') for tp in trimmed_pack['topics']]}")
    check("素材裁剪：客观档与职业模板都不裁（原样返回，含讨论经过）",
          len(host._person_pack(pack, {**pack_state, "objective_perspective": True})["topics"][0]["key_points"]) == 4
          and host._person_pack(
              pack, {**pack_state, "objective_perspective": True}
          )["topics"][0]["discussion"].startswith("武思华提出")
          and len(host._person_pack(
              pack, {**pack_state, "user": {"name": "开发人员", "persona_type": "role_template"}}
          )["topics"][0]["key_points"]) == 4, "")

    role = host._render_context(
        {**state, "user": {"name": "开发人员", "persona_type": "role_template"}}, "minutes"
    )
    check("职业模板：没有真人姓名可裁 → 走整篇",
          "已按人裁剪" not in role, "")

    check("裁不动时退回空串（调用方用整篇）：无关姓名",
          host._person_transcript({**state, "user": {"name": "查无此人"}}) == "", "")


def main() -> int:
    caplog_records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            caplog_records.append(record)

    handler = _Collect()
    logging.getLogger("tools.templates.router._gate").addHandler(handler)
    logging.getLogger("tools.templates.router._gate").setLevel(logging.WARNING)

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
        test_table_carried_column_allows_blank()
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
        test_home_school_feedback_groups()
        test_group_headings_need_body()
        test_debate_side_attribution_and_fabrication()
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
        test_column_fill_overlong_item_rewrite()
        test_personal_risk_attribution_in_pack()
        test_media_overview_scope()
        test_class_transcript_task_groups()
        test_quote_columns_have_background()
        test_ellipsis_table_row_template_recognized()
        test_table_row_bracket_not_split_as_field()
        test_lecture_evidence_cap()
        test_first_column_single_paragraph_merge()
        test_court_claims_table_both_sides()
        test_output_volume_and_hierarchy()
        test_subjective_judgment_guardrails()
        test_media_briefing_evidence_and_depth()
        test_qa_name_priority()
        test_understanding_speakers_field()
        test_understanding_user_channel()
        test_perspective_skip_for_personal()
        test_personal_no_full_fallback()
        test_person_reference_rules()
        test_render_context_personal_injection()
        test_render_view_directive()
        test_assignment_scope_rules()
        test_render_context_person_transcript()
        test_product_launch_overview()
        test_retro_annual_groups()
        test_domain_specific_accuracy_rules()
        test_fallback_text_dedupe()
        test_supervisor_contract_and_unavailable()
    finally:
        logging.getLogger("tools.templates.router._gate").removeHandler(handler)

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项：" + "，".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
