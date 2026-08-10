from __future__ import annotations

from llm_client import LLMClient
from ..models import MeetingUnderstanding
from .prompts import (
    MEETING_UNDERSTANDING_SYSTEM_PROMPT,
)
from .contracts import MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT


class MeetingUnderstandingAgent:
    """从会议原文中提取议题、决策、风险和未决问题。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, transcript: str) -> MeetingUnderstanding:
        return await self.client.structured(
            MEETING_UNDERSTANDING_SYSTEM_PROMPT,
            f"会议原文：\n{transcript}",
            MeetingUnderstanding,
            MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT,
        )
