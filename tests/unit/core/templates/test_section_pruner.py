# 拆分自原大文件，保留：test_knowledge_memo_groups, test_home_school_feedback_groups, test_home_school_content_groups…

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

def test_knowledge_memo_groups() -> None:
    """知识笔记：核心概念分组 + 核心结论双小节。"""
    text = (_active_dir() / "knowledge_memo.md").read_text(encoding="utf-8")
    expect("### 概念名" in text, "知识笔记：核心概念按概念名分组", "")
    expect("### 关键判断与结论" in text, "知识笔记：核心结论含关键判断", "")
    expect("### 易混辨析与适用边界" in text, "知识笔记：核心结论含易混辨析与适用边界", "")
    expect("单段概括，约 250–350 字" in text, "知识笔记：概述栏 250–350 字", "")


def test_home_school_feedback_groups() -> None:
    """家校沟通 [话题探讨]：议题主线 + 探讨焦点 + 校方/家长双分支。"""
    text = (_active_dir() / "home_school_liaison.md").read_text(encoding="utf-8")
    assert "[话题探讨]" in text
    assert "围绕育人与学业的深入探讨" in text
    assert "- **探讨主题/关注焦点**" in text
    assert "校方观察指导" in text and "家长真实反馈" in text
    assert "一条一议" in text

    # 只在本栏范围内查示例（避免误伤其它栏的正当措辞）
    spec = next(l for l in text.splitlines() if l.startswith("[") and "深入探讨" in l)
    assert "如费用" not in spec and "如手机" not in spec and "例如" not in spec
    assert "（照原文）" not in spec


def test_home_school_content_groups() -> None:
    """家校沟通：在校表现 / 话题探讨 / 共识与配合。"""
    text = (_active_dir() / "home_school_liaison.md").read_text(encoding="utf-8")
    expect("- **观察维度/表现领域**" in text, "家校：[在校表现] 按观察维度分项", "")
    expect("- **探讨主题/关注焦点**" in text and "校方观察指导" in text and "家长真实反馈" in text,
           "家校：[话题探讨] 校方/家长双分支", "")
    expect("### 学校推进" in text and "### 家庭协同" in text, "家校：[共识与配合] 分学校/家庭", "")
    plan = plan_placeholder_fill(text)
    expect(len(plan["scalars"]) == 4, "家校：4 个标量栏", f"{len(plan['scalars'])}")


def test_clinical_history_column() -> None:
    """就医咨询：5 栏 + 药品表。"""
    text = (_active_dir() / "clinical_advisory.md").read_text(encoding="utf-8")
    for col in ("就诊概况", "病史信息", "诊断结果", "治疗方案", "预警信号"):
        expect(f"# [{col}]" in text, f"就医咨询：包含 [{col}]", "")
    expect("既往病史、过敏史、用药史与生活史如实完整记录" in text, "就医咨询：病史信息完整记录", "")
    expect("| 药品名称 | 剂量 | 频次 | 用法 | 注意事项 |" in text, "就医咨询：药品表五列", "")


def test_overview_specs_have_scope() -> None:
    """概况栏：团队例会/辩论会声明尺寸与要素。"""
    team = (_active_dir() / "team_meeting.md").read_text(encoding="utf-8")
    debate = (_active_dir() / "debate_forum.md").read_text(encoding="utf-8")
    expect("单段概括，约 250–350 字" in team, "团队例会：概况栏 250–350 字", "")
    expect("单段概括，约 250–350 字" in debate, "辩论会：概况栏 250–350 字", "")
    expect("参会成员或部门" in team and "全局结论" in team, "团队例会：概况要素完整", "")
    expect("原文明示获胜方时据实记录" in debate, "辩论会：胜负只在原文明示时记录", "")


def test_debate_rounds_and_rows() -> None:
    """辩论会：四栏骨架 + 阵营/争议分组。"""
    debate = (_active_dir() / "debate_forum.md").read_text(encoding="utf-8")
    for col in ("辩论概况", "各方立场", "核心争议", "结辩裁决"):
        expect(f"# [{col}]" in debate, f"辩论会：包含 [{col}]", "")
    expect("按阵营设立小节" in debate and "### 阵营名称" in debate, "辩论会：按阵营分组立论", "")
    expect("### 争议议题名称" in debate, "辩论会：按争议议题分组", "")
    expect("**正方结辩**" in debate and "**反方结辩**" in debate and "评委点评" in debate, "辩论会：结辩与评委点评三条", "")


