from __future__ import annotations

from client import LLMClient
from .models import PerspectiveModeling
from .prompts import PERSPECTIVE_MODELING_SYSTEM_PROMPT
from .contracts import PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT


class PerspectiveModelingAgent:
    """Map a static user profile onto the current input context."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(
        self,
        transcript: str,
        user_json: str,
    ) -> PerspectiveModeling:
        return await self.client.structured(
            PERSPECTIVE_MODELING_SYSTEM_PROMPT,
            f"用户画像：\n{user_json}\n\n原文：\n{transcript}",
            PerspectiveModeling,
            PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT,
            label="core/perspective_modeling",
        )

