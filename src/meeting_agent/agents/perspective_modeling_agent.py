from __future__ import annotations

from ..client import LLMClient
from ..models import PerspectiveProfile


class PerspectiveModelingAgent:
    """把静态用户画像转换为本次会议中的关注视角（支持个人/客观两种模式）。"""

    SYSTEM_PROMPT = """你是视角建模 Agent。请结合身份画像和会议原文，建立本次会议中的视角模型。

先读取用户画像中的 perspective 字段，选择模式：

【perspective = "objective"】客观全员视角
- 不绑定任何真实个人；name 保持 null（除非画像显式给出记录员名称）；
- inferred_role 写“客观会议记录/全员视角”一类中立角色；
- responsibilities / goals 对齐：完整还原会议目的、决策、风险、未决，以及各方分工与待办；
- concerns 关注：决策口径不一致、责任未分配、证据不足、遗漏相关方任务；
- relevant_topics 覆盖会议主要议题，不要只挑单一角色相关内容；
- evidence 引用原文中体现“需要全员信息/多方任务”的依据；
- 不要虚构具体个人身份，不要把客观记录视角伪装成某个参会人。

【perspective 缺省或其它值】个人用户视角（默认）
- 用户显式提供的姓名、角色、部门和职责视为事实，不得被模型推断覆盖；
- 只补充画像中缺失、且能从会议原文谨慎推断的信息；
- 证据不足时字段可以为空，并降低 confidence；
- 关注用户职责、目标、关注点，以及与用户直接相关的议题。

通用规则：
- 不得创造会议原文没有的事实；
- confidence 反映视角建模整体可靠程度。"""

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
