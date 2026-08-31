from __future__ import annotations

from client import LLMClient

from ....models import Risk
from ..contracts import RISK_GENERATION_OUTPUT_CONTRACT
from ..prompts import RISK_GENERATION_SYSTEM_PROMPT


class RiskAgent:
    """从会议中提取风险、阻碍和隐患。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Risk:
        return await self.client.structured(
            RISK_GENERATION_SYSTEM_PROMPT,
            shared_context,
            Risk,
            RISK_GENERATION_OUTPUT_CONTRACT,
            label="risk/agent",
        )

