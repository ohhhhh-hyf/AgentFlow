# 拆分自原大文件，保留：test_table_carried_column_allows_blank, test_progress_table_rows, test_strip_default_only_content…

"""tests/unit/core/templates/test_section_pruner.py -- 模板装配器、自适应隐去与 SectionPruner 单元测试。"""

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

def test_table_carried_column_allows_blank() -> None:
    """表格承载栏允许为空：拼装产物不强填缺省词、表格内容照常装配。"""
    from core.templates.router._placeholder import assemble_placeholder_output

    tpl = (
        "# [候选人概况]\n[一段话概括候选人]\n\n"
        "# [能力评估]\n[**本栏明细由下表承载**（本栏不再另写说明文字、不要写「未提及」）]\n"
        "| 评估维度 | 评级 |\n| --- | --- |\n| [维度] | [评级] |\n"
    )
    out = assemble_placeholder_output(
        tpl,
        {"1": "候选人概况内容。", "2": ""},
        tables=[[["综合分析", "良"]]],
    )
    expect(bool(out) and "未提及" not in (out or ""), "表格承载栏为空 ⇒ 终稿不含「未提及」", (out or "")[:100])
    expect("综合分析" in (out or ""), "表格内容照常装配", (out or "")[:140])


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
        expect(need in text, f"项目进度会：含「{need}」", "")
    expect("应拆成" not in text and "五行" not in text, "项目进度会：不夹带示例式软引导（如「应拆成 … 五行」）", "")
    from core.templates.body_rules import BODY_FORMAT_RULES

    expect("状态标记（已完成 / 进行中 / 未开始 / 阻塞）仅在模板要求时出现一次" in BODY_FORMAT_RULES, "共用形态规则的状态标记口径保留（无 emoji）", "")


def test_strip_default_only_content() -> None:
    """只有缺省词的内容不展示：表格整行 / 正文整条 / 独立缺省句；整栏缺省则保留一行。

    回归背景（2026-09-18 用户实测）：就医咨询的药表出现整行「未明确」（模板声明的缺省词是
    「未明确」而 `_row_nonempty` 的空集里没有它）→ 被当数据行原样展示；同期还有 3 条
    `- **过敏史**：未提及。` 与 4 处"整栏只有未提及"。用户口径：这类内容不展示，
    但"整栏都没有"要保留一行缺省词（"没有"本身是信息）。
    """
    from core.execution.gate import (
        _item_default_only,
        _row_nonempty,
        apply_table_row_limits,
        enforce_render_output,
        gate_render_output,
        strip_default_only_content,
    )

    expect(not _row_nonempty("| 未明确 | 未明确 | 未明确 | 未明确 | 未明确 |"), "全缺省表行判为空（含模板缺省词「未明确」）", "")
    expect(not _row_nonempty("| 未提及 | — | — | — | — |"), "全未提及表行判为空", "")
    expect(_row_nonempty("| 奥美拉唑 | 未明确 | 口服 | 未明确 | 效果不佳 |"), "有内容的表行不算空", "")
    expect(_item_default_only("- **过敏史**：未提及。") and _item_default_only("- **个人史**：未提及"), "整条只有缺省词（`- **X**：未提及。`）被识别", "")
    expect(not _item_default_only("- **现病史**：2023年9月确诊。"), "有内容的条目不算缺省", "")

    doc = (
        "# 就医咨询\n\n## 就诊概况\n- **现病史**：2023年9月确诊。\n"
        "- **过敏史**：未提及。\n- **家族史**：未提及。\n\n"
        "## 病史信息\n- **过敏史**：未提及。\n\n"
        "## 诊断结果\n- **诊断**：待查。\n\n"
        "## 治疗方案\n- **检查安排**：建议做第二次基因检测。\n"
        "- **用药**：系统治疗包括化疗、靶向、免疫。\n\n"
        "| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |\n| --- | --- | --- | --- | --- |\n"
        "| 未明确 | 未明确 | 未明确 | 未明确 | 未明确 |\n\n"
        "## 预警信号\n未提及。\n"
    )
    out, notes = strip_default_only_content(doc)
    expect("- **过敏史**" not in out and "- **现病史**" in out and "- **检查安排**" in out, "整条缺省被删、有内容的条目保留", "")
    expect("| 未明确 | 未明确 | 未明确 | 未明确 | 未明确 |" in out and "| 药品名称 |" in out, "整表全缺省 → 保留首行缺省数据行（不再把表删空）", "")
    expect("## 预警信号\n未提及" in out, "整节只有缺省词 → 保留标题 + 一行缺省词", "")
    expect(bool(notes) and "已省略" in notes[0], "删除有记录（notes 记数）", f"{notes}")

    raw = (_active_dir() / "clinical_advisory.md").read_text(encoding="utf-8")
    gate = gate_render_output(raw, out)
    # 2026-09-19 起反转：整表缺省是**合法形态**（原文本就没有药品明细），保留首行缺省数据行后
    # 不再报「表格无有效数据行」。旧口径让这条硬伤无法修复（源里没有数据可填），
    # 实测 就医咨询 单次渲染 10 次 LLM 调用、整单 115.8s 后仍降级。
    expect("表格无有效数据行" not in gate["issues"] and not gate["hard_issues"], "整表缺省不再产生「表格无有效数据行」硬伤", f"hard={gate['hard_issues']} issues={gate['issues']}")

    blank = (
        "# 就医咨询\n\n## 就诊概况\n概况。\n\n## 病史信息\n病史。\n\n## 诊断结果\n诊断。\n\n"
        "## 治疗方案\n- **全身系统治疗**：核心是全身系统治疗。\n"
        "| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |\n| --- | --- | --- | --- | --- |\n\n"
        "## 预警信号\n预警。\n"
    )
    fixed_t, notes_t, issues_t = enforce_render_output(raw, blank)
    expect(not issues_t and "| 未提及 | — | — | — | — |" in fixed_t, "空表全流程：写入缺省占位行且零硬伤（原文本就没有药品明细时的出口）", f"{issues_t} {notes_t}")
    glued, n_glued = apply_table_row_limits(blank.rstrip("\n"), raw)
    expect("| 未提及 | — | — | — | — |" in glued.splitlines(), "表格在文末且无末尾换行时，占位行也独立成行（不粘连分隔行）", f"{n_glued} {glued.splitlines()[-1]!r}")

    for stem, bad in (
        ("clinical_advisory", "一律写「未明确」"),
        ("decision_review", "缺项直接写「未明确」"),
        ("project_progress", "缺项直接写「无」"),
        ("contract_vetting", "缺则写「无」"),
    ):
        txt = (_active_dir() / f"{stem}.md").read_text(encoding="utf-8")
        expect(bad not in txt, f"{stem}：不再要求逐项标缺省词", "")


