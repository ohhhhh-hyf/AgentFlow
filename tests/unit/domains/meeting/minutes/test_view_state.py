"""Phase 1：minutes view 单源状态 + core 解析节点。"""
from __future__ import annotations

import asyncio
import logging

import pytest

from domains.meeting.models import MeetingState
from domains.meeting.orchestrator import _Nodes
from domains.meeting.views import (
    VIEW_AGENDA_OBJECTIVE,
    VIEW_OBJECTIVE,
    VIEW_PERSONAL,
    VIEW_ROLE_TEMPLATE,
)


def _state(
    *,
    user: dict,
    has_valid_agenda: bool,
    objective_perspective: bool = False,
    line_views: dict | None = None,
) -> dict:
    state = {
        "user": user,
        "has_valid_agenda": has_valid_agenda,
        "objective_perspective": objective_perspective,
    }
    if line_views is not None:
        state["line_views"] = line_views
    return state


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            _state(
                user={"perspective": "objective"},
                has_valid_agenda=False,
            ),
            VIEW_OBJECTIVE,
        ),
        (
            _state(
                user={"name": "张三"},
                has_valid_agenda=False,
            ),
            VIEW_PERSONAL,
        ),
        (
            _state(
                user={"name": "开发人员", "persona_type": "role_template"},
                has_valid_agenda=False,
            ),
            VIEW_ROLE_TEMPLATE,
        ),
        (
            _state(
                user={"perspective": "objective"},
                has_valid_agenda=True,
                objective_perspective=True,
            ),
            VIEW_AGENDA_OBJECTIVE,
        ),
        (
            # personal + agenda 不允许；编排层兜底为 agenda_objective。
            _state(
                user={"name": "张三"},
                has_valid_agenda=True,
            ),
            VIEW_AGENDA_OBJECTIVE,
        ),
    ],
)
def test_minutes_view_node_writes_resolved_view(state: dict, expected: str) -> None:
    out = asyncio.run(_Nodes()._make_minutes_view_node()(state))
    assert out["line_views"]["minutes"] == expected


def test_minutes_view_node_preserves_other_lines() -> None:
    state = _state(
        user={"name": "张三"},
        has_valid_agenda=False,
        line_views={"actions": "objective"},
    )
    out = asyncio.run(_Nodes()._make_minutes_view_node()(state))
    assert out["line_views"] == {
        "actions": "objective",
        "minutes": VIEW_PERSONAL,
    }


def test_meeting_state_declares_line_views() -> None:
    assert "line_views" in MeetingState.__annotations__


def test_meeting_state_declares_line_layouts() -> None:
    assert "line_layouts" in MeetingState.__annotations__
    assert "line_containers" in MeetingState.__annotations__


def test_minutes_view_node_writes_layout_and_strips_template() -> None:
    state = _state(
        user={"perspective": "objective"},
        has_valid_agenda=True,
        objective_perspective=True,
    )
    state["templates"] = {
        "minutes": (
            "# 团队例会\n\n"
            "<!-- layout\n"
            "mode: topic_major\n"
            "container: 议题梳理\n"
            "-->\n\n"
            "## [议题梳理]\n"
            "[说明]\n"
        )
    }

    out = asyncio.run(_Nodes()._make_minutes_view_node()(state))

    assert out["line_views"]["minutes"] == VIEW_AGENDA_OBJECTIVE
    assert out["line_layouts"]["minutes"] == "topic_major"
    assert out["line_containers"]["minutes"] == "议题梳理"
    assert "<!-- layout" not in out["templates"]["minutes"]
    assert "## [议题梳理]" in out["templates"]["minutes"]


def test_minutes_view_node_defaults_column_major_without_layout() -> None:
    state = _state(
        user={"perspective": "objective"},
        has_valid_agenda=False,
    )
    template = "# 通用纪要\n\n## [全文摘要]\n[说明]\n"
    state["templates"] = {"minutes": template, "actions": "其他线模板"}

    out = asyncio.run(_Nodes()._make_minutes_view_node()(state))

    assert out["line_layouts"]["minutes"] == "column_major"
    assert out["line_containers"]["minutes"] == ""
    assert out["templates"]["minutes"] == template
    assert out["templates"]["actions"] == "其他线模板"


def test_minutes_view_node_logs_layout(caplog: pytest.LogCaptureFixture) -> None:
    state = _state(
        user={"perspective": "objective"},
        has_valid_agenda=True,
        objective_perspective=True,
    )
    state["templates"] = {
        "minutes": (
            "# 团队例会\n\n"
            "<!-- layout\n"
            "mode: topic_major\n"
            "container: 议题梳理\n"
            "-->\n\n"
            "## [议题梳理]\n"
            "[说明]\n"
        )
    }

    with caplog.at_level(logging.INFO, logger="agentflow"):
        asyncio.run(_Nodes()._make_minutes_view_node()(state))

    assert "[minutes:layout] layout=topic_major" in caplog.text
    assert "container=议题梳理" in caplog.text


class _BuilderStub:
    def __init__(self) -> None:
        self.nodes: list[str] = []
        self.edges: list[tuple[str, str]] = []

    def add_node(self, name: str, node) -> None:  # noqa: ANN001
        self.nodes.append(name)

    def add_edge(self, start: str, end: str) -> None:
        self.edges.append((start, end))


def test_build_core_wires_minutes_view_after_perspective() -> None:
    builder = _BuilderStub()
    cores = _Nodes()._build_core(builder, ["minutes"])

    assert cores == ["minutes_view"]
    assert "minutes_view" in builder.nodes
    assert ("perspective_modeling", "minutes_view") in builder.edges


def test_build_core_skips_minutes_view_without_minutes() -> None:
    builder = _BuilderStub()
    cores = _Nodes()._build_core(builder, ["actions"])

    assert cores == ["actions_entry"]
    assert "meeting_understanding" not in builder.nodes
    assert "perspective_modeling" not in builder.nodes
    assert "minutes_view" not in builder.nodes


def test_build_core_skips_view_for_agenda_minutes_only() -> None:
    builder = _BuilderStub()
    cores = _Nodes()._build_core(builder, ["agenda_minutes"])

    assert cores == ["meeting_understanding"]
    assert "minutes_view" not in builder.nodes
