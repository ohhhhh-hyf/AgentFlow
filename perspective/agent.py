from __future__ import annotations

from llm_client import LLMClient
from .models import PerspectiveModeling
from .prompts import (
    PERSPECTIVE_MODELING_SYSTEM_PROMPT,
)
from .contracts import PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT


class PerspectiveModelingAgent:
    """把静态用户画像转换为本次会议中的关注视角（支持个人/客观两种模式）。

    公共组件：输入只有 transcript + user_json，输出自包含的
    PerspectiveModeling 模型，不依赖任何 domain 特有逻辑，可被
    任意 domain 的 domain_core 直接复用。
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(
        self,
        transcript: str,
        user_json: str,
    ) -> PerspectiveModeling:
        return await self.client.structured(
            PERSPECTIVE_MODELING_SYSTEM_PROMPT,
            f"用户画像：\n{user_json}\n\n会议原文：\n{transcript}",
            PerspectiveModeling,
            PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT,
        )
