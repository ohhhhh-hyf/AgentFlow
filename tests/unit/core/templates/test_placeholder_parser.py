# 拆分自原大文件，保留：test_iter_placeholders, test_line_placeholders_filters_noise, test_parser_sees_field_not_text…

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

def test_iter_placeholders() -> None:
    """行级优先：整行 `[...]` 即使内含方括号字面也按一个占位；多对括号仍逐对。"""
    nested = "[明确家校达成的共识、后续配合措施及跟进计划，用 `- [ ]` 待办格式列出双方分工]"
    got = iter_placeholders(nested)
    expect(len(got) == 1 and got[0].group(1).startswith("明确家校达成的共识") and "- [ ]" in got[0].group(1), "整行占位（说明里带 `- [ ]` 字面）→ 1 个占位且内容为整句", f"n={len(got)}")
    expect(len(got) == 1 and nested[got[0].start() : got[0].end()] == nested, "行级占位的位置覆盖整行（供 next_char/切片用）", f"span={got[0].span() if got else None}")
    pair = iter_placeholders("[A] 与 [B]")
    expect(len(pair) == 2 and [m.group(1) for m in pair] == ["A", "B"], "一行两对括号仍逐对匹配（不回退成整行吞掉）", f"{[m.group(1) for m in pair]}")
    two_lines = "第一行 [甲]\n第二行 [乙]"
    spans = iter_placeholders(two_lines)
    expect(len(spans) == 2
          and two_lines[spans[0].start() : spans[0].end()] == "[甲]"
          and two_lines[spans[1].start() : spans[1].end()] == "[乙]", "多行时位置仍相对整段（跨行偏移正确）", f"{[m.span() for m in spans]}")
    for raw in ("| [维度] | … |", "- [具体内容描述]", "# [栏目标题]", "段落里的 [小括号] 说明"):
        m = iter_placeholders(raw)
        expect(len(m) >= 1, f"常规行不受影响：{raw[:22]}", f"n={len(m)}")


def test_line_placeholders_filters_noise() -> None:
    """`_line_placeholders` 仍过滤掉不像占位符的括号（JSON/链接残留）。"""
    from core.templates.router._placeholder import _line_placeholders

    expect(_line_placeholders("[x]") == [], "不像占位符的整行括号被过滤（如 `[x]`）", "")
    expect(len(_line_placeholders("[一段话概括会议主要内容与结论]")) == 1, "像占位符的说明行被保留", "")


def test_parser_sees_field_not_text() -> None:
    """含字面 `[ ]` 的说明行应解析成**字段**，而不是固定文字段。"""
    tpl = (
        "# [沟通概况]\n[一段话概括沟通双方与主题]\n\n"
        "# [共识与配合事项]\n[明确家校共识与分工，用 `- [ ]` 待办格式列出双方分工]\n"
    )
    segs = parse_placeholder_template(tpl)
    kinds = [s["kind"] for s in segs]
    expect(kinds.count("field") == 2, "说明行解析为字段（不再是 text 段）", f"kinds={kinds}")
    expect(scan_fixed_bracket_literals(tpl) == [], "固定段里不再出现带方括号的说明", f"{scan_fixed_bracket_literals(tpl)}")


def test_prompt_allows_sub_headings() -> None:
    """渲染规则（PLACEHOLDER_RULES/BODY_FORMAT_RULES）允许字段值内用下级标题分板块，只禁与栏目标题同名/同级。

    背景：模板里「二级标题写成员/模块」「多层级结构」这类说明，原先被 prompt 的
    "不要写 Markdown 标题（# / ##）"一刀切挡住 → 改成"只禁同级 `#`、允许 `##`/`###`"后两边口径一致。
    """
    from core.templates.body_rules import BODY_FORMAT_RULES
    from core.templates.template_prompt import PLACEHOLDER_RULES

    prompt = PLACEHOLDER_RULES
    expect("并列事项按业务或大类分组" in prompt and "三级/四级小节" in prompt,
           "模板规则允许按业务分组与多级小节", "")
    expect("不要写 Markdown 标题" not in prompt, "模板规则不再一刀切禁止写标题", "")
    expect("人名不作标题" in prompt, "仍保留「人名不作标题」保护", "")


