from __future__ import annotations

from ..client import DeepSeekClient
from ..models import ActionItems


class ActionItemsAgent:
    """提取本人、他人和未分配待办，供 Supervisor 校准筛选。"""

    SYSTEM_PROMPT = """你是待办事项 Agent。请提取可执行行动，并按本人、他人、未分配分类。
规则：
- my_actions 只能包含原文明示当前用户负责，或当前用户本人明确承诺完成的事项。
- 不得仅凭用户角色、职责、关注点或会议上下文推断当前用户是负责人。
- 会议决策、风险关注和条件触发本身不等于个人待办。
- 原文没有明确负责人的事项放入 unassigned_actions，owner 必须为 null。
- 他人明确负责的事项放入 delegated_actions。
- 一个待办只描述一个可独立完成的动作。
- 同一句发言中包含多个动作，或动作具有不同截止时间时，必须拆成多条待办。
- 截止时间无明确证据时使用 null。
- 每项必须提供能证明负责人和任务内容的简短原文依据。
- 避免把一般讨论误判为任务。"""

    OUTPUT_CONTRACT = """{
  "my_actions": [
    {
      "task": "字符串",
      "owner": "字符串或null",
      "deadline": "字符串或null",
      "priority": "high|medium|low",
      "status": "explicit|inferred",
      "evidence": "字符串",
      "confidence": "high|medium|low"
    }
  ],
  "delegated_actions": [],
  "unassigned_actions": []
}"""

    def __init__(self, client: DeepSeekClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> ActionItems:
        return await self.client.structured(
            self.SYSTEM_PROMPT,
            shared_context,
            ActionItems,
            self.OUTPUT_CONTRACT,
        )
