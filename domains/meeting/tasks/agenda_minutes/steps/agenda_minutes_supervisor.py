from __future__ import annotations

from domains.shared.supervisor import StructuredDomainSupervisor

from ....models import AgendaMinutesSupervisorReview
from ..contracts import AGENDA_MINUTES_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import AGENDA_MINUTES_SUPERVISOR_DOMAIN_PROMPT


class AgendaMinutesSupervisor(StructuredDomainSupervisor):
    """议程驱动型会议纪要领域监督者。"""

    domain_prompt = AGENDA_MINUTES_SUPERVISOR_DOMAIN_PROMPT
    review_model = AgendaMinutesSupervisorReview
    output_contract = AGENDA_MINUTES_SUPERVISOR_OUTPUT_CONTRACT
    label = "agenda_minutes/supervisor"
    extra_kwargs = {"max_tokens": 3000}
