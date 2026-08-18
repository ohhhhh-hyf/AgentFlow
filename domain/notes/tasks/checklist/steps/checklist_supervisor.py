from __future__ import annotations

from supervisor import GlobalSupervisor

from llm_client import LLMClient
from ....models import ChecklistSupervisorReview
from ..contracts import CHECKLIST_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import CHECKLIST_SUPERVISOR_DOMAIN_PROMPT


class ChecklistSupervisor:
    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            CHECKLIST_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> ChecklistSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            ChecklistSupervisorReview,
            CHECKLIST_SUPERVISOR_OUTPUT_CONTRACT, label='checklist/supervisor')
