from __future__ import annotations

from ..client import LLMClient
from ..models import PersonalizedMinutes


class MinutesGenerationAgent:
    """基于会议理解和视角模型生成纪要草稿（个人视角或客观全员视角）。"""

    SYSTEM_PROMPT = """你是会议纪要草稿 Agent。请基于会议理解、用户画像和视角模型生成结构化纪要草稿。

先读取上下文中的「视角模式」以及用户画像的 perspective 字段：

【视角模式 = objective，或 perspective = "objective"】客观全员视角
- 面向全体参会人与相关方，公平覆盖各方信息，保持事实中立；
- executive_summary 概括全会目的、主线讨论与结论；
- key_decisions 列出全部正式决策；
- personally_relevant_points 在此模式下表示「全员应知晓的关键执行要点与分工节点」
  （字段名沿用契约，内容必须是全员视角，不要写成某一个人的待办清单）；
- risks_and_blockers / unresolved_questions 覆盖会议中的全部明确风险与未决问题；
- 不要把事项强行归到单一人物；需要点名时使用原文明示的多方负责人；
- 不输出“你需要”“请你”等用户视角措辞。

【视角模式 = personal，或 perspective 缺省】个人用户视角（默认）
- 提高与用户职责直接相关内容的权重；
- 不遗漏会影响该用户的关键全局决策、风险和未决事项；
- personally_relevant_points 写与该用户职责/承诺直接相关的要点；
- 正文中不要出现「你」「您」等第二人称代词：直接删掉即可，例如「你需要」写成「需要」。

通用规则：
- 不得把建议写成正式决策；
- 不得创造会议原文没有的信息。"""

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
