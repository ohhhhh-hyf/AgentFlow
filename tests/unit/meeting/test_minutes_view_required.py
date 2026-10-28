"""Phase 3：生成 / 审核必须显式接收 view，不再从 context 反解析。"""
from __future__ import annotations

import asyncio

import pytest

from domains.meeting.models_generated import Minutes, MinutesSupervisorReview
from domains.meeting.tasks.minutes.prompts import (
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
)
from domains.meeting.tasks.minutes.steps.minutes_agent import MinutesGenerationAgent
from domains.meeting.tasks.minutes.steps.minutes_render import MinutesGenerationRender
from domains.meeting.tasks.minutes.steps.minutes_supervisor import (
    MinutesGenerationSupervisor,
)


class _AgentClient:
    def __init__(self) -> None:
        self.system = ""
        self.label = ""

    async def structured(self, system, user, model, contract, **kwargs):
        self.system = system
        self.label = str(kwargs.get("label") or "")
        return Minutes(headline="测试纪要")


class _SupervisorClient:
    def __init__(self) -> None:
        self.system = ""
        self.label = ""

    async def structured(self, system, user, model, contract, **kwargs):
        self.system = system
        self.label = str(kwargs.get("label") or "")
        return MinutesSupervisorReview(
            decision="approve",
            facts_check={"status": "pass", "findings": []},
            perspective_check={"status": "pass", "findings": []},
            consistency_check={"status": "pass", "findings": []},
            feedback=[],
        )


def test_minutes_agent_requires_view() -> None:
    agent = MinutesGenerationAgent(_AgentClient())
    with pytest.raises(TypeError):
        asyncio.run(agent.run("视角模式：personal"))


def test_minutes_supervisor_requires_view() -> None:
    supervisor = MinutesGenerationSupervisor(_SupervisorClient())
    with pytest.raises(TypeError):
        asyncio.run(supervisor.review("视角模式：personal"))


def test_minutes_agent_rejects_empty_view() -> None:
    agent = MinutesGenerationAgent(_AgentClient())
    with pytest.raises(ValueError, match="generation view is required"):
        asyncio.run(agent.run("视角模式：personal", view=""))


def test_minutes_supervisor_rejects_empty_view() -> None:
    supervisor = MinutesGenerationSupervisor(_SupervisorClient())
    with pytest.raises(ValueError, match="supervisor view is required"):
        asyncio.run(supervisor.review("视角模式：personal", view=""))


def test_minutes_agent_uses_view_not_context() -> None:
    client = _AgentClient()
    agent = MinutesGenerationAgent(client)
    asyncio.run(agent.run("视角模式：personal", view="objective"))

    assert client.label == "minutes/agent/objective/none"
    assert client.system.startswith(MINUTES_OBJECTIVE_GENERATION_PROMPT)


def test_minutes_supervisor_uses_view_not_context() -> None:
    client = _SupervisorClient()
    supervisor = MinutesGenerationSupervisor(client)
    asyncio.run(
        supervisor.review(
            "议题模式：agenda_enhanced\n视角模式：objective",
            view="objective",
        )
    )

    assert client.label == "minutes/supervisor/objective"
    assert MINUTES_OBJECTIVE_SUPERVISOR_PROMPT in client.system


def test_minutes_render_requires_view() -> None:
    render = MinutesGenerationRender(_AgentClient())
    with pytest.raises(TypeError):
        asyncio.run(render.run("视角模式：personal", "# Template"))


def test_minutes_render_rejects_empty_view() -> None:
    with pytest.raises(ValueError, match="render view is required"):
        MinutesGenerationRender._prompt_and_user(
            "视角模式：personal",
            "# Template",
            view="",
        )


def test_minutes_render_uses_view_not_context() -> None:
    prompt, _ = MinutesGenerationRender._prompt_and_user(
        "议题模式：agenda_enhanced\n视角模式：objective",
        "# Template",
        view="personal",
    )
    assert "【栏目语义自适应映射】" in prompt
    assert "严格遵循模板栏目规约与公文层级标准完成排版" not in prompt
