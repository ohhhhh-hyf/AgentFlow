"""Stage 5：template_classify 图节点、模板物化与日志。"""
from __future__ import annotations

import asyncio
import logging
import re

from langgraph.graph import START

from app.config import (
    resolve_agenda_template_format,
    resolve_template_format,
)
from core.graph.engine_text import line_template
from domains.meeting.models import MeetingState
from domains.meeting.orchestrator import (
    _EMPTY_MEETING_UNDERSTANDING,
    _Nodes,
)
from domains.meeting.tasks.minutes.steps import template_select

LONG_TRANSCRIPT = "会议内容" * 600  # 2400 字，不触发短会
AGENDA_TEXT = "1. 自研车载芯片二期量产 汇报人：张三"
AGENDA_TRANSCRIPT = (
    "张三 10:00: 进展汇报自研芯片二期量产良率 91.5%\n"
    + ("李四 10:05: 继续讨论量产排期与风险。\n" * 120)
)


class FakeClient:
    def __init__(self, response: str = '{"template":"project_progress","confidence":0.86}') -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict]] = []

    async def text(self, system: str, user: str, **kwargs) -> str:
        self.calls.append((system, user, kwargs))
        return self.response


class _BuilderStub:
    def __init__(self) -> None:
        self.nodes: list[str] = []
        self.edges: list[tuple[str, str]] = []

    def add_node(self, name: str, node) -> None:  # noqa: ANN001
        self.nodes.append(name)

    def add_edge(self, start: str, end: str) -> None:
        self.edges.append((start, end))


def _state(**overrides) -> dict:
    state = {
        "transcript": LONG_TRANSCRIPT,
        "templates": {"minutes": "【兜底模板】"},
        "template_auto": True,
        "template_source": "default",
        "template_id": "general_minutes",
        "template_mode": "normal",
        "line_extra": {},
        "lang": "zh",
    }
    state.update(overrides)
    return state


def _node(client: FakeClient):
    nodes = _Nodes()
    nodes.client = client
    return nodes._make_template_classify_node()


# ── 图接线 ────────────────────────────────────────────────────


def test_graph_inserts_classify_before_understanding() -> None:
    builder = _BuilderStub()
    _Nodes()._build_core(builder, ["minutes"])

    assert "template_classify" in builder.nodes
    assert (START, "template_classify") in builder.edges
    assert ("template_classify", "meeting_understanding") in builder.edges
    assert (START, "meeting_understanding") not in builder.edges


def test_graph_skips_classify_without_minutes() -> None:
    for lines in (["actions"], ["agenda_minutes"], ["minutes_trace"]):
        builder = _BuilderStub()
        _Nodes()._build_core(builder, lines)
        assert "template_classify" not in builder.nodes, lines
        assert (START, "meeting_understanding") in builder.edges


def test_graph_includes_classify_for_all_lines() -> None:
    builder = _BuilderStub()
    _Nodes()._build_core(builder, None)
    assert "template_classify" in builder.nodes


def test_meeting_state_declares_template_decision() -> None:
    assert "template_decision" in MeetingState.__annotations__


# ── no-op ────────────────────────────────────────────────────


def test_explicit_template_is_noop(monkeypatch, caplog) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    caplog.set_level(logging.INFO)
    client = FakeClient()
    out = asyncio.run(
        _node(client)(
            _state(template_auto=False, template_source="explicit", template_id="project_progress")
        )
    )
    assert out == {}
    assert client.calls == []
    assert "reason=explicit_template" in caplog.text


def test_personal_profile_is_noop(monkeypatch, caplog) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    caplog.set_level(logging.INFO)
    client = FakeClient()
    out = asyncio.run(
        _node(client)(
            _state(
                template_auto=False,
                template_source="personal_default",
                template_id="personal_minutes",
            )
        )
    )
    assert out == {}
    assert client.calls == []
    assert "reason=personal_profile" in caplog.text


def test_switch_off_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("MINUTES_TEMPLATE_AUTO", raising=False)
    client = FakeClient()
    out = asyncio.run(_node(client)(_state()))
    assert out == {}
    assert client.calls == []