def test_exchange_forum_structure() -> None:
    """沟通交流会：四栏骨架 + 议题/诉求分组。"""
    text = (_active_dir() / "exchange_forum.md").read_text(encoding="utf-8")
    for col in ("沟通背景", "核心信息", "各方诉求", "沟通结果"):
        expect(f"# [{col}]" in text, f"沟通交流会：包含 [{col}]", "")
    expect("### 议题名" in text and "- **业务实体/事实要点**" in text, "沟通交流会：[核心信息] 按议题分条", "")
    expect("- **参与方机构/身份**" in text, "沟通交流会：[各方诉求] 按参与方列诉求", "")


def test_interview_and_lecture_overview() -> None:
    """采访记录/专题讲座：概况尺寸与要素。"""
    interview = (_active_dir() / "interview_transcript.md").read_text(encoding="utf-8")
    lecture = (_active_dir() / "special_lecture.md").read_text(encoding="utf-8")
    expect("单段概括，约 250–350 字" in interview and "访谈核心看点" in interview, "采访记录：概况 250–350 且点出看点", "")
    expect("单段概括，约 250–350 字" in lecture and "核心主张与核心判断" in lecture, "专题讲座：概况 250–350 且点出核心主张", "")
    expect("### 论点名称" in lecture and "Q&A 环节" in lecture, "专题讲座：论点分节且问答下沉", "")


def test_conversation_and_seminar_enrichment() -> None:
    """对话记录/小组讨论：概况与共识分歧结构。"""
    conv = (_active_dir() / "conversation_transcript.md").read_text(encoding="utf-8")
    semi = (_active_dir() / "group_seminar.md").read_text(encoding="utf-8")
    expect("单段概括，约 250–350 字" in conv and "单段概括，约 250–350 字" in semi, "对话/小组：概况 250–350 字", "")
    expect("### 话题名称" in conv and "### 达成共识" in conv and "### 存有分歧" in conv, "对话记录：话题/共识/分歧分组", "")
    expect("### 议题名" in semi and "### 达成共识" in semi and "### 主要分歧" in semi, "小组讨论：议题/共识/分歧分组", "")


def test_project_progress_overview() -> None:
    """项目进度会：概况单段 250–350 + 后续计划按事项分点。"""
    text = (_active_dir() / "project_progress.md").read_text(encoding="utf-8")
    expect("一段写完，约 250–350 字" in text, "项目进度会：概况单段 250–350 字", "")
    expect("按事项分点写" in text and "`- **事项**：做什么 + 责任方 + 时间节点`" in text, "项目进度会：[后续计划] 按事项分点", "")
    from core.templates.template_eval import parse_section_char_budgets
    caps = [b for b in parse_section_char_budgets(text) if b["title"] == "项目概况"]
    expect(bool(caps) and caps[0]["hi"] == 350, "项目进度会：概况预算 350", f"{caps}")


def test_media_overview_scope() -> None:
    """新闻发布：发布会概况单段 300–350。"""
    from core.templates.template_eval import parse_section_char_budgets
    text = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    spec = next(l.strip() for l in text.splitlines() if l.strip().startswith("[一段写完"))
    expect("一段写完，约 300–350 字" in spec, "发布会概况：单段 300–350 字", spec[:80])
    expect("不铺开细节" in spec, "发布会概况：写明不铺开细节", "")
    caps = [b for b in parse_section_char_budgets(text) if b["title"] == "发布会概况"]
    expect(bool(caps) and caps[0]["hi"] == 350, "发布会概况：预算 350", f"{caps}")


def test_class_transcript_task_groups() -> None:
    """课堂记录：四栏骨架与知识点分组。"""
    text = (_active_dir() / "class_transcript.md").read_text(encoding="utf-8")
    for col in ("课程概况", "核心知识点", "问答记录", "课后任务"):
        expect(f"# [{col}]" in text, f"课堂记录：包含 [{col}]", "")
    expect("### 模块/主题名" in text and "下挂缩进子条" in text, "课堂记录：[核心知识点] 模块分组 + 缩进子条", "")
    expect("问题焦点：直接答案" in text, "课堂记录：[问答记录] 一问一答", "")


def test_quote_columns_have_background() -> None:
    """金句栏：引用 + 署名背景。"""
    expectations = {
        "special_lecture": "> —— **主讲人**",
        "interview_transcript": "> —— **受访者姓名**",
    }
    for stem, signature in expectations.items():
        text = (_active_dir() / f"{stem}.md").read_text(encoding="utf-8")
        expect("> “……”" in text and signature in text and "背景" in text, f"{stem} [金句总结]：引用 + 署名背景", "")
        expect("最多 6 句" in text, f"{stem} [金句总结]：最多 6 句", "")
    conv = (_active_dir() / "conversation_transcript.md").read_text(encoding="utf-8")
    expect("[关键原话]" not in conv, "conversation_transcript 已移除独立 [关键原话] 栏", "")


