# -*- coding: utf-8 -*-
from domain.notes.tasks.checklist.display import build_checklist_html, build_checklist_markdown
from domain.notes.tasks.checklist.gather import build_checklist_briefing, teacher_from_context
from domain.notes.tasks.checklist.select import activate_from_catalog, activate_points
from domain.notes.tasks.checklist.trace import _trace_card
from domain.notes.tasks.checklist.action import build_action_plan


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


def _nav_draft() -> dict:
    return {
        "course": "量子力学",
        "catalog_version": "1",
        "cards": [
            {"name": "厄米算符", "session_priority": "S", "chapter": "算符", "importance": "5"},
            {"name": "基矢", "session_priority": "B", "chapter": "表象", "importance": "3", "exam_preview": "会写展开"},
            {"name": "对易子", "session_priority": "C", "chapter": "算符", "importance": "2"},
        ],
    }


def test_no_teacher_merges_supplement_into_main_table():
    draft = _nav_draft()
    md = build_checklist_markdown(draft, has_teacher=False)
    html = build_checklist_html(draft, has_teacher=False)
    assert "| 核心 | 厄米算符 |" in md
    assert "| 简要 | 基矢 |" in md
    assert "| 补充 | 对易子 |" in md
    assert "老师未重点点" not in md
    assert "### 简要过一下" in md
    assert "基矢" in md.split("### 简要过一下", 1)[1]
    assert "### 补充" not in md
    assert "老师未重点点" not in html
    assert ">补充<" in html
    assert "对易子" in html
    assert "简要过一下" in html
    assert "<h3>补充</h3>" not in html


def test_with_teacher_keeps_separate_supplement_table():
    draft = _nav_draft()
    md = build_checklist_markdown(draft, has_teacher=True)
    html = build_checklist_html(draft, has_teacher=True)
    assert "老师未重点点" in md
    assert "### 补充" in md
    assert "| 补充 | 对易子 |" not in md
    assert "老师未重点点" in html
    assert "<h3>补充</h3>" in html


def test_action_plan_uses_structured_source_grounded_tasks():
    cards = [
        {
            "name": "洛必达法则",
            "session_priority": "S",
            "practice_type": ["choose_method", "calculate"],
            "session_focus_items": ["0/0型", "∞/∞型", "适用条件"],
            "knowledge_items": ["0/0型", "∞/∞型", "可导条件"],
            "completion_criteria": ["can_choose_method", "can_solve_variant"],
            "session_quotes": ["洛必达法则重点看适用条件。"],
        }
    ]
    plan = build_action_plan(cards, "")
    core = plan["phases"][1]["detail"]["sections"][0]
    assert core["task_objects"]
    assert core["task_objects"][0]["target"].startswith("洛必达法则")
    assert core["task_objects"][0]["output"]
    md = build_checklist_markdown({"course": "高数", "cards": cards, "phases": plan["phases"]})
    assert "产出：" in md
    assert "依据：老师原话 / 知识目录" in md
    html = build_checklist_html({"course": "高数", "cards": cards, "phases": plan["phases"]})
    assert 'class="ck-task-box" type="checkbox"' in html
    assert "data-ck-percent" in html
    assert "ck-progress-track" in html


def test_empty_prerequisites_fall_back_to_same_topic_foundation():
    catalog = {
        "course": "量子力学",
        "chapters": [
            {
                "name": "角动量",
                "topics": [
                    {
                        "name": "角动量",
                        "knowledge_points": [
                            {
                                "id": "kp_base",
                                "name": "角动量算符定义",
                                "importance": "4",
                                "foundational_level": "5",
                                "learning_role": "foundation",
                                "knowledge_items": ["定义", "分量"],
                            },
                            {
                                "id": "kp_core",
                                "name": "角动量对易式",
                                "importance": "5",
                                "foundational_level": "3",
                                "learning_role": "core_method",
                                "knowledge_items": ["对易关系"],
                                "prerequisites": [],
                            },
                        ],
                    }
                ],
            }
        ],
    }

    rows = activate_points(catalog, "角动量对易式必考。")
    core = next(row for row in rows if row["name"] == "角动量对易式")

    assert core["prerequisites"] == ["角动量算符定义"]
    assert any(row["name"] == "角动量算符定义" for row in rows)


def test_trace_html_wraps_plain_formula_for_mathjax():
    draft = {
        "course": "量子力学",
        "cards": [
            {
                "name": "厄米算符",
                "session_priority": "S",
                "chapter": "算符",
                "importance": "5",
                "provenance": {
                    "knowledge_evidence": [
                        {
                            "evidence_id": "kb_01",
                            "source": "notes",
                            "excerpt": "厄米算符满足 A=A^dagger，期望值为实数。",
                            "supports": ["explanation"],
                        }
                    ]
                },
            }
        ],
    }
    html = build_checklist_html(draft, has_teacher=False)
    assert "$A=A^dagger$" in html
