from __future__ import annotations

from domain._shared import StructuredDomainSupervisor

from ....models import QuizSupervisorReview
from ..contracts import QUIZ_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import QUIZ_SUPERVISOR_DOMAIN_PROMPT


class QuizSupervisor(StructuredDomainSupervisor):
    """审核自测题：不能靠抄原文作答。"""

    domain_prompt = QUIZ_SUPERVISOR_DOMAIN_PROMPT
    review_model = QuizSupervisorReview
    output_contract = QUIZ_SUPERVISOR_OUTPUT_CONTRACT
    label = "quiz/supervisor"
