from __future__ import annotations

from ..client import LLMClient
from ..models import PersonalizedMinutes
from ..prompts.minutes_generation import OUTPUT_CONTRACT, SYSTEM_PROMPT


class MinutesGenerationAgent:
    """基于会议理解和视角模型生成纪要草稿（个人视角或客观全员视角）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> PersonalizedMinutes:
        return await self.client.structured(
            SYSTEM_PROMPT,
            shared_context,
            PersonalizedMinutes,
            OUTPUT_CONTRACT,
        )
