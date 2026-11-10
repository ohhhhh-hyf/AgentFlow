# 拆分自原大文件，保留：test_english_length_budget_and_word_count, test_parse_lang_mode, test_meeting_understanding_prompt_assembly…

"""多语种模板目录隔离、请求体 lang 校验与动态模板解析单元测试。"""

from __future__ import annotations
import pytest
from pydantic import ValidationError
from app.config import (
    resolve_agenda_template_format,
    resolve_template_format,
    template_dir,
    template_key,
    template_registry,
)
from app.schemas import Extra, TaskRequest
from app.tasks import ApiError, _prepare, _runner_args, _template_file
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock
import pytest
from core.execution.hard_execution import enforce_minutes_draft, parse_lang_mode
from core.templates.length_budget import english_budget_line, word_count
from core.templates.router import validate_rendered_output
from domains.meeting.meeting_core.meeting_understanding_agent import MeetingUnderstandingAgent
from domains.meeting.tasks.minutes.steps.minutes_agent import MinutesGenerationAgent
from domains.meeting.tasks.minutes.steps.minutes_render import MinutesGenerationRender
from domains.meeting.tasks.minutes.steps.minutes_supervisor import MinutesGenerationSupervisor

pytestmark = pytest.mark.integration

def test_english_length_budget_and_word_count():
    """测试英文单词计数与篇幅预算生成。"""
    text = "Good morning everyone. Today we are gathered to discuss the Q3 roadmap, deliverables, and architecture."
    count = word_count(text)
    assert count == 15

    # 预算档位验证
    budget_short = english_budget_line(800, columns=3)
    assert "【Length Budget】" in budget_short
    assert "Source text ~800 words, template has 3 sections" in budget_short
    assert "400–" in budget_short

    budget_medium = english_budget_line(2500)
    assert "600–1800 words" in budget_medium

    budget_too_short = english_budget_line(50)
    assert budget_too_short == ""


def test_parse_lang_mode():
    """测试多语种模式上下文解析。"""
    assert parse_lang_mode("输出语种要求：英文（English）\n\n其他内容") == "en"
    assert parse_lang_mode("输出语种要求：\n英文（English）\n\n其他内容") == "en"
    assert parse_lang_mode("lang: en\n\n其他内容") == "en"
    assert parse_lang_mode("输出语种要求：中文\n\n其他内容") == "zh"
    assert parse_lang_mode("无语种声明上下文") == "zh"


@pytest.mark.anyio
async def test_meeting_understanding_prompt_assembly():
    """测试会议理解 Agent 在 lang='en' 时首尾插槽装配与中文零回归。"""
    mock_client = MagicMock()
    mock_client.structured = AsyncMock(return_value=MagicMock())

    agent = MeetingUnderstandingAgent(mock_client)

    # 1. 英文模式
    await agent.run("Meeting transcript text...", lang="en")
    call_args_en = mock_client.structured.call_args
    sys_prompt_en = call_args_en[0][0]
    assert "【核心人设与交付目标】" in sys_prompt_en
    assert "你是专职的【英文（English）】会议理解助手" in sys_prompt_en
    assert "## 语言红线" in sys_prompt_en
    assert "所有字段必须严格使用【英文（English）】输出" in sys_prompt_en
    assert "你是会议理解助手。你的任务是从会议原文中提取" not in sys_prompt_en

    # 2. 中文模式 (原样零修改保留)
    await agent.run("会议纪要原文...", lang="zh")
    call_args_zh = mock_client.structured.call_args
    sys_prompt_zh = call_args_zh[0][0]
    assert "你是会议理解助手。你的任务是从会议原文中提取" in sys_prompt_zh
    assert "【核心人设与交付目标】" not in sys_prompt_zh


@pytest.mark.anyio
async def test_minutes_agent_prompt_and_carry_enforce():
    """测试草稿 Agent 在 lang='en' 时首尾插槽装配与 hard_execution 英文对齐。"""
    mock_client = MagicMock()
    # 模拟返回合法 Minutes 结构
    dummy_minutes = MagicMock()
    dummy_minutes.model_dump.return_value = {
        "executive_summary": ["Team aligned on goals."],
        "key_decisions": ["Launch on Friday."],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
        "history_comparison": [],
    }
    mock_client.structured = AsyncMock(return_value=dummy_minutes)

    agent = MinutesGenerationAgent(mock_client)

    # 1. 英文生成
    ctx_en = "输出语种要求：英文（English）\n\n上下文"
    await agent.run(ctx_en, view="objective", lang="en")
    call_args_en = mock_client.structured.call_args
    sys_prompt_en = call_args_en[0][0]
    assert "【核心人设与交付目标】" in sys_prompt_en
    assert "你是专职的【英文（English）】会议纪要草稿 Agent" in sys_prompt_en
    assert "## 语言红线" in sys_prompt_en
    assert "[TBD]" in sys_prompt_en

    # 2. 验证 enforce_minutes_draft 补全 6 核心字段且不引入 headline
    draft_partial = {"executive_summary": ["test"]}
    enforced = enforce_minutes_draft(draft_partial, {}, lang="en")
    assert "headline" not in enforced
    assert enforced["executive_summary"] == ["test"]
    assert enforced["key_decisions"] == []


