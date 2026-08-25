# -*- coding: utf-8 -*-
from domain.notes.tasks.library.report import (
    _knowledge_units_from_chunk,
    build_library_html,
    build_library_markdown,
)


def test_library_increment_counts_heading_block_once():
    chunk = {
        "text": "能级公式。\n波函数。\n量子数。",
        "metadata": {
            "source": "notes.md",
            "heading": "氢原子",
            "heading_kind": "knowledge_point",
            "content_tags": "formula,definition",
        },
    }
    assert _knowledge_units_from_chunk(chunk) == ["氢原子"]


def test_library_increment_skips_item_only_heading():
    chunk = {
        "text": "注意适用条件。\n例题。",
        "metadata": {
            "source": "notes.md",
            "heading": "注意：边界条件",
            "heading_kind": "knowledge_point",
            "content_tags": "mistake",
        },
    }
    assert _knowledge_units_from_chunk(chunk) == []


def test_library_increment_skips_chapter_and_evidence_blocks():
    assert (
        _knowledge_units_from_chunk(
            {
                "text": "第一章",
                "metadata": {"heading": "量子力学", "heading_kind": "chapter"},
            }
        )
        == []
    )
    assert (
        _knowledge_units_from_chunk(
            {
                "text": "只是正文证据",
                "metadata": {"heading": "正文", "heading_kind": "evidence"},
            }
        )
        == []
    )


def test_library_report_uses_knowledge_unit_wording():
    draft = {
        "increment": "3",
        "files": [{"name": "notes.md", "added": "5"}],
        "items": [{"text": "氢原子", "source": "notes.md"}],
    }
    assert "新增可编目知识单元 3 个" in build_library_markdown(draft)
    assert "本次新增可编目知识单元" in build_library_html(draft)
