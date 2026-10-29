"""Step 5：actions-only 跳过 perspective_modeling。"""
from __future__ import annotations

from domains.meeting.orchestrator import _Nodes


class _Builder:
    def __init__(self) -> None:
        self.nodes: list[str] = []
        self.edges: list[tuple[object, str]] = []

    def add_node(self, name: str, node: object) -> None:
        self.nodes.append(name)

    def add_edge(self, start: object, end: str) -> None:
        self.edges.append((start, end))


def test_actions_only_skips_meeting_understanding_and_perspective() -> None:
    builder = _Builder()
    cores = _Nodes()._build_core(builder, ["actions"])

    assert "meeting_understanding" not in builder.nodes
    assert "perspective_modeling" not in builder.nodes
    assert "template_classify" not in builder.nodes
    assert "minutes_view" not in builder.nodes
    assert cores == ["actions_entry"]


def test_actions_with_other_lines_keeps_perspective_for_other_lines() -> None:
    builder = _Builder()
    _Nodes()._build_core(builder, ["actions", "risks"])

    assert "meeting_understanding" in builder.nodes
    assert "perspective_modeling" in builder.nodes