@pytest.mark.anyio
async def test_minutes_supervisor_prompt_assembly():
    """测试审核 Supervisor 在 lang='en' 时首尾插槽装配与准则微调。"""
    mock_client = MagicMock()
    mock_client.structured = AsyncMock(return_value=MagicMock())

    supervisor = MinutesGenerationSupervisor(mock_client)
    ctx_en = "输出语种要求：英文（English）\n\n草稿上下文"
    await supervisor.review(ctx_en, view="objective", lang="en")

    call_args_en = mock_client.structured.call_args
    sys_prompt_en = call_args_en[0][0]
    assert "【核心人设与交付目标】" in sys_prompt_en
    assert "你是专职的【英文（English）】纪要质量监督者" in sys_prompt_en
    assert "## 语言红线与审核准则" in sys_prompt_en
    assert "半角标点、[TBD] 状态标签与标准英文缩写属于标准公文规范" in sys_prompt_en


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("context", "view"),
    [
        (
            "视角模式：objective\n输出语种要求：英文（English）\n\n草稿上下文",
            "objective",
        ),
        (
            "视角模式：personal\n输出语种要求：英文（English）\n\n草稿上下文",
            "personal",
        ),
        (
            "议题模式：agenda_enhanced\n视角模式：objective\n输出语种要求：英文（English）\n\n草稿上下文",
            "agenda_objective",
        ),
    ],
)
async def test_supervisor_english_prompt_keeps_common_rules(context, view):
    """英文壳只剥人设首句，不能把公共审核规则切掉。"""
    mock_client = MagicMock()
    mock_client.structured = AsyncMock(return_value=MagicMock())

    supervisor = MinutesGenerationSupervisor(mock_client)
    await supervisor.review(context, view=view, lang="en")

    prompt = mock_client.structured.call_args[0][0]
    assert "## 领域审核规则：纪要生成" in prompt
    assert "## 整体标准（所有领域通用的评判准则）" in prompt
    assert "只审送审稿中实际出现的内容" in prompt


@pytest.mark.anyio
async def test_end_to_end_english_minutes_pipeline():
    """测试普通纪要全流程流式编排链路英文穿透与输出。"""
    from domains.meeting.orchestrator import MeetingAgentSystem
    from domains.meeting.models import MeetingUnderstanding, Minutes, MinutesSupervisorReview

    mock_client = MagicMock()
    dummy_und = MeetingUnderstanding(
        meeting_brief="Brief overview of cloud migration meeting",
        meeting_purpose="Discuss cloud migration timeline",
        decisions=["Target migration completion by Nov 15th."],
        open_questions=["Vendor support SLA for weekends."],
        risks=["Network throughput during peak hours."],
    )
    dummy_draft = Minutes(
        executive_summary=["The engineering team aligned on the Nov 15th cloud migration milestone."],
        key_decisions=["Target migration completion by Nov 15th."],
        personally_relevant_points=["[Bob] Submit migration runbook by Friday."],
        risks_and_blockers=["Network throughput during peak hours."],
        unresolved_questions=["Vendor support SLA for weekends."],
        history_comparison=[],
    )
    dummy_review = MinutesSupervisorReview(
        decision="approve",
        facts_check={"status": "pass", "findings": []},
        perspective_check={"status": "pass", "findings": []},
        consistency_check={"status": "pass", "findings": []},
        feedback=[],
    )

    calls = []
    async def mock_structured(sys_prompt, user_msg, model=None, schema=None, **kwargs):
        calls.append((schema, sys_prompt))
        if schema == MeetingUnderstanding:
            return dummy_und
        elif schema == Minutes:
            return dummy_draft
        elif schema == MinutesSupervisorReview:
            return dummy_review
        return dummy_draft

    mock_client.structured = AsyncMock(side_effect=mock_structured)

    render_calls = []
    async def mock_text(prompt, user, **kwargs):
        render_calls.append((prompt, user))
        return """# General Minutes

## Executive Summary
The engineering team aligned on the Nov 15th cloud migration milestone.

## Key Discussion Points
- Migration schedule and weekend downtime allowances.

## Decisions & Rulings
- Finalize cloud migration runbook by Friday."""

    mock_client.text = AsyncMock(side_effect=mock_text)

    async def mock_stream_text(prompt, user, **kwargs):
        render_calls.append((prompt, user))
        yield """# General Minutes

## Executive Summary
The engineering team aligned on the Nov 15th cloud migration milestone.

## Key Discussion Points
- Migration schedule and weekend downtime allowances.

## Decisions & Rulings
- Finalize cloud migration runbook by Friday."""

    mock_client.stream_text = mock_stream_text

    system = MeetingAgentSystem(client=mock_client)
    template = resolve_template_format("general_minutes", lang="en")
    transcript = "Alex: We need to finalize the cloud migration deadline by Friday. Bob: Agreed, target is Nov 15th."

    events = []
    async for event in system.run_streaming(
        transcript=transcript,
        # 英文全链路测试锁定 objective 路径；personal 单线走新的 PersonalPerspective 链路，
        # 其草稿上下文/渲染在阶段 3 单独验收。
        user={"name": "Alex", "perspective": "objective"},
        templates={"minutes": template},
        lines=["minutes"],
        lang="en",
    ):
        events.append(event)

    # 1. 验证关键事件产出
    types = [e.get("type") for e in events]
    assert "chunk" in types
    assert "done" in types

    chunk_events = [e for e in events if e.get("type") == "chunk" and e.get("line") == "minutes"]
    assert len(chunk_events) > 0
    full_text = "".join(e.get("text", "") for e in chunk_events)
    assert "# General Minutes" in full_text
    assert "## Executive Summary" in full_text

    # 2. 验证各 Agent System Prompt 均已挂载英文核心人设与语言红线
    for s, p in calls:
        assert "【核心人设与交付目标】" in p
        assert "英文（English）" in p
        assert "## 语言红线" in p

    assert len(render_calls) > 0
    render_prompt, _ = render_calls[0]
    assert "【核心人设与交付目标】" in render_prompt
    assert "## 语言红线" in render_prompt


