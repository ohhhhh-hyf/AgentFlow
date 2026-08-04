from __future__ import annotations

from ..client import LLMClient
from ..models import ActionItems
from ..prompts.action_items import OUTPUT_CONTRACT, SYSTEM_PROMPT


class ActionItemsAgent:
    """提取待办：个人模式筛本人待办；客观模式覆盖各方待办。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> ActionItems:
        return await self.client.structured(
            SYSTEM_PROMPT,
            shared_context,
            ActionItems,
            OUTPUT_CONTRACT,
        )
