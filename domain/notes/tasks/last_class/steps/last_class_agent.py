from __future__ import annotations

from llm_client import LLMClient

from ....models import LastClass
from ..contracts import LAST_CLASS_GENERATION_OUTPUT_CONTRACT
from ..prompts import LAST_CLASS_GENERATION_SYSTEM_PROMPT


class LastClassAgent:
    """把老师最后一课文本抽成考点：原话、公式要点、方法、例题和精讲。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> LastClass:
        return await self.client.structured(
            LAST_CLASS_GENERATION_SYSTEM_PROMPT,
            shared_context,
            LastClass,
            LAST_CLASS_GENERATION_OUTPUT_CONTRACT,
        )
