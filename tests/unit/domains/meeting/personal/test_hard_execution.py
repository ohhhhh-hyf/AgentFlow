"""Step 7：个人模式硬对齐测试。"""
from __future__ import annotations

from core.execution.hard_execution import enforce_minutes_draft


def _draft() -> dict:
    return {
        "headline": "",
        "executive_summary": ["个人业务进展"],
        "key_decisions": ["本场决策A"],
        "personally_relevant_points": ["**本人相关**：", "完成联调"],
        "risks_and_blockers": ["**本人相关**：", "显存不足"],
        "unresolved_questions": ["待确认测试范围"],
        "history_comparison": [],
    }


def test_personal_keeps_draft_risks_and_unresolved() -> None:
    understanding = {
        "meeting_brief": "评审会",
        "speakers": [{"name": "张三"}],
        "session_segments": [{"segment_title": "进展"}],
        "decisions": ["本场决策A", "本场决策B"],
    }
    out = enforce_minutes_draft(
        _draft(),
        understanding,
        mode="personal",
    )
    assert out["key_decisions"] == ["本场决策A"]
    assert out["risks_and_blockers"] == ["**本人相关**：", "显存不足"]
    assert out["unresolved_questions"] == ["待确认测试范围"]


def test_personal_headline_falls_back_to_meeting_brief() -> None:
    out = enforce_minutes_draft(
        _draft(),
        {"meeting_brief": "云迁移评审会", "decisions": ["本场决策A"]},
        mode="personal",
    )
    assert out["headline"] == "云迁移评审会"

    out_default = enforce_minutes_draft(
        _draft(),
        {"decisions": ["本场决策A"]},
        mode="personal",
        lang="en",
    )
    assert out_default["headline"] == "Meeting Minutes"


def test_personal_skips_memory_purge() -> None:
    out = enforce_minutes_draft(
        _draft(),
        {"meeting_brief": "评审会", "decisions": ["本场决策A"]},
        mode="personal",
        memory_texts=["本场决策A"],
        transcript="本场没有这句话",
    )
    assert out["key_decisions"] == ["本场决策A"]
    assert out["history_comparison"] == []


def test_personal_empty_understanding_keeps_draft_decisions() -> None:
    out = enforce_minutes_draft(_draft(), {}, mode="personal")
    assert out["key_decisions"] == ["本场决策A"]
    assert out["headline"] == "会议纪要"