def test_placeholder_rules_resolve_title_bracket_conflict() -> None:
    """回归：第 1 条不能再写“标题原样保留”，否则与第 2 条“去掉方括号”打架。"""
    from core.templates.template_prompt import (
        PLACEHOLDER_RULES,
        build_template_render_prompt,
    )

    assert "只替换方括号内的占位内容" in PLACEHOLDER_RULES
    assert "标题行例外" in PLACEHOLDER_RULES
    assert "标题行不得出现 [ ]" in PLACEHOLDER_RULES
    assert "固定文字、标题、表头、分隔行原样保留" not in PLACEHOLDER_RULES

    prompt = build_template_render_prompt(
        renderer="渲染器",
        source="草稿",
        empty_rule="空值",
    )
    assert "占位符模板的标题文字按占位规则去掉方括号" in prompt


def test_buggy_template_now_works() -> None:
    """两条历史坏损模板（模板文件未改也应被代码修复救回）：末栏恢复为字段。"""
    tdir = _active_dir()
    for tid in ("home_school_liaison", "legal_advisory"):
        p = tdir / f"{tid}.md"
        if not p.is_file():
            continue
        fmt, _ = split_template_meta(p.read_text(encoding="utf-8"))
        hints = [str(s.get("raw")) for s in plan_placeholder_fill(fmt)["scalars"]]
        ok = len(hints) >= 4 and bool(hints[-1].strip())
        expect(ok, f"{tid}：末栏仍是可填字段（不再退化成固定文案）", f"字段数={len(hints)}")


def test_placeholder_route_rules() -> None:
    """Fast Render 路由层：对占位符模板自动判定并下发 PLACEHOLDER_RULES 完整规则契约。"""
    from core.templates.router import route_template

    routed = route_template("内容来源：略。", FILL_TPL, "无模板系统提示", "模板基础提示\n")
    expect(routed is not None, "route_template 正确分派占位符模板", "")
    if routed is not None:
        sys_prompt, user_msg = routed
        expect("模板基础提示" in sys_prompt and "占位符模板" in sys_prompt, "系统提示词包含模板基础规则与 PLACEHOLDER_RULES", "")
        expect("并列事项按业务或大类分组" in sys_prompt, "系统提示词包含形态排版规则", "")
        expect("内容来源：略。" in user_msg and "模板原文：" in user_msg, "用户消息包含内容来源与模板原文", "")
        expect("【待处理业务素材】" in user_msg and "【交付执行令】" in user_msg, "用户消息包含待处理业务素材与交付执行令", "")


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
    expect(len(plan["scalars"]) == 2 and len(plan["row_templates"]) == 1, "表格栏说明不进字段清单（甲/乙两栏 + 1 张表）", f"{hints}")
    expect(table_caption_lines(CAPTION_TPL) == {4}, "紧跟表格的说明行被判为表格栏说明", f"{table_caption_lines(CAPTION_TPL)}")
    expect(not is_table_caption("医嘱清单：检查安排、用药各占一条，每条都是 `- ` 分点行")
          and table_caption_lines(BODY_CAPTION_TPL) == set(), "要求正文的医嘱清单不被误判（要 `- ` 分点）", f"{table_caption_lines(BODY_CAPTION_TPL)}")

    out = assemble_placeholder_output(
        CAPTION_TPL, {"1": "甲内容。", "2": "乙内容。"}, tables=[[["模块A", "进行中"]]]
    )
    expect("按下表逐行填写" not in out and "模块A" in out, "拼装：说明行不打印、表格照常输出", "")
    expect("未提及" not in out, "拼装：不产生「未提及」正文", f"{out!r}")
    expect("# 乙栏\n乙内容。" in out.replace("\r\n", "\n"), "拼装：后面的字段不错位（乙栏拿到自己的值）", f"{out!r}")
