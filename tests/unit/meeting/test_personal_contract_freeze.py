"""Step 1：冻结个人单线视角的输入/输出契约。

这些断言只锁“契约形状”，不测试实现细节。后续接 PersonalPerspective、
草稿上下文和渲染上下文时，任何字段漂移都应在这里先失败。
"""
from __future__ import annotations

import re

from app.config import resolve_task_template_format
from domains.meeting.tasks.minutes.contracts import (
    PersonalMinutesGenerationContract,
)
from domains.meeting.tasks.minutes.prompt_map import render_template_prompt
from domains.meeting.tasks.minutes.prompts import (
    MINUTES_PERSONAL_GENERATION_PROMPT,
    MINUTES_PERSONAL_RENDER_TEMPLATE_PROMPT,
    MINUTES_PERSONAL_SUPERVISOR_PROMPT,
)
from domains.meeting.views import VIEW_PERSONAL

PERSONAL_UNDERSTANDING_FIELDS = (
    "meeting_brief",
    "speakers",
    "session_segments",
    "decisions",
)

PERSONAL_PERSPECTIVE_FIELDS = (
    "confidence",
    "personal_summary",
    "focus_points",
    "possible_actions",
    "collaborations",
    "concerns",
    "data_gaps",
    "focus_risks",
    "open_questions",
)

PERSONAL_DRAFT_FIELDS = (
    "headline",
    "executive_summary",
    "key_decisions",
    "personally_relevant_points",
    "risks_and_blockers",
    "unresolved_questions",
    "history_comparison",
)

PERSONAL_RENDER_COLUMNS = (
    "会议概况",
    "要点梳理",
    "相关行动",
    "相关风险",
    "关键决策",
)


def test_personal_generation_prompt_freezes_4_plus_9_inputs() -> None:
    prompt = MINUTES_PERSONAL_GENERATION_PROMPT
    for field in PERSONAL_UNDERSTANDING_FIELDS:
        assert field in prompt, field
    for field in PERSONAL_PERSPECTIVE_FIELDS:
        assert field in prompt, field

    # 旧输入/旧字段不能重新漂回个人草稿 Prompt
    for forbidden in (
        "meeting_purpose",
        "action_hints",
        "risk_hints",
        "dependencies",
        "attention_points",
        "relevant_topics",
        "responsibilities",
    ):
        assert forbidden not in prompt, forbidden


def test_personal_draft_contract_has_exactly_7_fields() -> None:
    assert tuple(f.name for f in PersonalMinutesGenerationContract.fields) == PERSONAL_DRAFT_FIELDS
    contract = PersonalMinutesGenerationContract.to_output_contract()
    assert "session_segments" in contract
    assert "focus_points" in contract
    assert "attention_points" not in contract
    assert "responsibilities" not in contract


def test_personal_render_prompt_is_selected_and_uses_five_columns() -> None:
    prompt = MINUTES_PERSONAL_RENDER_TEMPLATE_PROMPT
    assert render_template_prompt(VIEW_PERSONAL) is prompt

    for anchor in (
        "executive_summary[0]",
        "executive_summary[1:]",
        "personally_relevant_points",
        "risks_and_blockers",
        "unresolved_questions",
        "**待确认**：",
        "key_decisions",
        "headline",
        "history_comparison",
    ):
        assert anchor in prompt, anchor

    # 通用渲染 prompt 不能把个人视角规则带回来
    from domains.meeting.tasks.minutes.prompts import MINUTES_RENDER_TEMPLATE_PROMPT

    assert "个人视角看板呈现" not in MINUTES_RENDER_TEMPLATE_PROMPT
    assert "本人牵头推进" not in MINUTES_RENDER_TEMPLATE_PROMPT


def test_personal_template_has_five_columns_and_pending_group() -> None:
    template = resolve_task_template_format("personal_minutes")
    titles = re.findall(r"^## \[([^\]]+)\]$", template, re.M)
    assert tuple(titles) == PERSONAL_RENDER_COLUMNS
    assert "**待确认**" in template
    assert "2–5 段" not in template


def test_personal_supervisor_prompt_freezes_review_scope() -> None:
    prompt = MINUTES_PERSONAL_SUPERVISOR_PROMPT
    assert "个人视角审查范围" in prompt
    for field in (
        "key_decisions",
        "personally_relevant_points",
        "risks_and_blockers",
        "unresolved_questions",
    ):
        assert field in prompt, field
