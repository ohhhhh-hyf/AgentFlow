"""Step 1：冻结待办客观化目标契约。

本阶段只冻结目标，不切换运行时契约；Step 2 再把 ACTION_ITEM_FIELDS /
ActionItemsGenerationContract / Prompt / Agent 切到目标。
"""
from __future__ import annotations

import asyncio

from domains.meeting.tasks.actions.contracts import (
    ACTIONS_OBJECTIVE_ITEM_FIELD_NAMES,
    ACTIONS_OBJECTIVE_OUTPUT_FIELDS,
    ACTIONS_OBJECTIVE_REMOVED_ITEM_FIELDS,
    ACTIONS_OBJECTIVE_REMOVED_OUTPUT_FIELDS,
    ACTION_ITEM_FIELDS,
    ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT,
    ActionItemsGenerationContract,
)
from domains.meeting.tasks.actions.prompts import (
    ACTION_ITEMS_GENERATION_SYSTEM_PROMPT,
)
from domains.meeting.tasks.actions.steps.actions_agent import ActionItemsAgent


def test_actions_objective_output_is_frozen() -> None:
    assert ACTIONS_OBJECTIVE_OUTPUT_FIELDS == (
        "assigned_actions",
        "unassigned_actions",
    )
    assert ACTIONS_OBJECTIVE_REMOVED_OUTPUT_FIELDS == (
        "my_actions",
        "delegated_actions",
    )


def test_actions_objective_item_fields_are_frozen_to_eight() -> None:
    assert ACTIONS_OBJECTIVE_ITEM_FIELD_NAMES == (
        "category",
        "task",
        "owner",
        "deadline",
        "collaborators",
        "acceptance_criteria",
        "dependency",
        "evidence",
    )
    assert len(ACTIONS_OBJECTIVE_ITEM_FIELD_NAMES) == 8


def test_removed_item_fields_are_not_in_target() -> None:
    for field in ACTIONS_OBJECTIVE_REMOVED_ITEM_FIELDS:
        assert field not in ACTIONS_OBJECTIVE_ITEM_FIELD_NAMES


def test_runtime_contract_matches_frozen_target_after_step_2() -> None:
    """Step 2：运行时契约已切到目标字段，旧字段不再出现。"""
    current = {field.name for field in ACTION_ITEM_FIELDS}
    assert tuple(field.name for field in ACTION_ITEM_FIELDS) == ACTIONS_OBJECTIVE_ITEM_FIELD_NAMES
    for field in ACTIONS_OBJECTIVE_REMOVED_ITEM_FIELDS:
        assert field not in current


def test_runtime_contract_is_objective_and_has_no_personal_arrays() -> None:
    contract = ActionItemsGenerationContract.to_output_contract()
    for field in ACTIONS_OBJECTIVE_OUTPUT_FIELDS:
        assert field in contract
    for field in ACTIONS_OBJECTIVE_REMOVED_OUTPUT_FIELDS:
        assert field not in contract


def test_actions_agent_is_always_objective() -> None:
    captured: dict = {}

    class FakeClient:
        async def structured(self, system, user, model, contract, **kwargs):
            captured.update(
                system=system,
                contract=contract,
                label=kwargs.get("label"),
            )
            return object()

    agent = ActionItemsAgent(FakeClient())
    asyncio.run(agent.run("视角模式：personal\n\n会议原文：测试"))

    assert captured["system"] == ACTION_ITEMS_GENERATION_SYSTEM_PROMPT
    assert captured["contract"] == ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT
    assert captured["label"] == "actions/agent"
