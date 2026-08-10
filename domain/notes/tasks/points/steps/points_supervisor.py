from __future__ import annotations

from supervisor import GlobalSupervisor

from llm_client import LLMClient
from ....models import PointsSupervisorReview
from ..contracts import POINTS_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import POINTS_SUPERVISOR_DOMAIN_PROMPT


class PointsSupervisor:
    """知识点总结任务的领域监督者。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            POINTS_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> PointsSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            PointsSupervisorReview,
            POINTS_SUPERVISOR_OUTPUT_CONTRACT,
        )