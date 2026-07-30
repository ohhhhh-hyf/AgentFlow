from __future__ import annotations

from ..client import DeepSeekClient
from ..models import PersonalizedMinutes


class MinutesGenerationAgent:
    """基于会议理解和用户视角生成个性化纪要草稿。"""

    SYSTEM_PROMPT = """你是个性化会议纪要 Agent。基于会议理解和用户画像生成简洁、准确、便于该用户决策的纪要。
规则：提高与用户职责相关内容的权重，但不可遗漏关键全局决策；不得把提议写成决策；不要创造原文没有的信息。"""

    OUTPUT_CONTRACT = """{
  "headline": "字符串",
  "executive_summary": ["字符串"],
  "key_decisions": ["字符串"],
  "personally_relevant_points": ["字符串"],
  "risks_and_blockers": ["字符串"],
  "unresolved_questions": ["字符串"]
}"""

    def __init__(self, client: DeepSeekClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> PersonalizedMinutes:
        return await self.client.structured(
            self.SYSTEM_PROMPT,
            shared_context,
            PersonalizedMinutes,
            self.OUTPUT_CONTRACT,
        )
