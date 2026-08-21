from __future__ import annotations

from supervisor import GlobalSupervisor

from llm_client import LLMClient
from ....models import MinutesTraceSupervisorReview
from ..contracts import MINUTES_TRACE_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import MINUTES_TRACE_SUPERVISOR_DOMAIN_PROMPT


class MinutesTraceSupervisor:
    """审核溯源纪要正文。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            MINUTES_TRACE_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> MinutesTraceSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            MinutesTraceSupervisorReview,
            MINUTES_TRACE_SUPERVISOR_OUTPUT_CONTRACT,
            label="minutes_trace/supervisor",
        )
