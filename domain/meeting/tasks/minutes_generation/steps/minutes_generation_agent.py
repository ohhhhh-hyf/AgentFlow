from __future__ import annotations

from llm_client import LLMClient
from ....models import Minutes
from ..prompts import (
    MINUTES_GENERATION_SYSTEM_PROMPT,
)
from ..contracts import MINUTES_GENERATION_OUTPUT_CONTRACT


class MinutesGenerationAgent:
    """基于会议理解和视角模型生成纪要草稿（个人视角或客观全员视角）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Minutes:
        return await self.client.structured(
            MINUTES_GENERATION_SYSTEM_PROMPT,
            shared_context,
            Minutes,
            MINUTES_GENERATION_OUTPUT_CONTRACT,
        )
