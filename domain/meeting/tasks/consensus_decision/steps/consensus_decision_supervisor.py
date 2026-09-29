from __future__ import annotations

from domain._shared import StructuredDomainSupervisor

from ....models import ConsensusDecisionSupervisorReview
from ..contracts import CONSENSUS_DECISION_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import CONSENSUS_DECISION_SUPERVISOR_DOMAIN_PROMPT


class ConsensusDecisionSupervisor(StructuredDomainSupervisor):
    """共识决策任务的领域监督者。

    一次 LLM 调用完成全局标准 + 共识成色/得失真实性/引句真实性双重评判。
    """

    domain_prompt = CONSENSUS_DECISION_SUPERVISOR_DOMAIN_PROMPT
    review_model = ConsensusDecisionSupervisorReview
    output_contract = CONSENSUS_DECISION_SUPERVISOR_OUTPUT_CONTRACT
    label = "consensus_decision/supervisor"
    extra_kwargs = {"temperature": 0.0}
