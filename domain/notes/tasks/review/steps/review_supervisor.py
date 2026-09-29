from __future__ import annotations

from domain._shared import StructuredDomainSupervisor

from ....models import ReviewSupervisorReview
from ..contracts import REVIEW_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import REVIEW_SUPERVISOR_DOMAIN_PROMPT


class ReviewSupervisor(StructuredDomainSupervisor):
    """审核笔记审查草稿：quote 必须能对上原文。"""

    domain_prompt = REVIEW_SUPERVISOR_DOMAIN_PROMPT
    review_model = ReviewSupervisorReview
    output_contract = REVIEW_SUPERVISOR_OUTPUT_CONTRACT
    label = "review/supervisor"
