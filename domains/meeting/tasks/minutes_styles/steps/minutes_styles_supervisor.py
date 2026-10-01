from __future__ import annotations

from domains.shared.supervisor import StructuredDomainSupervisor

from ....models import MultiStylesSupervisorReview
from ..contracts import MULTI_STYLES_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import MULTI_STYLES_SUPERVISOR_DOMAIN_PROMPT


class MultiStylesSupervisor(StructuredDomainSupervisor):
    """Review the 多样式纪要 draft."""

    domain_prompt = MULTI_STYLES_SUPERVISOR_DOMAIN_PROMPT
    review_model = MultiStylesSupervisorReview
    output_contract = MULTI_STYLES_SUPERVISOR_OUTPUT_CONTRACT
    label = "minutes_styles/supervisor"
