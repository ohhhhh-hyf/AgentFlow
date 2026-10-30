from __future__ import annotations

from domains.shared.supervisor import StructuredGenerationAgent

from ....models import ActionItems
from ..contracts import ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT
from ..prompts import ACTION_ITEMS_GENERATION_SYSTEM_PROMPT, build_actions_system_prompt


class ActionItemsAgent(StructuredGenerationAgent):
    """提取客观待办：输出单一扁平 actions 数组。"""

    system_prompt = ACTION_ITEMS_GENERATION_SYSTEM_PROMPT
    output_model = ActionItems
    output_contract = ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT
    label = "actions/agent"

    async def run(self, shared_context: str) -> ActionItems:
        return await self.client.structured(
            build_actions_system_prompt(shared_context),
            shared_context,
            self.output_model,
            self.output_contract,
            label="actions/agent",
            **self.extra_kwargs,
        )
