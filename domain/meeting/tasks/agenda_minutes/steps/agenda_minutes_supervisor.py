from __future__ import annotations

from domain._shared import GlobalSupervisor

from tools.llm import LLMClient
from ....models import AgendaMinutesSupervisorReview
from ..contracts import AGENDA_MINUTES_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import AGENDA_MINUTES_SUPERVISOR_DOMAIN_PROMPT


class AgendaMinutesSupervisor:
    """议程驱动型会议纪要领域监督者。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            AGENDA_MINUTES_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> AgendaMinutesSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            AgendaMinutesSupervisorReview,
            AGENDA_MINUTES_SUPERVISOR_OUTPUT_CONTRACT,
            label="agenda_minutes/supervisor",
            max_tokens=3000,
        )
