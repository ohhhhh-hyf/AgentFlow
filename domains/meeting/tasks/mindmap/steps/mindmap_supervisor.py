from __future__ import annotations

from domains.shared.supervisor import StructuredDomainSupervisor

from ....models import MindmapSupervisorReview
from ..contracts import MINDMAP_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import MINDMAP_SUPERVISOR_DOMAIN_PROMPT


class MindmapSupervisor(StructuredDomainSupervisor):
    """Review the 思维导图 draft."""

    domain_prompt = MINDMAP_SUPERVISOR_DOMAIN_PROMPT
    review_model = MindmapSupervisorReview
    output_contract = MINDMAP_SUPERVISOR_OUTPUT_CONTRACT
    label = "mindmap/supervisor"
