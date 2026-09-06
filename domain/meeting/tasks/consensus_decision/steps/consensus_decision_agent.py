from __future__ import annotations

from client import LLMClient
from ....models import ConsensusDecision
from ..contracts import CONSENSUS_DECISION_GENERATION_OUTPUT_CONTRACT
from ..prompts import CONSENSUS_DECISION_GENERATION_SYSTEM_PROMPT


class ConsensusDecisionAgent:
    """基于会议理解和会议原文提炼共识成色与因果决策推演草稿。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> ConsensusDecision:
        return await self.client.structured(
            CONSENSUS_DECISION_GENERATION_SYSTEM_PROMPT,
            shared_context,
            ConsensusDecision,
            CONSENSUS_DECISION_GENERATION_OUTPUT_CONTRACT,
            temperature=0.0,
            label="consensus_decision/agent",
        )
