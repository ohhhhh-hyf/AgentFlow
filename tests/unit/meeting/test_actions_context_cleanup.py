"""Step 7：actions 审核 / 渲染上下文清理。"""
from __future__ import annotations

from domains.meeting.orchestrator import _Nodes


def _state() -> dict:
    return {
        "transcript": "张三：周五前完成接口改造。",
        "user": {"name": "张三"},
        "objective_perspective": False,
        "lang": "zh",
        "meeting_understanding": {
            "meeting_brief": "周例会",
            "session_segments": [{"segment_title": "接口改造"}],
            "action_hints": [{"action": "接口改造"}],
        },
        "personal_perspective": {"personal_summary": "个人视角"},
        "perspective_profile": {"personal_summary": "旧视角"},
        "user_hits_block": "【本用户命中】",
        "user_radar_block": "【重点关注雷达】",
        "line_extra": {"actions": "旧记忆"},
        "lines": {
            "actions": {
                "draft": {
                    "assigned_actions": [
                        {
                            "category": "接口改造",
                            "task": "完成接口改造",
                            "owner": "张三",
                            "deadline": "周五前",
                            "collaborators": None,
                            "acceptance_criteria": None,
                            "dependency": None,
                            "evidence": "张三：周五前完成接口改造。",
                        }
                    ],
                    "unassigned_actions": [],
                },
                "review": {"decision": "approve"},
                "revision_count": 0,
            }
        },
        "templates": {},
    }


def test_actions_supervisor_context_has_no_understanding_or_personal_blocks() -> None:
    context = _Nodes()._supervisor_context(_state(), "actions")
    assert "纪要草稿：" in context or "待办草稿：" in context
    assert "原文（最高事实来源）" in context
    assert "视角模式：objective" in context
    for forbidden in (
        "用户画像",
        "用户视角模型",
        "会议理解",
        "【本用户命中】",
        "【重点关注雷达】",
        "旧记忆",
    ):
        assert forbidden not in context, forbidden


def test_actions_render_context_is_draft_only() -> None:
    context = _Nodes()._render_context(_state(), "actions")
    assert "视角模式：objective" in context
    assert "已批准" in context
    assert "接口改造" in context
    for forbidden in (
        "用户画像",
        "会议理解",
        "【本用户命中】",
        "【重点关注雷达】",
        "旧记忆",
        "个人视角",
        "旧视角",
    ):
        assert forbidden not in context, forbidden