def test_short_text_skips_agent(monkeypatch, caplog) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    caplog.set_level(logging.INFO)
    client = FakeClient()
    out = asyncio.run(_node(client)(_state(transcript="短会")))
    assert client.calls == []
    assert "templates" not in out
    assert out["template_decision"]["reason"] == "short_text"
    assert out["template_decision"]["action"] == "skip"
    assert "reason=short_text" in caplog.text


# ── 应用与 shadow ────────────────────────────────────────────


def test_on_applies_selected_template(monkeypatch, caplog) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    caplog.set_level(logging.INFO)
    client = FakeClient()
    out = asyncio.run(_node(client)(_state()))

    assert out["template_id"] == "project_progress"
    assert out["template_source"] == "auto"
    assert out["template_mode"] == "normal"
    assert out["templates"]["minutes"] == resolve_template_format("project_progress", "zh").strip()
    assert out["template_decision"]["applied"] is True
    assert out["template_decision"]["accepted"] is True
    assert "[template:auto:start]" in caplog.text
    assert "[template:auto:decision]" in caplog.text
    assert "[template:auto:materialize]" in caplog.text
    assert "[template:auto:done]" in caplog.text


def test_shadow_classifies_without_overriding(monkeypatch, caplog) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "shadow")
    caplog.set_level(logging.INFO)
    client = FakeClient()
    out = asyncio.run(_node(client)(_state()))

    assert "templates" not in out
    assert "template_id" not in out
    assert out["template_decision"]["applied"] is False
    assert out["template_decision"]["accepted"] is True
    assert out["template_decision"]["template"] == "project_progress"
    assert "shadow=1" in caplog.text
    assert "[template:auto:materialize]" not in caplog.text


def test_low_confidence_keeps_general(monkeypatch) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    client = FakeClient('{"template":"project_progress","confidence":0.62}')
    out = asyncio.run(_node(client)(_state()))

    assert "templates" not in out
    assert out["template_id"] == "general_minutes"
    assert out["template_source"] == "auto_fallback"
    assert out["template_decision"]["reason"] == "low_confidence"
    assert out["template_decision"]["applied"] is False


def test_invalid_output_keeps_general(monkeypatch) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    client = FakeClient("not json")
    out = asyncio.run(_node(client)(_state()))

    assert "templates" not in out
    assert out["template_source"] == "auto_fallback"
    assert out["template_decision"]["reason"] == "invalid_output"


def test_empty_materialize_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    monkeypatch.setattr(template_select, "resolve_template_text", lambda *a, **k: "")
    client = FakeClient()
    out = asyncio.run(_node(client)(_state()))

    assert "templates" not in out
    assert out["template_source"] == "auto_fallback"
    assert out["template_decision"]["reason"] == "empty_template"
    assert out["template_decision"]["applied"] is False


# ── 议题模式 ─────────────────────────────────────────────────


def test_agenda_uses_agenda_candidates_and_template(monkeypatch) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    client = FakeClient('{"template":"team_meeting","confidence":0.84}')
    out = asyncio.run(
        _node(client)(
            _state(
                template_mode="agenda",
                line_extra={"agenda_text": AGENDA_TEXT},
            )
        )
    )

    system, user, _ = client.calls[0]
    assert len(re.findall(r"^- [a-z_]+（", system, re.M)) == 20
    assert "【现场审定的有效议题清单】" in user
    assert out["templates"]["minutes"] == resolve_agenda_template_format("team_meeting", "zh").strip()
    assert out["template_decision"]["mode"] == "agenda"


def test_agenda_single_line_skips_understanding_and_keeps_template(monkeypatch) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    client = FakeClient('{"template":"project_progress","confidence":0.86}')
    state = _state(
        transcript=AGENDA_TRANSCRIPT,
        template_mode="agenda",
        line_extra={"agenda_text": AGENDA_TEXT},
    )
    state.update(asyncio.run(_node(client)(state)))

    understanding = _Nodes()._make_meeting_understanding_node(["minutes"])
    result = asyncio.run(understanding(state))

    assert result["meeting_understanding"] == _EMPTY_MEETING_UNDERSTANDING
    assert "templates" not in result
    assert state["template_id"] == "project_progress"
    expected = resolve_agenda_template_format("project_progress", "zh").strip()
    assert line_template(state, "minutes") == expected
