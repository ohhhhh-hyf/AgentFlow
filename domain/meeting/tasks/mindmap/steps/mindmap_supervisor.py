from __future__ import annotations

from supervisor import GlobalSupervisor

from llm_client import LLMClient
from ....models import MindmapSupervisorReview
from ..contracts import MINDMAP_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import MINDMAP_SUPERVISOR_DOMAIN_PROMPT


class MindmapSupervisor:
    """Review the 思维导图 draft."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            MINDMAP_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> MindmapSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            MindmapSupervisorReview,
            MINDMAP_SUPERVISOR_OUTPUT_CONTRACT,
            label="mindmap/supervisor",
        )
