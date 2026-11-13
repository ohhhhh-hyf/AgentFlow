"""后处理清洗模块单元测试：验证围栏剥离、标题方括号清除、空子栏裁切与英文序号罗马化。"""
import sys
from pathlib import Path

DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

from tasks.minutes.postprocess import (
    clean_heading_brackets,
    clean_markdown_fence,
    collapse_multiple_newlines,
    localize_agenda_headings_for_en,
    postprocess_minutes_markdown,
    prune_empty_subsections,
)


def test_clean_markdown_fence_and_greetings():
    """测试围栏剥离与前言寒暄清除。"""
    raw = "好的，以下是为您整理的纪要：\n\n```markdown\n# 全文摘要\n会议顺利召开。\n```"
    cleaned = clean_markdown_fence(raw)
    assert cleaned.startswith("# 全文摘要")
    assert not cleaned.endswith("```")
    assert "好的，以下是" not in cleaned


def test_clean_heading_brackets():
    """测试防御性清理标题中的方括号。"""
    raw = "# [全文摘要]\n一段内容。\n\n## [架构研讨]\n- 详情\n\n### [结论定调]\n- 决议"
    cleaned = clean_heading_brackets(raw)
    assert "# 全文摘要" in cleaned
    assert "## 架构研讨" in cleaned
    assert "### 结论定调" in cleaned
    assert "[" not in cleaned
    assert "]" not in cleaned


def test_collapse_multiple_newlines():
    """测试多余空行收敛。"""
    raw = "# 标题\n\n\n\n\n正文内容\n\n\n\n尾部"
    collapsed = collapse_multiple_newlines(raw)
    assert "\n\n\n" not in collapsed
    assert "# 标题\n\n正文内容\n\n尾部" == collapsed


def test_prune_empty_subsections():
    """测试空三级子栏裁切与无意义套话清理。"""
    raw = (
        "## 一. 项目推进\n"
        "### 要点梳理\n"
        "- 研发完成核心模块。\n"
        "### 结论定调\n"
        "暂无。\n"
        "### 风险预警\n"
        "### 下一议题\n"
        "内容。"
    )
    pruned = prune_empty_subsections(raw)
    # 含有实质内容的保留
    assert "### 要点梳理" in pruned
    assert "- 研发完成核心模块。" in pruned
    assert "### 下一议题" in pruned
    # 仅含套话或空行的子栏被剔除
    assert "### 结论定调" not in pruned
    assert "暂无" not in pruned
    assert "### 风险预警" not in pruned


def test_localize_agenda_headings_for_en():
    """测试英文模式下中文序号转罗马数字。"""
    raw = "## 一. Project Initiation\n### 二. Architecture Design\n## 三. Risk Assessment"
    en_headings = localize_agenda_headings_for_en(raw)
    assert "## I. Project Initiation" in en_headings
    assert "### II. Architecture Design" in en_headings
    assert "## III. Risk Assessment" in en_headings


def test_postprocess_minutes_markdown_pipeline():
    """测试端到端统一后处理清洗管道。"""
    raw = (
        "好的，为您生成如下纪要：\n"
        "```markdown\n"
        "# [Executive Summary]\n"
        "The project is going well.\n\n\n\n"
        "## 一. [Infrastructure Update]\n"
        "### [Discussion Points]\n"
        "- Migrated to cloud successfully.\n"
        "### [Key Decisions]\n"
        "暂无。\n"
        "```"
    )
    processed = postprocess_minutes_markdown(raw, lang="en")
    assert processed.startswith("# Executive Summary")
    assert "## I. Infrastructure Update" in processed
    assert "### Discussion Points" in processed
    assert "### Key Decisions" not in processed  # 空子栏被裁剪
    assert "暂无" not in processed
    assert "[" not in processed
    assert "]" not in processed
    assert "\n\n\n" not in processed
