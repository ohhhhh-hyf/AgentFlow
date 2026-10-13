from __future__ import annotations

from core.execution.hard_execution import parse_perspective_mode
from domains.shared.supervisor import StructuredGenerationAgent

from ....models import ActionItems
from ..contracts import (
    ACTION_ITEMS_GENERATION_OUTPUT_CONTRACT,
    ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT,
    ACTION_ITEMS_PERSONAL_GENERATION_OUTPUT_CONTRACT,
)
from ..prompts import (
    ACTION_ITEMS_GENERATION_SYSTEM_PROMPT,
    ACTION_ITEMS_OBJECTIVE_GENERATION_PROMPT,
    ACTION_ITEMS_PERSONAL_GENERATION_PROMPT,
)


class ActionItemsAgent(StructuredGenerationAgent):
    """提取待办：个人模式筛本人待办；客观模式覆盖各方待办。"""

    system_prompt = ACTION_ITEMS_GENERATION_SYSTEM_PROMPT
    output_model = ActionItems
    output_contract = ACTION_ITEMS_GENERATION_OUTPUT_CONTRACT
    label = "actions/agent"

    async def run(self, shared_context: str) -> ActionItems:
        mode = parse_perspective_mode(shared_context)
        if mode in ("personal", "role_template"):
            prompt = ACTION_ITEMS_PERSONAL_GENERATION_PROMPT
            contract = ACTION_ITEMS_PERSONAL_GENERATION_OUTPUT_CONTRACT
        else:
            prompt = ACTION_ITEMS_OBJECTIVE_GENERATION_PROMPT
            contract = ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT

        return await self.client.structured(
            prompt,
            shared_context,
            self.output_model,
            contract,
            label=f"actions/agent/{mode}",
            **self.extra_kwargs,
        )
