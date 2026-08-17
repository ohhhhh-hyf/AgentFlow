from __future__ import annotations

from supervisor import GlobalSupervisor

from llm_client import LLMClient
from ....models import LastClassSupervisorReview
from ..contracts import LAST_CLASS_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import LAST_CLASS_SUPERVISOR_DOMAIN_PROMPT


class LastClassSupervisor:
    """审核划重点抽取：忠实原文 + 程度分级合理。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            LAST_CLASS_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> LastClassSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            LastClassSupervisorReview,
            LAST_CLASS_SUPERVISOR_OUTPUT_CONTRACT,
        )
