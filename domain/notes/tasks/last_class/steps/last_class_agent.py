from __future__ import annotations

from llm_client import LLMClient

from ....models import LastClass
from ..contracts import LAST_CLASS_GENERATION_OUTPUT_CONTRACT
from ..prompts import LAST_CLASS_GENERATION_SYSTEM_PROMPT


class LastClassAgent:
    """把老师划重点文本抽成重点知识点，并写满精讲与补充备忘。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> LastClass:
        return await self.client.structured(
            LAST_CLASS_GENERATION_SYSTEM_PROMPT,
            shared_context,
            LastClass,
            LAST_CLASS_GENERATION_OUTPUT_CONTRACT,
        )
