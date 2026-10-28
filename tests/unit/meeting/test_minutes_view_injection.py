"""Phase 2：核心图把 state["line_views"] 注入生成 / 审核 Agent。"""
from __future__ import annotations

import asyncio

from core.runtime.render import _render_run
from domains.meeting.orchestrator import MeetingAgentSystem


class _AgentStub:
    def __init__(self) -> None:
        self.view = ""
        self.context = ""

    async def run(self, context: str, *, view: str):
        self.view = view
        self.context = context

        class _Out:
            def model_dump(self) -> dict:
                return {"headline": "测试纪要"}

        return _Out()


class _SupervisorStub:
    def __init__(self) -> None:
        self.view = ""
        self.calls = 0

    async def review(self, context: str, *, view: str) -> dict:
        self.view = view
        self.calls += 1
        return {
            "decision": "approve",
            "feedback": [],
            "facts_check": {"status": "pass", "findings": []},
            "perspective_check": {"status": "pass", "findings": []},
            "consistency_check": {"status": "pass", "findings": []},
        }


def _state(*, line_views=None, transcript: str = "张三：讨论下周排期。") -> dict:
    state = {
        "transcript": transcript,
        "meeting_understanding": {
            "meeting_brief": "",
            "meeting_purpose": "",
            "speakers": [],
            "session_segments": [],
            "decisions": [],
            "risks": [],
            "open_questions": [],
        },
        "user": {"name": "张三"},
        "perspective_profile": {},
        "objective_perspective": False,
        "line_extra": {},
        "line_modes": {},
        "templates": {},
        "lang": "zh",
        "lines": {
            "minutes": {
                "draft": {"headline": "测试纪要"},
                "revision_feedback": [],
            }
        },
    }
    if line_views is not None:
        state["line_views"] = line_views
    return state


def _agent_system(agent: _AgentStub) -> MeetingAgentSystem:
    system = object.__new__(MeetingAgentSystem)
    system._task_lines = {
        "minutes": {
            "agent_attr": "minutes_agent",
            "empty_draft": {},
        }
    }
    system._line_cn_names = {"minutes": "纪要"}
    system.minutes_agent = agent
    return system


def _supervisor_system(supervisor: _SupervisorStub) -> MeetingAgentSystem:
    system = object.__new__(MeetingAgentSystem)
    system._task_lines = {
        "minutes": {
            "supervisor_attr": "minutes_supervisor",
            "reject_review": {
                "facts_check": {"status": "fail", "findings": ["x"]},
                "perspective_check": {"status": "fail", "findings": ["x"]},
                "consistency_check": {"status": "fail", "findings": ["x"]},
            },
        }
    }
    system._line_cn_names = {"minutes": "纪要"}
    system._supervisor_fast_path_chars = 2000
    system._supervisor_guardrail_range = (2000, 5000)
    system.minutes_supervisor = supervisor
    return system


def test_agent_node_injects_line_view() -> None:
    agent = _AgentStub()
    out = asyncio.run(
        _agent_system(agent)._make_agent_node("minutes")(
            _state(line_views={"minutes": "personal"})
        )
    )

    assert agent.view == "personal"
    draft = out["lines"]["minutes"]
    assert draft["degraded"] is False
    assert draft["draft"]["headline"] == "测试纪要"


def test_agent_node_without_view_degrades() -> None:
    agent = _AgentStub()
    out = asyncio.run(_agent_system(agent)._make_agent_node("minutes")(_state()))

    assert agent.view == ""
    assert out["lines"]["minutes"]["degraded"] is True


def test_supervisor_node_injects_line_view() -> None:
    supervisor = _SupervisorStub()
    out = asyncio.run(
        _supervisor_system(supervisor)._make_supervisor_node("minutes")(
            _state(
                line_views={"minutes": "agenda_objective"},
                transcript="张工：本周完成联调。" * 1000,
            )
        )
    )

    assert supervisor.view == "agenda_objective"
    assert supervisor.calls == 1
    review = out["lines"]["minutes"]["review"]
    assert review["decision"] == "approve"


def test_supervisor_node_without_view_marks_unavailable() -> None:
    supervisor = _SupervisorStub()
    out = asyncio.run(
        _supervisor_system(supervisor)._make_supervisor_node("minutes")(
            _state(transcript="张工：本周完成联调。" * 1000)
        )
    )

    assert supervisor.calls == 0
    review = out["lines"]["minutes"]
    assert review["review_unavailable"]


class _RenderStub:
    def __init__(self) -> None:
        self.view = ""

    async def run(self, context: str, template: str, *, view: str) -> str:
        self.view = view
        return "ok"


def test_render_run_injects_view() -> None:
    render = _RenderStub()
    out = asyncio.run(
        _render_run(render, "渲染上下文", "# 模板", None, view="personal")
    )

    assert out == "ok"
    assert render.view == "personal"
