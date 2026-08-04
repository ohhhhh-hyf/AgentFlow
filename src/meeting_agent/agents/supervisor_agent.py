from __future__ import annotations

from ..client import LLMClient
from ..models import SupervisorReview
from ..prompts.supervisor import OUTPUT_CONTRACT, SYSTEM_PROMPT


class SupervisorAgent:
    """审核中间结果，并决定放行、定向返工或拒绝（支持个人/客观视角）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def review(self, context: str) -> SupervisorReview:
        return await self.client.structured(
            SYSTEM_PROMPT,
            context,
            SupervisorReview,
            OUTPUT_CONTRACT,
        )