def test_fallback_text_dedupe() -> None:
    """降级拼装：headline 与文档标题重复时不再重复输出；「；」连接不再出现「。；」。"""
    from domains.meeting.tasks.minutes.contracts import MinutesFallbackRules
    from core.graph.engine_text import fallback_text

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
    expect(text.count(headline) == 0, "降级文本不再重复文档标题（headline 去重）", f"{text[:40]!r}")
    expect("。；" not in text and "；" in text, "多项用「；」连接、不出现「。；」", f"{text!r}")
    text2, _ = fallback_text(state, "minutes", MinutesFallbackRules, {}, lambda s: "", "", title="别的标题")
    expect(text2.startswith(headline), "标题不同时仍保留 headline", f"{text2[:24]!r}")


def test_table_isolation_and_deduplication() -> None:
    """支柱 1 与支柱 3 验证：形态 A 纯表格栏识别、形态 B 复合栏表格隔离纪律、标量去表与表头行数据去重。"""
    from core.templates.router._base import is_table_caption
    from core.templates.router._placeholder import (
        _strip_markdown_tables,
        _section_has_table,
        _column_fill_user,
        assemble_placeholder_output,
        normalize_fill_tables,
    )

    # 1. _strip_markdown_tables 单元测试
    raw_with_trailing_table = (
        "1. **用药说明**：阿莫西林 1.2g 口服。\n"
        "2. **复诊建议**：3天后复查。\n\n"
        "| 药品 | 剂量 | 用法 |\n"
        "| --- | --- | --- |\n"
        "| 阿莫西林 | 1.2g | 口服 |\n"
    )
    stripped = _strip_markdown_tables(raw_with_trailing_table)
    expect("| 药品 |" not in stripped and "2. **复诊建议**" in stripped, "标量末尾私自绘制的 Markdown 表格被干净剥离", f"{stripped}")

    # 防线 3：条目列表内部（中间）潜伏表格的物理挖除与前后正文缝合（对标 1b6b7876）
    raw_with_middle_table = (
        "1. **检查安排**：留大便查潜血。\n"
        "2. **复诊安排**：汇报医生。\n\n"
        "| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 斯达舒 | — | 每日四五次 | 口服 | 初有效后效果不佳 |\n"
        "| 奥美拉唑 | — | — | 口服 | 武汉药厂生产 |\n\n"
        "3. **生活方式与饮食**：戒烟戒酒。"
    )
    stripped_mid = _strip_markdown_tables(raw_with_middle_table)
    expect("| 药品名称 |" not in stripped_mid
          and "2. **复诊安排**" in stripped_mid
          and "3. **生活方式与饮食**" in stripped_mid, "标量条目中间潜伏的 Markdown 表格被物理挖除且前后条目自然缝合", f"{stripped_mid}")

    raw_with_leading_table = "| 类别 | 内容 |\n| --- | --- |\n| A | B |\n\n正文要点内容"
    stripped_lead = _strip_markdown_tables(raw_with_leading_table)
    expect("| 类别 |" not in stripped_lead and stripped_lead == "正文要点内容", "标量开头私自绘制的 Markdown 表格被物理剥离", f"{stripped_lead}")

    text_with_inline_pipe = "- **责任人**：张三 | 组长\n- **说明**：普通文本含管道符"
    kept_pipe = _strip_markdown_tables(text_with_inline_pipe)
    expect(kept_pipe == text_with_inline_pipe.strip(), "正文中非表格的管道符文字完整保留", f"{kept_pipe}")

    only_table = "| 列1 | 列2 |\n| --- | --- |\n| 值1 | 值2 |"
    expect(_strip_markdown_tables(only_table) == "", "纯表格文本被剥离为空", f"{_strip_markdown_tables(only_table)}")

    # 2. 支柱 3-2：normalize_fill_tables 表头数据行过滤
    row_templates = [{
        "header_cells": ["维度", "本产品", "上代/竞品", "提升"],
        "fields": [{"hint": "维度"}, {"hint": "本产品"}, {"hint": "上代/竞品"}, {"hint": "提升"}],
    }]
    dup_header_tables = [[
        ["维度", "本产品", "上代/竞品", "提升"],  # 误输出的表头数据行
        ["机身高度", "167厘米", "洗烘套装叠放", "无需踮脚操作"],  # 真实数据行
    ]]
    norm = normalize_fill_tables(dup_header_tables, row_templates)
    expect(len(norm[0]) == 1 and norm[0][0][0] == "机身高度", "normalize_fill_tables 成功过滤重复表头数据行", f"{norm}")

    # 3. 支柱 1 形态 A：纯表格承载栏识别与防线 1（彻底剔除纯表格标量）
    hiring_caption = (
        "[**本栏明细由下表承载**(本栏不再另写说明文字、不要写「未提及」)："
        "**一行一个评估维度**，维度名取原文的考察要素或评价口径……评级的判据是本行的依据……]"
    )
    expect(is_table_caption(hiring_caption), "面试报告能力评估说明行被识别为纯表格栏说明", f"{is_table_caption(hiring_caption)}")

    court_caption = (
        "[**本栏明细由下表承载**(本栏不再另写说明文字、不要写「未提及」；二审等无原告/被告之分时按实际立场方填写)："
        "**每个立场方各一行，行数与当事方数量一致**……]"
    )
    expect(is_table_caption(court_caption), "庭审记录诉辩说明行被识别为纯表格栏说明", f"{is_table_caption(court_caption)}")

    with open("resources/templates/zh/hiring_report.md", "r", encoding="utf-8") as f:
        hiring_tpl = f.read()
    hiring_plan = plan_placeholder_fill(hiring_tpl)
    expect(len(hiring_plan["scalars"]) == 2
          and all("能力评估" not in s.get("hint", "") for s in hiring_plan["scalars"]), "防线1：面试报告能力评估在计划层彻底剔除纯表格标量（仅2个标量，不调模型）", f"{[s.get('hint')[:20] for s in hiring_plan['scalars']]}")

    # 4. 支柱 1 形态 B：复合栏表格隔离纪律注入
    with open("resources/templates/zh/clinical_advisory.md", "r", encoding="utf-8") as f:
        clinical_tpl = f.read()
    expect(_section_has_table(clinical_tpl, "治疗方案"), "临床咨询的「治疗方案」被识别为复合表格栏", "")
    col_user = _column_fill_user(
        "上下文",
        clinical_tpl,
        index=3,
        total=5,
        hint="医嘱清单",
        title="治疗方案",
        others=["就诊概况", "病史信息", "诊断结果", "预警信号"],
    )
    expect("【表格隔离纪律】" in col_user and "严禁在正文输出任何 Markdown 表格" in col_user, "复合表格栏用户提示词中成功注入【表格隔离纪律】", f"{col_user}")

    # 5. 拼装层去重集成验证：模拟模型在标量末尾或条目中间画了表，拼装后只有一个表
    scalar_values = [
        "就诊概况正文",
        "病史背景正文",
        "诊断检查正文",
        "复诊预警正文",
    ]
    extracted_tables = [[
        ["斯达舒", "未提及", "每日四五次", "口服", "初有效后效果不佳"],
    ]]
    assembled = assemble_placeholder_output(
        clinical_tpl,
        scalar_values,
        tables=extracted_tables,
    )
    expect(assembled.count("| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |") == 1, "拼装结果中只包含一份表格（表头出现且仅出现一次）", f"{assembled}")
    expect("就诊概况正文" in assembled and "| 斯达舒 | 未提及 | 每日四五次 |" in assembled, "正文与表格提取数据同时存在且无重复表格", f"{assembled}")
