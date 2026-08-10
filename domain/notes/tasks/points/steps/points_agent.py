from __future__ import annotations

from llm_client import LLMClient

from ....models import Points
from ..contracts import POINTS_GENERATION_OUTPUT_CONTRACT
from ..prompts import POINTS_GENERATION_SYSTEM_PROMPT


class PointsAgent:
    """从笔记中提取并总结知识点。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Points:
        return await self.client.structured(
            POINTS_GENERATION_SYSTEM_PROMPT,
            shared_context,
            Points,
            POINTS_GENERATION_OUTPUT_CONTRACT,
        )