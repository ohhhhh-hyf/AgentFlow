from __future__ import annotations

from ..client import LLMClient
from ..models import PerspectiveProfile


class PerspectiveModelingAgent:
    """把静态用户画像转换为本次会议中的用户关注视角。"""

    SYSTEM_PROMPT = """你是用户视角建模 Agent。请结合用户提供的身份画像和会议原文，建立本次会议中的用户视角模型。
规则：
- 用户显式提供的姓名、角色、部门和职责视为事实，不得被模型推断覆盖。
- 只补充画像中缺失、且能从会议原文谨慎推断的信息。
- 证据不足时字段可以为空，并降低 confidence。
- 关注用户职责、目标、关注点，以及与用户直接相关的议题。"""

    OUTPUT_CONTRACT = """{
  "confidence": "high|medium|low",
  "name": "字符串或null",
  "inferred_role": "字符串或null",
  "responsibilities": ["字符串"],
  "goals": ["字符串"],
  "concerns": ["字符串"],
  "relevant_topics": ["字符串"],
  "evidence": ["字符串"]
}"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(
        self,
        transcript: str,
        user_json: str,
    ) -> PerspectiveProfile:
        return await self.client.structured(
            self.SYSTEM_PROMPT,
            f"用户画像：\n{user_json}\n\n会议原文：\n{transcript}",
            PerspectiveProfile,
            self.OUTPUT_CONTRACT,
        )
