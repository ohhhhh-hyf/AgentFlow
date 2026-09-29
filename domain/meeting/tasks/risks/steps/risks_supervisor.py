from __future__ import annotations

from domain._shared import StructuredDomainSupervisor

from ....models import RiskSupervisorReview
from ..contracts import RISK_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import RISK_SUPERVISOR_DOMAIN_PROMPT


class RiskSupervisor(StructuredDomainSupervisor):
    """风险分析任务的领域监督者。"""

    domain_prompt = RISK_SUPERVISOR_DOMAIN_PROMPT
    review_model = RiskSupervisorReview
    output_contract = RISK_SUPERVISOR_OUTPUT_CONTRACT
    # 注意：label 是 risk/ 而不是 risks/（历史拼写，改名会变监控口径）
    label = "risk/supervisor"
