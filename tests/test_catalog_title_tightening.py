# -*- coding: utf-8 -*-
from domain.notes.tasks.catalog.gather import (
    _candidate_budget,
    _score_title_candidate,
    _title_candidates,
)
from tools.knowledge.source_role import heading_level


def test_short_item_only_lines_do_not_become_headings():
    assert heading_level("注意") is None
    assert heading_level("例题1") is None
    assert heading_level("步骤：代入") is None
    assert heading_level("小结") is None
    assert heading_level("定义：洛必达法则") == (3, "定义：洛必达法则")


def test_item_only_knowledge_point_candidates_are_downgraded():
    score, reasons = _score_title_candidate(
        {
            "heading": "例题：氢原子能级计算",
            "heading_score": "8",
            "heading_kind": "knowledge_point",
            "content_tags": "example,formula",
        }
    )
    assert score == 4
    assert "细碎标题仅作item/evidence" in reasons


def test_candidate_budget_scales_with_pages_not_fixed_400():
    candidates = [
        {"source": "notes.md", "page": str(page), "score": 8}
        for page in range(1, 22)
    ]
    assert _candidate_budget(candidates) == 105


def test_title_candidates_filter_low_item_only_rows():
    grouped = {
        "material": [],
        "notes": [
            {
                "source": "notes.md",
                "heading": "易错：边界条件",
                "heading_score": "8",
                "heading_kind": "knowledge_point",
                "content_tags": "mistake",
            },
            {
                "source": "notes.md",
                "heading": "洛必达法则",
                "heading_score": "8",
                "heading_kind": "knowledge_point",
                "content_tags": "method",
            },
        ],
        "unknown": [],
    }
    candidates = _title_candidates(grouped)
    assert [row["heading"] for row in candidates] == ["洛必达法则", "易错：边界条件"]
    assert candidates[1]["score"] == 4
