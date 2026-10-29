"""Step 6：个人单线草稿上下文测试。"""
from __future__ import annotations

from core.execution.hard_execution import extract_labeled_json
from domains.meeting.orchestrator import _Nodes
from domains.shared.perspective import (
    PERSONAL_DRAFT_UNDERSTANDING_FIELDS,
    PERSONAL_PERSPECTIVE_FIELDS,
)
from domains.meeting.tasks.minutes.steps.minutes_agent import _extract_transcript


class _Host(_Nodes):
    def __init__(self) -> None:
        pass

    def _understanding(self, state):
        return state.get("meeting_understanding") or {}


def _state(*, with_aux: bool = False) -> dict:
    state = {
        "user": {"name": "申家坤", "name_aliases": ["家坤"]},
        "meeting_understanding": {
            "meeting_brief": "demo 评审",
            "meeting_purpose": "确认上线窗口",
            "speakers": [{"name": "申家坤"}],
            "session_segments": [{"segment_title": "压测"}],
            "decisions": ["周五上线"],
            "open_questions": ["测试范围"],
            "risks": ["显存不足"],
            "action_hints": [{"owner": "申家坤"}],
            "dependencies": ["测试环境"],
            "topics": ["旧字段"],
        },
        "personal_perspective": {
            "confidence": "high",
            "personal_summary": "负责压测。",
            "focus_points": ["压测"],
            "possible_actions": ["周五前提交报告"],
            "collaborations": ["张工：提供环境"],
            "concerns": ["显存不足"],
            "data_gaps": ["缺少驱动"],
            "focus_risks": ["上线窗口"],
            "open_questions": ["确认范围"],
            "attention_points": ["旧字段"],
            "evidence": ["旧依据"],
        },
        "objective_perspective": False,
        "has_valid_agenda": False,
    }
    if with_aux:
        state["line_extra"] = {
            "minutes_auxiliary": "【用户核心关键点】\n- 关注压测"
        }
    return state


def test_personal_draft_context_has_only_4_plus_9_and_aux() -> None:
    context = _Host()._line_shared_context(_state(with_aux=True), "minutes")

    assert context.startswith("会议理解：")
    assert "用户视角模型：" in context
    assert "【辅助材料】" in context
    assert "【用户核心关键点】" in context

    for field in PERSONAL_DRAFT_UNDERSTANDING_FIELDS:
        assert field in context, field
    for field in PERSONAL_PERSPECTIVE_FIELDS:
        assert field in context, field

    for forbidden in (
        "meeting_purpose",
        "action_hints",
        "dependencies",
        "topics",
        "attention_points",
        "evidence",
        "用户画像",
        "偏好",
        "命中",
        "雷达",
        "会议原文",
        "篇幅预算",
    ):
        assert forbidden not in context, forbidden

    understanding = extract_labeled_json(context, "会议理解")
    perspective = extract_labeled_json(context, "用户视角模型")
    assert tuple(understanding) == PERSONAL_DRAFT_UNDERSTANDING_FIELDS
    assert tuple(perspective) == PERSONAL_PERSPECTIVE_FIELDS
    assert _extract_transcript(context) == ""


def test_personal_draft_context_omits_aux_when_absent() -> None:
    context = _Host()._line_shared_context(_state(), "minutes")
    assert "【辅助材料】" not in context
    assert "会议理解：" in context
    assert "用户视角模型：" in context


def test_objective_context_keeps_legacy_path() -> None:
    state = _state()
    state["user"] = {}
    context = _Host()._line_shared_context(state, "minutes")
    assert "视角模式：objective" in context
    assert "用户视角模型：" not in context
