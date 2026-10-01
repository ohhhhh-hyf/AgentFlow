from __future__ import annotations

from domains.shared.supervisor import StructuredGenerationAgent

from ....models import ConsensusDecision
from ..contracts import CONSENSUS_DECISION_GENERATION_OUTPUT_CONTRACT
from ..prompts import CONSENSUS_DECISION_GENERATION_SYSTEM_PROMPT


class ConsensusDecisionAgent(StructuredGenerationAgent):
    """基于会议理解和会议原文提炼共识成色与因果决策推演草稿。"""

    system_prompt = CONSENSUS_DECISION_GENERATION_SYSTEM_PROMPT
    output_model = ConsensusDecision
    output_contract = CONSENSUS_DECISION_GENERATION_OUTPUT_CONTRACT
    label = "consensus_decision/agent"
    extra_kwargs = {"temperature": 0.0}
