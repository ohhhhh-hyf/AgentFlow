"""Step 6：actions-only 跳过会议理解 / 视角建模的 FakeLLM 集成测试。"""
from __future__ import annotations

import asyncio

from domains.meeting.models import (
    ActionItems,
    ActionItemsSupervisorReview,
    MeetingUnderstanding,
)
from domains.meeting.orchestrator import MeetingAgentSystem


def _items() -> ActionItems:
    return ActionItems(
        assigned_actions=[
            {
                "category": "网关鉴权",
                "task": "完成网关鉴权重构",
                "owner": "张三",
                "deadline": "周五下班前",
                "collaborators": "李四",
                "acceptance_criteria": "通过联调",
                "dependency": "等待测试环境就绪",
                "evidence": "张三：我周五前把网关鉴权重构完，李四配合联调。",
            }
        ],
        unassigned_actions=[
            {
                "category": "上线排期",
                "task": "补充测试环境GPU驱动版本",
                "owner": None,
                "deadline": None,
                "collaborators": None,
                "acceptance_criteria": None,
                "dependency": None,
                "evidence": "需要补充测试环境的GPU驱动版本。",
            }
        ],
    )


def _review() -> ActionItemsSupervisorReview:
    return ActionItemsSupervisorReview(
        decision="approve",
        actions_check={"status": "pass", "findings": []},
        feedback=[],
    )


class _FakeClient:
    def __init__(self) -> None:
        self.structured_calls: list[tuple[object, str, str]] = []
        self.render_calls: list[tuple[str, str]] = []

    async def structured(self, system, user, model=None, contract=None, **kwargs):
        self.structured_calls.append((model, system, user))
        if model is MeetingUnderstanding:
            raise AssertionError("actions-only 不应调用会议理解")
        if model is ActionItems:
            return _items()
        if model is ActionItemsSupervisorReview:
            return _review()
        raise AssertionError(f"unexpected model: {model!r}")

    async def text(self, prompt, user, **kwargs):
        self.render_calls.append((prompt, user))
        return "1. **[网关鉴权]**\n   - 完成网关鉴权重构 (责任人：张三)"

    async def stream_text(self, prompt, user, **kwargs):
        self.render_calls.append((prompt, user))
        yield "1. **[网关鉴权]**\n   - 完成网关鉴权重构 (责任人：张三)"


def test_actions_only_bypasses_meeting_understanding_and_perspective() -> None:
    client = _FakeClient()
    system = MeetingAgentSystem(client=client)

    async def _consume():
        events = []
        async for event in system.run_streaming(
            transcript="张三：我周五前把网关鉴权重构完，李四配合联调。",
            user={"name": "张三", "name_aliases": ["小张"]},
            lines=["actions"],
            lang="zh",
        ):
            events.append(event)
        return events

    events = asyncio.run(_consume())
    types = [event.get("type") for event in events]
    assert "chunk" in types
    assert "done" in types

    models = [model for model, _, _ in client.structured_calls]
    assert MeetingUnderstanding not in models
    assert ActionItems in models
    full_text = "".join(
        event.get("text", "")
        for event in events
        if event.get("type") == "chunk" and event.get("line") == "actions"
    )
    assert "网关鉴权" in full_text
    assert "完成网关鉴权重构" in full_text

    actions_calls = [
        (system_prompt, user)
        for model, system_prompt, user in client.structured_calls
        if model is ActionItems
    ]
    assert len(actions_calls) == 1
    system_prompt, user_prompt = actions_calls[0]
    assert "全员待办事项 Agent" in system_prompt
    assert "会议原文" in user_prompt
    assert "会议理解" not in user_prompt
    assert "用户画像" not in user_prompt
    assert "perspective_profile" not in user_prompt
