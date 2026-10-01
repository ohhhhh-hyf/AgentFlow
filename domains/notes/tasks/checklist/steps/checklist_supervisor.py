from __future__ import annotations

from domains.shared.supervisor import StructuredDomainSupervisor

from ....models import ChecklistSupervisorReview
from ..contracts import CHECKLIST_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import CHECKLIST_SUPERVISOR_DOMAIN_PROMPT


class ChecklistSupervisor(StructuredDomainSupervisor):
    domain_prompt = CHECKLIST_SUPERVISOR_DOMAIN_PROMPT
    review_model = ChecklistSupervisorReview
    output_contract = CHECKLIST_SUPERVISOR_OUTPUT_CONTRACT
    label = "checklist/supervisor"
    extra_kwargs = {"max_tokens": 1024}
