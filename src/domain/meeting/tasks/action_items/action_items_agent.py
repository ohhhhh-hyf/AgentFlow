from __future__ import annotations

from llm_client import LLMClient
from ...models import ActionItems
from .prompts import (
    ACTION_ITEMS_OUTPUT_CONTRACT,
    ACTION_ITEMS_SYSTEM_PROMPT,
)


class ActionItemsAgent:
    """提取待办：个人模式筛本人待办；客观模式覆盖各方待办。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> ActionItems:
        return await self.client.structured(
            ACTION_ITEMS_SYSTEM_PROMPT,
            shared_context,
            ActionItems,
            ACTION_ITEMS_OUTPUT_CONTRACT,
        )
