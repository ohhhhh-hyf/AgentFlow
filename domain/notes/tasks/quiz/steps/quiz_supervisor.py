from __future__ import annotations

from supervisor import GlobalSupervisor

from llm_client import LLMClient
from ....models import QuizSupervisorReview
from ..contracts import QUIZ_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import QUIZ_SUPERVISOR_DOMAIN_PROMPT


class QuizSupervisor:
    """审核自测题：不能靠抄原文作答。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            QUIZ_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> QuizSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            QuizSupervisorReview,
            QUIZ_SUPERVISOR_OUTPUT_CONTRACT, label='quiz/supervisor')
