from __future__ import annotations

from domains.shared.supervisor import StructuredGenerationAgent

from ....models import ActionItems
from ..contracts import ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT
from ..prompts import ACTION_ITEMS_GENERATION_SYSTEM_PROMPT


class ActionItemsAgent(StructuredGenerationAgent):
    """提取客观待办：直接从会议原文分组、分点并输出待办字段。"""

    system_prompt = ACTION_ITEMS_GENERATION_SYSTEM_PROMPT
    output_model = ActionItems
    output_contract = ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT
    label = "actions/agent"

    async def run(self, shared_context: str) -> ActionItems:
        return await self.client.structured(
            ACTION_ITEMS_GENERATION_SYSTEM_PROMPT,
            shared_context,
            self.output_model,
            ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT,
            label="actions/agent",
            **self.extra_kwargs,
        )
