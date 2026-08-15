from __future__ import annotations

from supervisor import GlobalSupervisor

from llm_client import LLMClient
from ....models import ReviewSupervisorReview
from ..contracts import REVIEW_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import REVIEW_SUPERVISOR_DOMAIN_PROMPT


class ReviewSupervisor:
    """审核笔记审查草稿：quote 必须能对上原文。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            REVIEW_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> ReviewSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            ReviewSupervisorReview,
            REVIEW_SUPERVISOR_OUTPUT_CONTRACT,
        )
