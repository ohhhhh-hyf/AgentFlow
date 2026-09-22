from __future__ import annotations

from domain._shared import GlobalSupervisor

from tools.llm import LLMClient
from ....models import ConsensusDecisionSupervisorReview
from ..contracts import CONSENSUS_DECISION_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import CONSENSUS_DECISION_SUPERVISOR_DOMAIN_PROMPT


class ConsensusDecisionSupervisor:
    """共识决策任务的领域监督者。

    一次 LLM 调用完成全局标准 + 共识成色/得失真实性/引句真实性双重评判。
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            CONSENSUS_DECISION_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> ConsensusDecisionSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            ConsensusDecisionSupervisorReview,
            CONSENSUS_DECISION_SUPERVISOR_OUTPUT_CONTRACT,
            temperature=0.0,
            label="consensus_decision/supervisor",
        )
