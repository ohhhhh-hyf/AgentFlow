"""Step 2：审核原文摘录说明与真实送审范围保持一致。"""
from __future__ import annotations

from domains.meeting.orchestrator import _Nodes


def _long_minutes_state() -> dict:
    transcript = "张三：本周完成接口联调，缓存保护下周完成。\n" * 2000
    return {
        "transcript": transcript,
        "meeting_understanding": {
            "meeting_brief": "联调进度会",
            "meeting_purpose": "同步进度",
            "speakers": [{"name": "张三"}],
            "session_segments": [],
            "decisions": ["缓存保护下周完成"],
            "risks": ["接口联调可能延期"],
            "open_questions": ["缓存容量待确认"],
        },
        "user": {"perspective": "objective"},
        "perspective_profile": {},
        "objective_perspective": True,
        "line_extra": {},
        "lines": {
            "minutes": {
                "draft": {
                    "headline": "进度会",
                    "executive_summary": ["张三完成接口联调，缓存保护下周完成。"],
                    "key_decisions": ["缓存保护下周完成"],
                    "personally_relevant_points": ["张三负责接口联调"],
                    "risks_and_blockers": ["接口联调可能延期"],
                    "unresolved_questions": ["缓存容量待确认"],
                    "history_comparison": [],
                }
            }
        },
    }


def test_minutes_source_pack_scope_matches_supervisor_draft() -> None:
    """minutes 送审稿不含搬运三字段，source pack 不应再要求核对它们。"""
    text = _Nodes()._supervisor_source_pack(_long_minutes_state(), "minutes")

    assert "送审稿中实际出现的字段" in text
    assert "未出现在送审稿中的字段，不在本轮审核范围" in text
    assert "草稿中从理解层逐字搬运" not in text
    assert "决策、风险、未决问题" not in text
