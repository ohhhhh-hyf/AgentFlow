"""Step 3：minutes prompt map + 议程专用输出契约 + 议程审核 prompt 清理。"""
from __future__ import annotations

import asyncio

from domains.meeting.models_generated import Minutes
from domains.meeting.tasks.minutes.contracts import (
    MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT,
    MINUTES_GENERATION_OUTPUT_CONTRACT,
)
from domains.meeting.tasks.minutes.prompt_map import (
    is_agenda_view,
    minutes_prompt_set,
    prompt_label,
    resolve_prompt_view,
)
from domains.meeting.tasks.minutes.prompts import (
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_AGENDA_RENDER_PROMPT,
    MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    MINUTES_OBJECTIVE_RENDER_PROMPT,
    MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
    MINUTES_PERSONAL_GENERATION_PROMPT,
    MINUTES_PERSONAL_RENDER_PROMPT,
    MINUTES_PERSONAL_SUPERVISOR_PROMPT,
    MINUTES_RENDER_TEMPLATE_PROMPT,
)
from domains.meeting.tasks.minutes.steps.minutes_agent import MinutesGenerationAgent
from domains.meeting.views import (
    VIEW_AGENDA_OBJECTIVE,
    VIEW_OBJECTIVE,
    VIEW_PERSONAL,
    VIEW_ROLE_TEMPLATE,
)

_CONTRACT_KEYS = (
    "headline",
    "executive_summary",
    "key_decisions",
    "personally_relevant_points",
    "risks_and_blockers",
    "unresolved_questions",
    "history_comparison",
)


def test_resolve_prompt_view() -> None:
    assert (
        resolve_prompt_view("议题模式：agenda_enhanced\n视角模式：objective")
        == VIEW_AGENDA_OBJECTIVE
    )
    assert resolve_prompt_view("视角模式：personal") == VIEW_PERSONAL
    assert resolve_prompt_view("视角模式：role_template") == VIEW_ROLE_TEMPLATE
    assert resolve_prompt_view("视角模式：objective") == VIEW_OBJECTIVE
    assert resolve_prompt_view("") == VIEW_OBJECTIVE


def test_prompt_sets_by_view() -> None:
    agenda = minutes_prompt_set(VIEW_AGENDA_OBJECTIVE)
    assert agenda.generation is MINUTES_AGENDA_GENERATION_PROMPT
    assert agenda.supervisor is MINUTES_AGENDA_SUPERVISOR_PROMPT
    assert agenda.render is MINUTES_AGENDA_RENDER_PROMPT
    assert agenda.render_template is MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    assert is_agenda_view(agenda.view)
    assert prompt_label(agenda.view) == "agenda"

    personal = minutes_prompt_set(VIEW_PERSONAL)
    assert personal.generation is MINUTES_PERSONAL_GENERATION_PROMPT
    assert personal.supervisor is MINUTES_PERSONAL_SUPERVISOR_PROMPT
    assert personal.render is MINUTES_PERSONAL_RENDER_PROMPT
    assert personal.render_template is MINUTES_RENDER_TEMPLATE_PROMPT
    assert prompt_label(personal.view) == "personal"

    # role_template 沿用 objective prompts（与既有行为一致），但保留 view 标签
    role = minutes_prompt_set(VIEW_ROLE_TEMPLATE)
    assert role.view == VIEW_ROLE_TEMPLATE
    assert role.generation is MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert role.supervisor is MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
    assert role.render is MINUTES_OBJECTIVE_RENDER_PROMPT
    assert role.render_template is MINUTES_RENDER_TEMPLATE_PROMPT
    assert prompt_label(role.view) == "objective"

    # 未知 view 回退 objective，不抛 500
    fallback = minutes_prompt_set("unknown")
    assert fallback.generation is MINUTES_OBJECTIVE_GENERATION_PROMPT


def test_agenda_contract_is_clean() -> None:
    contract = MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT
    assert "个人" not in contract
    assert "MeetingUnderstanding" not in contract
    for key in _CONTRACT_KEYS:
        assert f'"{key}"' in contract
    # 与共享契约保持同一组 key，便于下游 Minutes 模型校验
    for key in _CONTRACT_KEYS:
        assert f'"{key}"' in MINUTES_GENERATION_OUTPUT_CONTRACT


def test_agenda_agent_uses_agenda_contract() -> None:
    captured: dict = {}

    class FakeClient:
        async def structured(self, system, user, model, contract, **kwargs):
            captured["system"] = system
            captured["contract"] = contract
            return Minutes(headline="")

    agent = MinutesGenerationAgent(FakeClient())
    agenda_context = (
        "议题模式：agenda_enhanced\n"
        "视角模式：objective\n\n"
        "会议理解：\n{}\n"
    )
    asyncio.run(agent.run(agenda_context, source_transcript="tagged transcript"))
    assert captured["contract"] == MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT
    combined = captured["system"] + "\n" + captured["contract"]
    assert "个人模式下" not in combined
    assert "来自MeetingUnderstanding" not in combined
    assert "MeetingUnderstanding" not in combined

    captured.clear()
    normal_context = "视角模式：objective\n\n会议理解：\n{}\n"
    asyncio.run(agent.run(normal_context))
    assert captured["contract"] == MINUTES_GENERATION_OUTPUT_CONTRACT


def test_agenda_supervisor_prompt_drops_upstream_carry_claims() -> None:
    prompt = MINUTES_AGENDA_SUPERVISOR_PROMPT
    assert "搬运项免审" not in prompt
    assert "上游事实搬运项" not in prompt
    assert "历史记忆隔离审查" not in prompt
    assert "本轮送审范围" in prompt
    assert "历史记忆审查" in prompt
    # 既有放行规则必须保留
    assert "属于符合公文规范的表述优化，予以充分认可并放行通过" in prompt

    # 普通 objective/personal 审核 prompt 不受影响
    assert "搬运项免审" in MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
    assert "搬运项免审" in MINUTES_PERSONAL_SUPERVISOR_PROMPT
