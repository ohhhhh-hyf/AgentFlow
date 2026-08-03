from __future__ import annotations

from ..client import DeepSeekClient
from ..models import MeetingUnderstanding


class MeetingUnderstandingAgent:
    """从会议原文中提取议题、决策、风险和未决问题。"""

    SYSTEM_PROMPT = """你是会议理解 Agent。请忠实还原会议内容、议题、结论、分歧、风险与未决问题。
规则：
- 只根据会议原文，不补充原文没有的信息。
- 区分“讨论/建议”和“正式决策”。
- 不得编造负责人、日期或结论。
- 保留对后续纪要和待办有用的具体信息。"""

    OUTPUT_CONTRACT = """{
  "meeting_purpose": "字符串",
  "topics": [
    {
      "title": "字符串",
      "discussion": "字符串",
      "conclusion": "字符串或null",
      "participants": ["字符串"]
    }
  ],
  "decisions": ["字符串"],
  "open_questions": ["字符串"],
  "risks": ["字符串"]
}"""

    def __init__(self, client: DeepSeekClient) -> None:
        self.client = client

    async def run(self, transcript: str) -> MeetingUnderstanding:
        return await self.client.structured(
            self.SYSTEM_PROMPT,
            f"会议原文：\n{transcript}",
            MeetingUnderstanding,
            self.OUTPUT_CONTRACT,
        )
