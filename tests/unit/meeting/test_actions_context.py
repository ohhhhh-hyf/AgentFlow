"""Step 4：actions 上下文只读会议原文。"""
from __future__ import annotations

from domains.meeting.orchestrator import _Nodes


def test_actions_context_is_transcript_only() -> None:
    state = {
        "transcript": "张三：周五前完成接口改造。",
        "user": {"name": "张三", "name_aliases": ["小张"]},
        "objective_perspective": False,
        "meeting_understanding": {
            "meeting_brief": "周例会",
            "meeting_purpose": "同步进展",
            "speakers": [{"name": "张三"}],
            "session_segments": [{"segment_title": "接口改造"}],
            "decisions": ["周五前完成"],
            "action_hints": [{"action": "接口改造", "owner": "张三"}],
        },
        "perspective_profile": {"personal_summary": "旧视角"},
        "user_hits_block": "【本用户命中】",
        "user_radar_block": "【重点关注雷达】",
    }
    context = _Nodes()._line_shared_context(state, "actions")
    assert context == "会议原文：\n张三：周五前完成接口改造。"
    for forbidden in (
        "会议理解",
        "用户画像",
        "【本用户命中】",
        "【重点关注雷达】",
        "旧视角",
        "action_hints",
    ):
        assert forbidden not in context
