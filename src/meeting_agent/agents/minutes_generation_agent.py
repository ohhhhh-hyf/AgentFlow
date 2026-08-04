from __future__ import annotations

from ..client import LLMClient
from ..models import PersonalizedMinutes


class MinutesGenerationAgent:
    """基于会议理解和用户视角生成个性化纪要草稿。"""

    SYSTEM_PROMPT = """你是个性化会议纪要 Agent。请基于会议理解和用户画像，生成简洁、准确、便于该用户决策的纪要草稿。
规则：
- 提高与用户职责直接相关内容的权重。
- 不遗漏会影响用户的关键全局决策、风险和未决事项。
- 不得把建议写成正式决策。
- 不得创造会议原文没有的信息。
- 正文中不要出现「你」「您」等第二人称代词：直接删掉即可，例如「你需要」写成「需要」，「与你相关」写成「相关」；不要改成姓名或角色称呼。"""

    OUTPUT_CONTRACT = """{
  "headline": "字符串",
  "executive_summary": ["字符串"],
  "key_decisions": ["字符串"],
  "personally_relevant_points": ["字符串"],
  "risks_and_blockers": ["字符串"],
  "unresolved_questions": ["字符串"]
}"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> PersonalizedMinutes:
        return await self.client.structured(
            self.SYSTEM_PROMPT,
            shared_context,
            PersonalizedMinutes,
            self.OUTPUT_CONTRACT,
        )
