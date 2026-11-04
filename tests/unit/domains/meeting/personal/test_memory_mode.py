"""1.3C：普通个人纪要的记忆注入 mode 修复。"""
from __future__ import annotations

from pathlib import Path

import pytest

from domains.meeting.memory import runtime as memory_runtime
from domains.meeting.memory.bind import BindResult
from domains.meeting.memory.extract import MeetingFact
from domains.meeting.memory.inject import build_memory_context
from domains.meeting.memory.runtime import (
    META_KEY,
    _memory_perspective_mode,
    encode_meta,
)


class _UserModel:
    def model_dump(self):
        return {"name": "张三", "focus_person": ["李四"]}


def test_memory_mode_branches() -> None:
    assert (
        _memory_perspective_mode(
            {
                "objective_perspective": True,
                "user": {"name": "张三"},
            }
        )
        == "objective"
    )
    assert _memory_perspective_mode({"user": {"name": "张三"}}) == "personal"
    assert (
        _memory_perspective_mode(
            {"user": {"name": "开发人员", "persona_type": "role_template"}}
        )
        == "role_template"
    )
    assert _memory_perspective_mode({"user": {}}) == "objective"
    assert _memory_perspective_mode({}) == "objective"
    assert _memory_perspective_mode({"user": _UserModel()}) == "personal"


def _install_line_extra_stubs(monkeypatch: pytest.MonkeyPatch) -> dict:
    captured: dict = {}
    fact = MeetingFact(meeting_id="m_test", time="")
    fact.title = "测试事实"

    monkeypatch.setattr(
        memory_runtime, "extract_meeting_fact", lambda *a, **k: fact
    )
    monkeypatch.setattr(
        memory_runtime, "load_registry", lambda *a, **k: {"projects": {}}
    )
    monkeypatch.setattr(memory_runtime, "list_meetings", lambda *a, **k: [])
    monkeypatch.setattr(
        memory_runtime,
        "resolve_bind",
        lambda *a, **k: BindResult(
            project_id="p_test",
            mode="explicit",
            confidence="high",
            core_name="P",
        ),
    )
    monkeypatch.setattr(
        memory_runtime, "_project_entry", lambda *a, **k: {"name": "P"}
    )
    monkeypatch.setattr(
        memory_runtime,
        "load_state",
        lambda *a, **k: {
            "actions": [],
            "open_items": [],
            "risks": [],
            "decisions": [],
        },
    )
    monkeypatch.setattr(
        memory_runtime,
        "backfill_meeting_titles",
        lambda state, meetings: state,
    )

    def fake_context(**kwargs):
        captured["perspective_mode"] = kwargs.get("perspective_mode")
        return "ctx", []

    monkeypatch.setattr(memory_runtime, "build_memory_context", fake_context)
    return captured


def _meta() -> dict[str, str]:
    return {
        META_KEY: encode_meta(
            Path("."),
            "u_test_memory_mode",
            request_id="req_memory_mode",
        )
    }


def test_build_line_extra_minutes_uses_personal_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_line_extra_stubs(monkeypatch)
    state = {
        "transcript": "张三 10:00: 讨论常规事项",
        "meeting_understanding": {},
        "user": {"name": "张三"},
    }
    memory_runtime.build_line_extra(state, "minutes", line_extra=_meta())
    assert captured["perspective_mode"] == "personal"


def test_build_line_extra_minutes_styles_ignores_style(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_line_extra_stubs(monkeypatch)
    state = {
        "transcript": "张三 10:00: 讨论常规事项",
        "meeting_understanding": {},
        "user": {"name": "张三"},
        "line_modes": {"minutes_styles": "brief"},
    }
    memory_runtime.build_line_extra(state, "minutes_styles", line_extra=_meta())
    assert captured["perspective_mode"] == "personal"


def test_build_line_extra_objective_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_line_extra_stubs(monkeypatch)
    state = {
        "transcript": "张三 10:00: 讨论常规事项",
        "meeting_understanding": {},
        "objective_perspective": True,
        "user": {"name": "张三"},
    }
    memory_runtime.build_line_extra(state, "minutes", line_extra=_meta())
    assert captured["perspective_mode"] == "objective"


def test_build_line_extra_role_template_keeps_role_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_line_extra_stubs(monkeypatch)
    state = {
        "transcript": "开发人员 10:00: 讨论常规事项",
        "meeting_understanding": {},
        "user": {"name": "开发人员", "persona_type": "role_template"},
    }
    memory_runtime.build_line_extra(state, "minutes", line_extra=_meta())
    # build_memory_context 只认 personal；role_template 仍走 objective 分支
    assert captured["perspective_mode"] == "role_template"


def _open_items_state() -> dict:
    return {
        "actions": [
            {"text": "完成鉴权插件升级", "owner": "张三", "status": "open"},
            {"text": "前端联调排期", "owner": "李四", "status": "open"},
            {"text": "预算审批", "owner": "王五", "status": "open"},
            {"text": "办公室搬迁", "owner": "赵六", "status": "open"},
        ],
        "open_items": [],
        "risks": [],
        "decisions": [],
        "recent_meetings": [],
    }


def test_build_memory_context_personal_filters_unrelated() -> None:
    context, _ = build_memory_context(
        project_id="p_test",
        project={"name": "P"},
        state=_open_items_state(),
        bind=BindResult(
            project_id="p_test", mode="explicit", confidence="high"
        ),
        meetings=[],
        current_fact=None,
        user={"name": "张三", "focus_person": ["李四"]},
        perspective_mode="personal",
    )
    assert "完成鉴权插件升级" in context
    assert "前端联调排期" in context
    assert "预算审批" not in context
    assert "办公室搬迁" not in context


def test_build_memory_context_objective_keeps_unrelated() -> None:
    context, _ = build_memory_context(
        project_id="p_test",
        project={"name": "P"},
        state=_open_items_state(),
        bind=BindResult(
            project_id="p_test", mode="explicit", confidence="high"
        ),
        meetings=[],
        current_fact=None,
        user={"name": "张三", "focus_person": ["李四"]},
        perspective_mode="objective",
    )
    assert "完成鉴权插件升级" in context
    assert "前端联调排期" in context
    assert "预算审批" in context
    assert "办公室搬迁" in context
