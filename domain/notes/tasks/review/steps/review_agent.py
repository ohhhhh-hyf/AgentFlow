from __future__ import annotations

from llm_client import LLMClient

from ....models import Review
from ..contracts import REVIEW_GENERATION_OUTPUT_CONTRACT
from ..prompts import REVIEW_GENERATION_SYSTEM_PROMPT


class ReviewAgent:
    """从笔记中抽取知识点与记录问题。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Review:
        return await self.client.structured(
            REVIEW_GENERATION_SYSTEM_PROMPT,
            shared_context,
            Review,
            REVIEW_GENERATION_OUTPUT_CONTRACT,
        )
