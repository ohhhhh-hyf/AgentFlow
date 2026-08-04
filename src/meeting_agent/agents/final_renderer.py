from __future__ import annotations

from ..client import LLMClient
from ..models import FinalReport


class FinalRenderer:
    """把 Supervisor 已放行的内容渲染为最终展示结果。"""

    SYSTEM_PROMPT = """你是最终结果渲染器。Supervisor 已经完成事实与证据审核，你只能根据已批准的内容生成最终展示结果，不得重新推理、补充或改写业务事实。
规则：
- personalized_minutes 必须是一段完整、连贯的字符串，不得使用数组、分点或编号。
- 纪要突出与用户职责相关的讨论，同时保留影响用户的关键全局决策、风险和未决事项。
- personalized_minutes 与 action_items 的 task 中不要出现「你」「您」：直接去掉该字即可（如「你需要」→「需要」），不要改写成姓名或角色称呼。
- action_items 只保留当前用户本人明确负责或明确承诺的事项。
- 不得保留属于他人、负责人为空，或仅凭角色推断的事项。
- 不得合并不同动作、负责人或截止时间。
- 不得新增 Supervisor 已批准内容之外的事实。
- 除 title、personalized_minutes、action_items 外，不要输出其他顶层字段。"""

    OUTPUT_CONTRACT = """{
  "title": "字符串",
  "personalized_minutes": "一段完整、连贯的字符串",
  "action_items": [
    {
      "task": "字符串",
      "owner": "字符串或null",
      "deadline": "字符串或null",
      "priority": "high|medium|low",
      "status": "explicit|inferred",
      "evidence": "字符串",
      "confidence": "high|medium|low"
    }
  ]
}"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, approved_context: str) -> FinalReport:
        return await self.client.structured(
            self.SYSTEM_PROMPT,
            approved_context,
            FinalReport,
            self.OUTPUT_CONTRACT,
        )
