# -*- coding: utf-8 -*-
from domain.notes.tasks.catalog.gather import (
    _candidate_budget,
    _compact_existing,
    _detail_pool_candidates,
    _limited_middle_candidates,
    _score_title_candidate,
    _title_path,
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
    assert _candidate_budget(candidates) == 126


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


def test_title_path_dedupes_repeated_levels():
    assert _title_path(
        {
            "heading_path_text": "一维束缚态 / 一维束缚态 / 一维半无限深方势阱",
            "chapter": "一维束缚态",
            "topic": "一维束缚态",
        }
    ) == ["一维束缚态", "一维半无限深方势阱"]


def test_compact_existing_only_expands_relevant_or_incomplete_points():
    catalog = {
        "course": "量子力学",
        "version": 1,
        "chapters": [
            {
                "id": "c1",
                "name": "束缚态",
                "topics": [
                    {
                        "id": "t1",
                        "name": "一维束缚态",
                        "knowledge_points": [
                            {
                                "id": "kp_old",
                                "name": "无限深方势阱",
                                "source_documents": ["old.md"],
                                "practice_type": ["calculation"],
                                "completion_criteria": ["能独立演算"],
                                "learning_role": "core",
                                "risk_tags": ["boundary"],
                            },
                            {
                                "id": "kp_new",
                                "name": "半无限深方势阱",
                                "source_documents": ["new.md"],
                                "practice_type": ["calculation"],
                                "completion_criteria": ["能判断边界条件"],
                                "learning_role": "core",
                                "risk_tags": ["boundary"],
                            },
                            {
                                "id": "kp_missing",
                                "name": "谐振子",
                                "source_documents": ["old.md"],
                                "practice_type": [],
                                "completion_criteria": ["能写出能级"],
                                "learning_role": "core",
                                "risk_tags": ["formula"],
                            },
                        ],
                    }
                ],
            }
        ],
    }

    text = _compact_existing(catalog, detailed_sources={"new.md"})

    assert "已有KP摘要：[kp_old] 无限深方势阱" in text
    assert "[kp_new] 半无限深方势阱（与新资料相关）" in text
    assert "[kp_missing] 谐振子（缺字段：practice_type）" in text
    assert "其余已有 KP 只按摘要匹配；不要重写。" in text


def test_middle_candidates_are_limited_by_file_and_page():
    rows = [
        {
            "source": "notes.md",
            "page": "1",
            "path": ["章节", f"中等标题{i}"],
            "score": 6,
        }
        for i in range(6)
    ]
    rows.extend(
        {
            "source": "notes.md",
            "page": str(page),
            "path": ["章节", f"另一页标题{page}-{i}"],
            "score": 6,
        }
        for page in range(2, 8)
        for i in range(3)
    )

    limited = _limited_middle_candidates(rows, total_limit=100)

    assert [row["path"][-1] for row in limited[:5]] == [
        "中等标题0",
        "中等标题1",
        "中等标题2",
        "中等标题3",
        "中等标题4",
    ]
    assert "中等标题5" not in {row["path"][-1] for row in limited}
    assert len(limited) == 23


def test_detail_pool_keeps_middle_and_low_rows_for_items():
    rows = [
        {
            "source": "notes.md",
            "page": "1",
            "path": ["角动量", "角动量对易式"],
            "score": 6,
            "content_tags": "formula",
        },
        {
            "source": "notes.md",
            "page": "1",
            "path": ["角动量", "注意：边界条件"],
            "score": 4,
            "content_tags": "mistake",
        },
    ]

    detail = _detail_pool_candidates(rows)

    assert [row["path"][-1] for row in detail] == ["角动量对易式", "注意：边界条件"]
