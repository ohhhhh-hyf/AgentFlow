"""Step 9：个人单线 minutes 的 FakeLLM 全链路集成测试。"""
from __future__ import annotations

import asyncio

from app.config import resolve_task_template_format
from domains.meeting.models import (
    MeetingUnderstanding,
    Minutes,
    MinutesSupervisorReview,
)
from domains.meeting.orchestrator import MeetingAgentSystem
from domains.meeting.tasks.minutes.prompts import (
    MINUTES_PERSONAL_GENERATION_PROMPT,
)
from domains.shared.perspective import (
    PERSONAL_PERSPECTIVE_MODELING_SYSTEM_PROMPT,
    PersonalPerspective,
)

_FINAL_MARKDOWN = """# demo 评审个人纪要

## 会议概况
申家坤负责压测，周五前提交报告。

## 要点梳理
压测和显存优化是本次主线。

## 相关行动
**本人相关**：
- 周五前提交报告

## 相关风险
**本人相关**：
- 显存不足

**待确认**：
- 确认测试范围

## 关键决策
- 周五上线
"""


def _understanding() -> MeetingUnderstanding:
    return MeetingUnderstanding(
        meeting_brief="demo 评审",
        meeting_purpose="确认上线窗口",
        speakers=[{"name": "申家坤"}],
        session_segments=[
            {
                "segment_title": "压测",
                "context_and_reasoning": "讨论压测和显存",
                "key_facts": ["周五上线"],
            }
        ],
        decisions=["周五上线"],
        open_questions=["确认测试范围"],
        risks=["显存不足"],
    )


def _perspective() -> PersonalPerspective:
    return PersonalPerspective(
        confidence="high",
        personal_summary="负责压测和显存优化。",
        focus_points=["压测", "显存"],
        possible_actions=["周五前提交报告"],
        collaborations=["张工：提供测试环境"],
        concerns=["显存不足"],
        data_gaps=["缺少驱动"],
        focus_risks=["上线窗口"],
        open_questions=["确认测试范围"],
    )


def _draft() -> Minutes:
    return Minutes(
        headline="demo 评审个人纪要",
        executive_summary=["申家坤负责压测，周五前提交报告。"],
        key_decisions=["周五上线"],
        personally_relevant_points=["**本人相关**：", "周五前提交报告"],
        risks_and_blockers=["**本人相关**：", "显存不足"],
        unresolved_questions=["确认测试范围"],
        history_comparison=[],
    )


def _review() -> MinutesSupervisorReview:
    return MinutesSupervisorReview(
        decision="approve",
        facts_check={"status": "pass", "findings": []},
        perspective_check={"status": "pass", "findings": []},
        consistency_check={"status": "pass", "findings": []},
        feedback=[],
    )


class _FakeClient:
    def __init__(self) -> None:
        self.structured_calls: list[tuple[object, str, str]] = []
        self.render_calls: list[tuple[str, str]] = []

    async def structured(self, system, user, model=None, contract=None, **kwargs):
        self.structured_calls.append((model, system, user))
        if model is MeetingUnderstanding:
            return _understanding()
        if model is PersonalPerspective:
            return _perspective()
        if model is Minutes:
            return _draft()
        if model is MinutesSupervisorReview:
            return _review()
        raise AssertionError(f"unexpected structured schema: {model!r}")

    async def text(self, prompt, user, **kwargs):
        self.render_calls.append((prompt, user))
        return _FINAL_MARKDOWN

    async def stream_text(self, prompt, user, **kwargs):
        self.render_calls.append((prompt, user))
        yield _FINAL_MARKDOWN


def test_personal_single_line_pipeline_with_fake_llm() -> None:
    client = _FakeClient()
    system = MeetingAgentSystem(client=client)
    template = resolve_task_template_format("personal_minutes")

    async def _consume():
        events = []
        async for event in system.run_streaming(
            transcript=(
                "申家坤 00:01\n负责压测，周五前提交报告。\n"
                "张工 00:10\n提供测试环境。\n"
                + "补充讨论内容。" * 1200
            ),
            user={
                "name": "申家坤",
                "name_aliases": ["家坤"],
                "role": "后端工程师",
                "focus_person": ["张工"],
                "focus_thing": ["压测"],
                "preferences": ["先说结论"],
            },
            templates={"minutes": template},
            lines=["minutes"],
            lang="zh",
        ):
            events.append(event)
        return events

    events = asyncio.run(_consume())
    types = [event.get("type") for event in events]
    assert "chunk" in types
    assert "done" in types

    full_text = "".join(
        event.get("text", "")
        for event in events
        if event.get("type") == "chunk" and event.get("line") == "minutes"
    )
    assert "## 会议概况" in full_text
    assert "## 相关风险" in full_text
    assert "**待确认**" in full_text

    perspective_calls = [
        (system_prompt, user)
        for model, system_prompt, user in client.structured_calls
        if model is PersonalPerspective
    ]
    assert len(perspective_calls) == 1
    assert perspective_calls[0][0] == PERSONAL_PERSPECTIVE_MODELING_SYSTEM_PROMPT
    assert "【个人证据包】" in perspective_calls[0][1]
    assert "action_hints" not in perspective_calls[0][1]
    assert "dependencies" not in perspective_calls[0][1]

    draft_calls = [
        (system_prompt, user)
        for model, system_prompt, user in client.structured_calls
        if model is Minutes
    ]
    assert len(draft_calls) == 1
    assert draft_calls[0][0] == MINUTES_PERSONAL_GENERATION_PROMPT
    draft_user = draft_calls[0][1]
    assert "会议理解：" in draft_user
    assert "用户视角模型：" in draft_user
    assert "用户画像" not in draft_user
    assert "【本用户命中】" not in draft_user
    assert "会议原文" not in draft_user

    supervisor_calls = [
        (system_prompt, user)
        for model, system_prompt, user in client.structured_calls
        if model is MinutesSupervisorReview
    ]
    assert len(supervisor_calls) == 1
    assert "个人视角审查范围" in supervisor_calls[0][0]
    assert "key_decisions" in supervisor_calls[0][0]
    supervisor_user = supervisor_calls[0][1]
    assert "纪要草稿：" in supervisor_user
    assert "【本用户命中】" not in supervisor_user
    assert "【重点关注雷达】" not in supervisor_user

    assert client.render_calls
    render_prompt, render_user = client.render_calls[0]
    assert render_prompt.startswith("你是个人视角会议纪要渲染器")
    assert "MINUTES_PERSONAL_RENDER_TEMPLATE_PROMPT" not in render_prompt
    assert "## [会议概况]" in render_user
    assert "用户画像" not in render_user
    assert "会议原文" not in render_user
    assert "【本用户命中】" not in render_user
