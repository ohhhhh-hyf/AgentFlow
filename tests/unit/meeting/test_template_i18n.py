"""多语种模板目录隔离、请求体 lang 校验与动态模板解析单元测试。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import (
    resolve_template_format,
    template_dir,
    template_key,
    template_registry,
)
from app.schemas import Extra, TaskRequest
from app.tasks import ApiError, _prepare, _runner_args, _template_file


def test_task_request_lang_validation():
    """测试 TaskRequest 第一层顶层字段 lang 校验与归一化。"""
    # 缺省为中文
    req_default = TaskRequest()
    assert req_default.lang == "zh"

    # 显式英文与别名大小写清洗
    req_en = TaskRequest(lang="en")
    assert req_en.lang == "en"

    req_en_upper = TaskRequest(lang="EN")
    assert req_en_upper.lang == "en"

    req_english = TaskRequest(lang="english")
    assert req_english.lang == "en"

    # 显式中文与别名清洗
    req_zh = TaskRequest(lang="zh")
    assert req_zh.lang == "zh"

    req_chinese = TaskRequest(lang="chinese")
    assert req_chinese.lang == "zh"

    # 非法语种取值拦截 (抛出 422 验证异常)
    with pytest.raises(ValidationError) as exc_info:
        TaskRequest(lang="fr")
    assert "lang 仅支持 'zh' 或 'en'" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info_jp:
        TaskRequest(lang="jp")
    assert "lang 仅支持 'zh' 或 'en'" in str(exc_info_jp.value)


def test_template_dir_and_registry_isolation():
    """测试模板目录与注册表严格按语种物理隔离。"""
    zh_dir = template_dir("zh")
    assert zh_dir.name == "zh"
    assert zh_dir.is_dir()

    en_dir = template_dir("en")
    assert en_dir.name == "en"
    assert en_dir.is_dir()

    # 默认调用指向中文
    default_dir = template_dir()
    assert default_dir.name == "zh"

    # 中文注册表包含 29 个模板
    reg_zh = template_registry("zh")
    assert len(reg_zh) == 29
    assert any("general_minutes" in k for k in reg_zh)
    assert any("project_progress" in k for k in reg_zh)

    # 英文注册表首期试点仅包含已英化的 general_minutes
    reg_en = template_registry("en")
    assert len(reg_en) >= 1
    assert any("general_minutes" in k for k in reg_en)
    # 严格隔离：未英化的模板绝对不出现在英文注册表中
    assert not any("project_progress" in k for k in reg_en)


def test_template_format_resolution_by_language():
    """测试按语种准确解析模板 format。"""
    # 1. 英文通用纪要解析
    en_fmt = resolve_template_format("general_minutes", lang="en")
    assert "# General Minutes" in en_fmt
    assert "[Executive Summary]" in en_fmt
    assert "[Key Discussion Points]" in en_fmt
    assert "[Decisions & Rulings]" in en_fmt
    assert "通用纪要" not in en_fmt

    # 支持英文标题匹配
    en_title_fmt = resolve_template_format("General Minutes", lang="en")
    assert "# General Minutes" in en_title_fmt

    # 2. 中文通用纪要解析
    zh_fmt = resolve_template_format("general_minutes", lang="zh")
    assert "# 通用纪要" in zh_fmt
    assert "[全文摘要]" in zh_fmt
    assert "[要点梳理]" in zh_fmt
    assert "[结论定调]" in zh_fmt

    zh_title_fmt = resolve_template_format("通用纪要", lang="zh")
    assert "# 通用纪要" in zh_title_fmt


def test_strict_isolation_untranslated_template():
    """测试严格语种隔离：英文模式请求未英化的模板，绝不回退至中文，返回空。"""
    # project_progress 尚未英化
    en_untranslated = resolve_template_format("project_progress", lang="en")
    assert en_untranslated == ""

    # 中文模式正常加载
    zh_translated = resolve_template_format("project_progress", lang="zh")
    assert len(zh_translated) > 0
    assert "项目概况" in zh_translated or "进度追踪" in zh_translated


def test_template_file_task_preparation():
    """测试 app.tasks._template_file 的多语种解析与非法拦截。"""
    # 英文模式加载 general_minutes 成功
    tpl_en = _template_file("meeting", "minutes", "general_minutes", lang="en")
    assert tpl_en is not None
    assert "General Minutes" in tpl_en.read_text(encoding="utf-8")

    # 中文模式加载 general_minutes 成功
    tpl_zh = _template_file("meeting", "minutes", "general_minutes", lang="zh")
    assert tpl_zh is not None
    assert "通用纪要" in tpl_zh.read_text(encoding="utf-8")

    # 英文模式请求尚未英化的模板，必须抛出 400 ApiError
    with pytest.raises(ApiError) as exc_info:
        _template_file("meeting", "minutes", "contract_vetting", lang="en")
    assert exc_info.value.status == 400
    assert "extra.template 非法" in exc_info.value.message


def test_prepare_and_runner_args_pipeline_pass_through():
    """测试 _prepare 与 _runner_args 全流程透传 lang 参数。"""
    # 1. 英文请求
    req_en = TaskRequest(
        lang="en",
        texts={"transcript": "Good morning team, let us review the sprint."},
        extra=Extra(template="general_minutes"),
    )
    p_en = _prepare("meeting", "minutes", req_en, user_id="test_user")
    assert p_en.lang == "en"
    args_en = _runner_args(p_en)
    assert args_en["lang"] == "en"
    tpl_path_en = p_en.templates.get("minutes")
    assert tpl_path_en is not None
    assert "General Minutes" in tpl_path_en.read_text(encoding="utf-8")

    # 2. 中文请求
    req_zh = TaskRequest(
        lang="zh",
        texts={"transcript": "各位早，今天我们做一下冲刺评审。"},
        extra=Extra(template="general_minutes"),
    )
    p_zh = _prepare("meeting", "minutes", req_zh, user_id="test_user")
    assert p_zh.lang == "zh"
    args_zh = _runner_args(p_zh)
    assert args_zh["lang"] == "zh"
    tpl_path_zh = p_zh.templates.get("minutes")
    assert tpl_path_zh is not None
    assert "通用纪要" in tpl_path_zh.read_text(encoding="utf-8")


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
        "headline": "Sprint Planning",
        "executive_summary": ["Team aligned on goals."],
        "key_decisions": ["Launch on Friday."],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
    }
    mock_client.structured = AsyncMock(return_value=dummy_minutes)

    agent = MinutesGenerationAgent(mock_client)

    # 1. 英文生成
    ctx_en = "输出语种要求：英文（English）\n\n上下文"
    await agent.run(ctx_en, lang="en")
    call_args_en = mock_client.structured.call_args
    sys_prompt_en = call_args_en[0][0]
    assert "【核心人设与交付目标】" in sys_prompt_en
    assert "你是专职的【英文（English）】会议纪要草稿 Agent" in sys_prompt_en
    assert "## 语言红线" in sys_prompt_en
    assert "[TBD]" in sys_prompt_en

    # 2. 验证 enforce_minutes_draft 英文默认标题为 'Meeting Minutes'
    draft_no_title = {"headline": "", "executive_summary": ["test"]}
    enforced_en = enforce_minutes_draft(draft_no_title, {}, lang="en")
    assert enforced_en["headline"] == "Meeting Minutes"

    enforced_zh = enforce_minutes_draft(draft_no_title, {}, lang="zh")
    assert enforced_zh["headline"] == "会议纪要"


@pytest.mark.anyio
async def test_minutes_supervisor_prompt_assembly():
    """测试审核 Supervisor 在 lang='en' 时首尾插槽装配与准则微调。"""
    mock_client = MagicMock()
    mock_client.structured = AsyncMock(return_value=MagicMock())

    supervisor = MinutesGenerationSupervisor(mock_client)
    ctx_en = "输出语种要求：英文（English）\n\n草稿上下文"
    await supervisor.review(ctx_en, lang="en")

    call_args_en = mock_client.structured.call_args
    sys_prompt_en = call_args_en[0][0]
    assert "【核心人设与交付目标】" in sys_prompt_en
    assert "你是专职的【英文（English）】纪要质量监督者" in sys_prompt_en
    assert "## 语言红线与审核准则" in sys_prompt_en
    assert "半角标点、[TBD] 状态标签与标准英文缩写属于标准公文规范" in sys_prompt_en


def test_minutes_render_prompt_and_fallback_draft():
    """测试渲染器 Prompt 插槽装配与零 LLM 确定性兜底渲染。"""
    # 1. 渲染 Prompt 测试
    render = MinutesGenerationRender(MagicMock())
    ctx_en = "输出语种要求：英文（English）\n\n草稿"
    prompt_en, user_en = render._prompt_and_user(ctx_en, "", lang="en")
    assert "【核心人设与交付目标】" in prompt_en
    assert "你是专职的【英文（English）】会议纪要渲染器" in prompt_en
    assert "## 语言红线" in prompt_en
    assert "标点符号统一使用标准半角英文标点" in prompt_en

    # 2. 确定性零 LLM 兜底渲染 (render_draft) - 英文模式
    state_en = {
        "lang": "en",
        "lines": {
            "minutes": {
                "draft": {
                    "headline": "AI Architecture Sync",
                    "executive_summary": ["Aligned on multi-agent protocol and language parameters."],
                    "key_decisions": ["Adopt slot-assembly architecture for all agents."],
                    "personally_relevant_points": ["[Alice] Deliver unit test suite by EOD."],
                    "risks_and_blockers": ["High concurrency token consumption."],
                    "unresolved_questions": ["Evaluation metrics for English draft quality."],
                }
            }
        }
    }
    rendered_en = MinutesGenerationRender.render_draft(state_en)
    assert "# AI Architecture Sync" in rendered_en
    assert "## Executive Summary" in rendered_en
    assert "## Key Decisions" in rendered_en
    assert "## Action Items" in rendered_en
    assert "## Risks & Blockers" in rendered_en
    assert "## Open Questions" in rendered_en
    # 确保无中文字符
    assert not any("\u4e00" <= c <= "\u9fff" for c in rendered_en)

    # 3. 空草稿英文模式
    empty_state_en = {"lang": "en", "lines": {"minutes": {"draft": {}}}}
    assert MinutesGenerationRender.render_draft(empty_state_en) == "Please refer directly to the meeting transcript."

    # 4. 中文模式零回归
    state_zh = {
        "lang": "zh",
        "lines": {
            "minutes": {
                "draft": {
                    "headline": "架构同步会",
                    "executive_summary": ["全员对齐技术方案。"],
                    "key_decisions": ["采用插槽装配模式。"],
                }
            }
        }
    }
    rendered_zh = MinutesGenerationRender.render_draft(state_zh)
    assert "## 全文摘要" in rendered_zh
    assert "## 关键决策" in rendered_zh


def test_render_gate_english_tags_whitelist():
    """测试渲染门禁对英文常见状态标签（如 [TBD], [Pending] 等）的放行与占位残留拦截。"""
    template = """# General Minutes

