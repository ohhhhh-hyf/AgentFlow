from __future__ import annotations

from llm_client import LLMClient
from ...models import PersonalizedMinutes
from .prompts import (
    MINUTES_GENERATION_OUTPUT_CONTRACT,
    MINUTES_GENERATION_SYSTEM_PROMPT,
)


class MinutesGenerationAgent:
    """基于会议理解和视角模型生成纪要草稿（个人视角或客观全员视角）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> PersonalizedMinutes:
        return await self.client.structured(
            MINUTES_GENERATION_SYSTEM_PROMPT,
            shared_context,
            PersonalizedMinutes,
            MINUTES_GENERATION_OUTPUT_CONTRACT,
        )
