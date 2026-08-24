# -*- coding: utf-8 -*-
from domain.notes.tasks.checklist.gather import build_checklist_briefing, teacher_from_context
from domain.notes.tasks.checklist.select import activate_from_catalog, activate_points
from domain.notes.tasks.checklist.trace import _trace_card


def _catalog() -> dict:
    return {
        "course": "量子力学",
        "version": "1",
        "chapters": [
            {
                "name": "第一章",
                "topics": [
                    {
                        "name": "算符",
                        "knowledge_points": [
                            {
                                "id": "kp_001",
                                "name": "厄米算符",
                                "importance": "5",
                                "knowledge_items": ["A=A†"],
                            },
                            {
                                "id": "kp_002",
                                "name": "对易子",
                                "importance": "3",
                                "knowledge_items": ["[A,B]"],
                            },
                        ],
                    }
                ],
            }
        ],
    }


def test_empty_teacher_activates_from_catalog_not_quotes():
    rows = activate_points(_catalog(), "")
    names = {row["name"] for row in rows}
    assert "厄米算符" in names
    assert all(not row.get("session_quotes") for row in rows)
    assert activate_from_catalog(_catalog())


def test_teacher_text_still_matches_named_kp():
    rows = activate_points(_catalog(), "本次必考厄米算符，务必掌握。")
    assert any(row["name"] == "厄米算符" for row in rows)
    assert any(row.get("session_quotes") for row in rows)


def test_placeholder_transcript_is_not_teacher_focus():
    assert teacher_from_context("根据已有知识目录和知识库生成复习清单") == ""
    assert teacher_from_context("【用户ID】1\n【学科/课程】phy") == ""


def test_briefing_without_teacher_skips_teacher_trace_mode():
    activated = activate_points(_catalog(), "")
    text = build_checklist_briefing(_catalog(), activated, "")
    assert "未提供老师划重点" in text
    assert "跳过老师重点溯源" in text


def test_trace_card_skips_teacher_evidence_when_empty():
    card = {
        "name": "厄米算符",
        "session_priority": "S",
        "knowledge_items": ["A=A†"],
        "session_quotes": [],
        "exam_preview": "会判断是否厄米",
        "key_facts": ["A=A†"],
        "explain": "厄米算符满足 A=A†。",
        "method_steps": ["检查共轭转置"],
        "pitfalls": [],
    }
    traced = _trace_card(card, "", [])
    assert traced["provenance"]["teacher_evidence"] == []
