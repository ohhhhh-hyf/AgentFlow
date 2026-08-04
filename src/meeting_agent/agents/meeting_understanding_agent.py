from __future__ import annotations

from ..client import LLMClient
from ..models import MeetingUnderstanding
from ..prompts.meeting_understanding import OUTPUT_CONTRACT, SYSTEM_PROMPT


class MeetingUnderstandingAgent:
    """从会议原文中提取议题、决策、风险和未决问题。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, transcript: str) -> MeetingUnderstanding:
        return await self.client.structured(
            SYSTEM_PROMPT,
            f"会议原文：\n{transcript}",
            MeetingUnderstanding,
            OUTPUT_CONTRACT,
        )
