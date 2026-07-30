from __future__ import annotations

from ..client import DeepSeekClient
from ..models import FinalReport


class FinalIntegrationAgent:
    """校准中间结果，只输出用户视角纪要和该用户待办。"""

    SYSTEM_PROMPT = """你是会议成果整合 Agent。最终只生成两个业务结果：
1. personalized_minutes：从该用户的角色、职责和关注点出发整理的一段完整会议纪要；
2. action_items：只包含该用户本人负责、共同负责或需要主动跟进的待办事项。

规则：
- personalized_minutes 必须是一个连贯的字符串段落，不得返回数组、分点或编号；
- 该段落应包含与用户相关的关键讨论、正式决策、风险和未决事项，但不要写无关细节；
- action_items 只能保留 owner 与用户姓名完全一致，且 evidence 明确证明该用户负责或本人承诺的任务；
- owner 为 null、属于他人或仅根据角色推断的事项不得进入最终 action_items；
- 会议决策、风险和条件触发可以写入 personalized_minutes，但不能因此自动转化为用户待办；
- 不得把不同动作或不同截止时间的待办合并成一条；
- 每个待办使用 task、owner、deadline、priority、status、evidence、confidence 字段；
- 负责人或截止时间没有明确证据时使用 null；
- 冲突时以会议理解和会议原文证据为准；
- 保留不确定性，不得新增事实；
- 除 title、personalized_minutes、action_items 外不要输出其他顶层字段。"""

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

    def __init__(self, client: DeepSeekClient) -> None:
        self.client = client

    async def run(self, integration_context: str) -> FinalReport:
        return await self.client.structured(
            self.SYSTEM_PROMPT,
            integration_context,
            FinalReport,
            self.OUTPUT_CONTRACT,
        )
