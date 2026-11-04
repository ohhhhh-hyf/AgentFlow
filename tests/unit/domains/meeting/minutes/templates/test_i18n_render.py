# 拆分自 test_i18n.py，覆盖：test_minutes_render_prompt_and_fallback_draft, test_render_gate_english_tags_whitelist, test_localize_agenda_headings_for_en…

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

def test_minutes_render_prompt_and_fallback_draft():
    """测试渲染器模板 Prompt 装配与零 LLM 确定性兜底渲染。"""
    # 1. 模板渲染 Prompt 测试（无模板 LLM prompt 已删除）
    render = MinutesGenerationRender(MagicMock())
    ctx_en = "输出语种要求：英文（English）\n\n草稿"
    prompt_en, user_en = render._prompt_and_user(
        ctx_en,
        "# Template\n{{scalar:Summary}}",
        view="objective",
        lang="en",
    )
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


def test_localize_agenda_headings_for_en():
    from domains.meeting.tasks.minutes.prompts import localize_agenda_headings_for_en

    text = "### 一. 议题A / ### 二. 议题B / 中文数字序号"
    out = localize_agenda_headings_for_en(text)
    assert "### I. 议题A" in out
    assert "### II. 议题B" in out
    assert "罗马数字序号" in out
    assert "### 一." not in out
    assert "### 二." not in out
    assert "中文数字序号" not in out


def test_agenda_en_render_prompt_uses_roman_headings():
    from domains.meeting.tasks.minutes.steps.minutes_render import (
        MinutesGenerationRender,
    )

    render = MinutesGenerationRender(MagicMock())
    ctx = (
        "议题模式：agenda_enhanced\n"
        "视角模式：objective\n"
        "输出语种要求：英文（English）\n\n"
        "草稿"
    )
    prompt, _ = render._prompt_and_user(
        ctx,
        "# Template\n{{scalar:要点梳理}}",
        view="agenda_objective",
        lang="en",
    )
    assert "### I." in prompt
    assert "### 一." not in prompt


def test_personal_en_render_prompt_uses_normal_template_prompt():
    """非 agenda 的 personal / role_template 不进入议题渲染 prompt。"""
    from domains.meeting.tasks.minutes.steps.minutes_render import (
        MinutesGenerationRender,
    )

    render = MinutesGenerationRender(MagicMock())
    ctx = "视角模式：personal\n输出语种要求：英文（English）\n\n草稿"
    prompt, _ = render._prompt_and_user(
        ctx,
        "# Template\n{{scalar:Summary}}",
        view="personal",
        lang="en",
    )
    assert "【核心人设与交付目标】" in prompt
    assert "【栏目语义自适应映射】" not in prompt
    assert "严格遵循模板栏目规约与公文层级标准完成排版" not in prompt


def test_agenda_zh_prompts_keep_chinese_headings():
    from domains.meeting.tasks.minutes.prompts import (
        MINUTES_AGENDA_GENERATION_PROMPT,
        MINUTES_AGENDA_SUPERVISOR_PROMPT,
    )

    for prompt in (
        MINUTES_AGENDA_GENERATION_PROMPT,
        MINUTES_AGENDA_SUPERVISOR_PROMPT,
    ):
        assert "### 一." in prompt
        assert "### I." not in prompt

    assert "中文数字序号" in MINUTES_AGENDA_GENERATION_PROMPT
    assert "三级标题序号" in MINUTES_AGENDA_SUPERVISOR_PROMPT


def test_agenda_supervisor_title_normalization_rule():
    from domains.meeting.tasks.minutes.prompts import MINUTES_AGENDA_SUPERVISOR_PROMPT

    prompt = MINUTES_AGENDA_SUPERVISOR_PROMPT
    assert "### 标题一致性口径" in prompt
    assert "忽略大小写" in prompt
    assert "连续空白" in prompt
    assert "连字符差异" in prompt
    assert "语义被改写" in prompt
    assert "英文标题保留原文" in prompt
    assert "标题比对口径" in prompt
