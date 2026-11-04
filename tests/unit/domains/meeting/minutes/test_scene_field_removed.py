"""会议理解 scene 字段下线回归：模型、契约、空结构、上下文、审核摘要都不再出现。"""
from __future__ import annotations

from dataclasses import fields

from core.runtime.supervisor_slice import summarize_understanding
from domains.meeting.meeting_core.contracts import (
    ALL_CORE_FIELD_NAMES,
    build_core_contract_for_tasks,
)
from domains.meeting.models import MeetingUnderstanding
from domains.meeting.orchestrator import _EMPTY_MEETING_UNDERSTANDING, _Nodes


def test_meeting_understanding_has_no_scene_field() -> None:
    names = {f.name for f in fields(MeetingUnderstanding)}

    assert "scene" not in names
    assert "scene" not in ALL_CORE_FIELD_NAMES


def test_minutes_contract_has_no_scene_field() -> None:
    contract, omitted = build_core_contract_for_tasks(["minutes"])

    assert '"scene"' not in contract
    assert "scene" not in omitted


def test_empty_understanding_has_no_scene_key() -> None:
    assert "scene" not in _EMPTY_MEETING_UNDERSTANDING


def test_meeting_pack_has_no_scene_key() -> None:
    state = {
        "meeting_understanding": {
            "meeting_brief": "周会",
            "meeting_purpose": "同步进展",
            "scene": "团队例会",  # 旧数据兼容：多出的键应被忽略
            "speakers": [],
            "session_segments": [],
            "decisions": [],
            "open_questions": [],
            "risks": [],
        }
    }

    pack = _Nodes._meeting_pack(object(), state, "minutes")

    assert "scene" not in pack


def test_render_context_has_no_scene_key() -> None:
    state = {
        "transcript": "张三：本周完成联调。",
        "objective_perspective": True,
        "templates": {},
        "line_extra": {},
        "user": {},
        "meeting_understanding": {
            "meeting_brief": "周会",
            "meeting_purpose": "同步进展",
            "scene": "团队例会",  # 旧数据兼容：不应再进入渲染上下文
            "speakers": [],
            "session_segments": [],
            "decisions": [],
            "open_questions": [],
            "risks": [],
        },
        "lines": {"minutes": {"draft": {}, "review": {}}},
    }

    context = _Nodes()._render_context(state, "minutes")

    assert "scene" not in context


def test_supervisor_summary_ignores_legacy_scene() -> None:
    text = summarize_understanding(
        {
            "meeting_purpose": "同步进展",
            "scene": "团队例会",  # 旧数据兼容：不应再出现在审核摘要
            "session_segments": [],
        }
    )

    assert "目的：同步进展" in text
    assert "场景：" not in text


def test_understanding_needle_keep_has_no_scene() -> None:
    for line_name, fields_keep in _Nodes._understanding_needle_keep.items():
        assert "scene" not in fields_keep, line_name