## [Executive Summary]
[Single paragraph, approx. 150–250 words: Overview of meeting]

## [Key Decisions]
[Focus on final approved resolutions: List item by item]
"""
    # 1. 包含合法的英文状态标签（[TBD], [Pending Confirmation], [Approved] 等）应放行通过
    valid_output = """# General Minutes

## Executive Summary
The team discussed the upcoming platform release and settled the timeline.

## Key Decisions
- **Feature Freeze**: Deadline set for Friday [Approved].
- **Security Audit**: Vendor contract is currently [Pending Confirmation].
- **Performance Benchmark**: GPU node provisioning is [TBD].
"""
    errors = validate_rendered_output(valid_output, template)
    assert errors == [], f"Expected no gate errors, got: {errors}"

    # 2. 真实残留未替换的模板说明占位符应被拦截
    unfilled_output = """# General Minutes

## Executive Summary
[Single paragraph, approx. 150–250 words: Overview of meeting]

## Key Decisions
- **Feature Freeze**: Done.
"""
    unfilled_errors = validate_rendered_output(unfilled_output, template)
    assert len(unfilled_errors) > 0
    assert any("残留占位符" in err for err in unfilled_errors)



@pytest.mark.anyio
async def test_end_to_end_english_minutes_pipeline():
    """测试普通纪要全流程流式编排链路英文穿透与输出。"""
    from domains.meeting.orchestrator import MeetingAgentSystem
    from domains.meeting.models import MeetingUnderstanding, Minutes, MinutesSupervisorReview

    mock_client = MagicMock()
    dummy_und = MeetingUnderstanding(
        meeting_brief="Brief overview of cloud migration meeting",
        meeting_purpose="Discuss cloud migration timeline",
        scene="通用",
        decisions=["Target migration completion by Nov 15th."],
        open_questions=["Vendor support SLA for weekends."],
        risks=["Network throughput during peak hours."],
    )
    dummy_draft = Minutes(
        headline="Cloud Migration Architecture Sync",
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

    system = MeetingAgentSystem(client=mock_client)
    template = resolve_template_format("general_minutes", lang="en")
    transcript = "Alex: We need to finalize the cloud migration deadline by Friday. Bob: Agreed, target is Nov 15th."

    events = []
    async for event in system.run_streaming(
        transcript=transcript,
        user={"name": "Alex"},
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