def test_lecture_evidence_cap() -> None:
    """讲座：两级结构 + 论点分节 + 问答下沉。"""
    text = (_active_dir() / "special_lecture.md").read_text(encoding="utf-8")
    spec = next(l for l in text.splitlines() if "两级结构" in l)
    expect("两级结构" in spec and "### 论点名称" in spec and "Q&A 环节" in spec, "讲座：两级结构与问答下沉", spec[:80])
    expect("### 论点名称" in spec, "讲座：论点为小节标题", "")


def test_court_claims_table_both_sides() -> None:
    """庭审：四栏骨架 + 行数提示解析。"""
    from core.templates.template_eval import parse_row_hint
    text = (_active_dir() / "court_transcript.md").read_text(encoding="utf-8")
    for col in ("庭审概况", "诉辩意见", "举证质证", "庭审结果"):
        expect(f"# [{col}]" in text, f"庭审记录：包含 [{col}]", "")
    expect("按立场方逐组呈现" in text, "庭审记录：[诉辩意见] 按立场方分组", "")
    expect(parse_row_hint("原告、被告各占一行（原文有第三人、反诉方的照此增行）") is None, "parse_row_hint：「各占一行」是形态不是上限", "")
    expect(parse_row_hint("最多 3 行") == 3, "parse_row_hint：数字行数仍有效", "")


def test_subjective_judgment_guardrails() -> None:
    """主观判断：采访看点以内化原话为限，辩论胜负以原文明示为限。"""
    d = _active_dir()
    itv = (d / "interview_transcript.md").read_text(encoding="utf-8")
    expect("访谈核心看点" in itv and "受访者身份背景" in itv, "采访：概况点出受访者与访谈看点", "")
    deb = (d / "debate_forum.md").read_text(encoding="utf-8")
    expect("原文明示获胜方时据实记录" in deb, "辩论：胜负只在原文明示时记录", "")
    hir = (d / "hiring_report.md").read_text(encoding="utf-8")
    expect("评级统一标注 优/良/中/差" in hir and "依据列记录面试官点评或候选人具体答题事例" in hir, "面试：评级与依据同源", "")


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
    from core.templates.template_eval import parse_section_char_budgets

    text = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")

    hints: dict[str, str] = {}
    current = None
    for seg in parse_placeholder_template(text):
        if seg["kind"] == "title":
            current = seg["raw"]
        elif seg["kind"] == "field" and current:
            hints.setdefault(current, str(seg["hint"]))
    core = hints["核心信息"]
    stance = hints["官方表态"]

    assert "按业务领域或政策板块设立小节「### 板块名称」" in core
    assert "- **举措/成果要点**" in core
    assert "关键数据自然加粗" in core
    assert "客观讲透事实依据与工作成效" in core

    assert "- **表态议题**" in stance
    assert "能明确发言人时注明「（姓名/身份）」" in stance
    assert "关键原话直接规范引用" in stance
    assert "具体问答交互下沉至「Q&A环节」" in stance

    caps = [b for b in parse_section_char_budgets(text) if b["title"] == "发布会概况"]
    assert caps and caps[0]["hi"] in (350, 400)


def test_product_launch_overview() -> None:
    """产品发布：四栏骨架与概况尺寸。"""
    text = (_active_dir() / "product_launch.md").read_text(encoding="utf-8")
    for col in ("产品概况", "市场定位", "核心卖点", "发售信息"):
        expect(f"# [{col}]" in text, f"产品发布：包含 [{col}]", "")
    expect("单段概括，约 250–350 字" in text, "产品发布：概况 250–350 字", "")
    expect("本栏明细由下表承载" in text, "产品发布：[核心卖点] 表格承载", "")


def test_retro_annual_groups() -> None:
    """复盘会：五栏骨架与改进计划。"""
    text = (_active_dir() / "retrospective_session.md").read_text(encoding="utf-8")
    for col in ("复盘概况", "关键成果", "亮点事项", "不足事项", "改进计划"):
        expect(f"# [{col}]" in text, f"复盘会：包含 [{col}]", "")
    expect("- **改进事项名称**" in text, "复盘会：[改进计划] 按改进事项逐条", "")