@pytest.mark.anyio
async def test_prepared_run_lang_propagation():
    """测试 PreparedRun 包含 lang 字段并正确透传至 run_streaming。"""
    from core.runner.runner import PreparedRun

    # 1. 验证 PreparedRun 默认及显式传参
    default_prep = PreparedRun(
        ctx=MagicMock(),
        system=MagicMock(),
        user=MagicMock(),
        transcript="test",
        line_names=["minutes"],
        template_texts={},
        line_extra={},
        memory_bind=None,
        memory_enabled=False,
        graph_silent=False,
        usage_before={},
        task_monitor=None,
        subject=None,
    )
    assert default_prep.lang == "zh"

    en_prep = PreparedRun(
        ctx=MagicMock(),
        system=MagicMock(),
        user=MagicMock(),
        transcript="test",
        line_names=["minutes"],
        template_texts={},
        line_extra={},
        memory_bind=None,
        memory_enabled=False,
        graph_silent=False,
        usage_before={},
        task_monitor=None,
        subject=None,
        lang="en",
    )
    assert en_prep.lang == "en"


@pytest.mark.anyio
async def test_agenda_en_generation_prompt_uses_roman_headings():
    from domains.meeting.models import Minutes
    from domains.meeting.tasks.minutes.steps.minutes_agent import MinutesGenerationAgent

    captured: dict = {}

    class FakeClient:
        async def structured(self, system, *args, **kwargs):
            captured["system"] = system
            return Minutes()

    agent = MinutesGenerationAgent(FakeClient())
    ctx = (
        "议题模式：agenda_enhanced\n"
        "视角模式：objective\n"
        "输出语种要求：英文（English）\n\n"
        "会议理解：\n{}"
    )
    await agent.run(
        ctx,
        view="agenda_objective",
        lang="en",
        source_transcript="tagged transcript",
    )

    prompt = captured["system"]
    assert "### I." in prompt
    assert "### 一." not in prompt
    assert "罗马数字序号" in prompt
    assert "中文数字序号" not in prompt


@pytest.mark.anyio
async def test_agenda_en_supervisor_prompt_uses_roman_headings():
    from domains.meeting.tasks.minutes.steps.minutes_supervisor import (
        MinutesGenerationSupervisor,
    )

    mock_client = MagicMock()
    mock_client.structured = AsyncMock(return_value=MagicMock())
    supervisor = MinutesGenerationSupervisor(mock_client)
    ctx = (
        "议题模式：agenda_enhanced\n"
        "视角模式：objective\n"
        "输出语种要求：英文（English）\n\n"
        "草稿上下文"
    )
    await supervisor.review(ctx, view="agenda_objective", lang="en")

    prompt = mock_client.structured.call_args[0][0]
    assert "### I." in prompt
    assert "### II." in prompt
    assert "### 一." not in prompt
    assert "三级标题序号" in prompt
    assert "中文数字序号" not in prompt
    assert "标题一致性口径" in prompt
    assert "忽略大小写" in prompt
    assert "语义被改写" in prompt
