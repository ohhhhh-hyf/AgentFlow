from __future__ import annotations

from domain._shared import StructuredDomainSupervisor

from ....models import MinutesTraceSupervisorReview
from ..contracts import MINUTES_TRACE_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import MINUTES_TRACE_SUPERVISOR_DOMAIN_PROMPT


class MinutesTraceSupervisor(StructuredDomainSupervisor):
    """审核溯源纪要正文。"""

    domain_prompt = MINUTES_TRACE_SUPERVISOR_DOMAIN_PROMPT
    review_model = MinutesTraceSupervisorReview
    output_contract = MINUTES_TRACE_SUPERVISOR_OUTPUT_CONTRACT
    label = "minutes_trace/supervisor"
