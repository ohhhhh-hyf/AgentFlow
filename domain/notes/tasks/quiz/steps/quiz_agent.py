from __future__ import annotations

from llm_client import LLMClient

from ....models import Quiz
from ..contracts import QUIZ_GENERATION_OUTPUT_CONTRACT
from ..prompts import QUIZ_GENERATION_SYSTEM_PROMPT


class QuizAgent:
    """从笔记拆解可提问点并生成自测题。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Quiz:
        return await self.client.structured(
            QUIZ_GENERATION_SYSTEM_PROMPT,
            shared_context,
            Quiz,
            QUIZ_GENERATION_OUTPUT_CONTRACT,
        )
