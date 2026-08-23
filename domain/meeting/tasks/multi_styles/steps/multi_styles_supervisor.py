from __future__ import annotations

from supervisor import GlobalSupervisor

from client import LLMClient
from ....models import MultiStylesSupervisorReview
from ..contracts import MULTI_STYLES_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import MULTI_STYLES_SUPERVISOR_DOMAIN_PROMPT


class MultiStylesSupervisor:
    """Review the 多样式纪要 draft."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            MULTI_STYLES_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> MultiStylesSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            MultiStylesSupervisorReview,
            MULTI_STYLES_SUPERVISOR_OUTPUT_CONTRACT,
            label="multi_styles/supervisor",
        )

