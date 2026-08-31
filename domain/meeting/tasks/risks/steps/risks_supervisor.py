from __future__ import annotations

from supervisor import GlobalSupervisor

from client import LLMClient
from ....models import RiskSupervisorReview
from ..contracts import RISK_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import RISK_SUPERVISOR_DOMAIN_PROMPT


class RiskSupervisor:
    """风险分析任务的领域监督者。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            RISK_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> RiskSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            RiskSupervisorReview,
            RISK_SUPERVISOR_OUTPUT_CONTRACT,
            label="risk/supervisor",
        )
