from __future__ import annotations

from llm_client import LLMClient
from ..models import PerspectiveProfile
from .prompts import (
    PERSPECTIVE_MODELING_OUTPUT_CONTRACT,
    PERSPECTIVE_MODELING_SYSTEM_PROMPT,
)


class PerspectiveModelingAgent:
    """把静态用户画像转换为本次会议中的关注视角（支持个人/客观两种模式）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(
        self,
        transcript: str,
        user_json: str,
    ) -> PerspectiveProfile:
        return await self.client.structured(
            PERSPECTIVE_MODELING_SYSTEM_PROMPT,
            f"用户画像：\n{user_json}\n\n会议原文：\n{transcript}",
            PerspectiveProfile,
            PERSPECTIVE_MODELING_OUTPUT_CONTRACT,
        )
