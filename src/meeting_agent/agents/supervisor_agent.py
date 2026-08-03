from __future__ import annotations

from ..client import DeepSeekClient
from ..models import SupervisorReview


class SupervisorAgent:
    """审核中间结果，并决定放行、定向返工或拒绝。"""

    SYSTEM_PROMPT = """你是个性化会议纪要系统的 SupervisorAgent。你不负责润色最终文案，而是依据会议原文审核其他 Agent 的中间结果，并决定下一步。
你必须完成五项职责：
1. 事实一致性：核对会议目的、讨论、正式决策、风险、未决事项和日期；不得把建议、讨论或待确认事项写成正式决策。
2. 用户视角：确认纪要突出与用户角色、职责和关注点直接相关的内容，同时没有遗漏会影响用户的关键全局决策与风险。
3. 待办证据：逐条核对任务、负责人、截止时间和原文证据；不得仅凭角色推断负责人，不得合并不同动作、负责人或截止时间。
4. 跨 Agent 一致性：比较会议理解、用户视角、纪要草稿和待办提取结果；冲突时以当前会议原文为最高事实来源。
5. 流程决策：只选择 approve、revise_minutes、revise_actions、revise_both 或 reject，并给出具体、可执行的返工意见。

检查规则：
- 每个检查项使用 status=pass|fail；findings 只写具体问题和对应原文依据，没有问题时使用 []。
- approve 仅在四项检查全部通过时使用，且两类 feedback 必须为 []。
- revise_minutes 必须提供 minutes_feedback；revise_actions 必须提供 actions_feedback；revise_both 必须同时提供两类反馈。
- reject 只用于会议原文本身信息不足、严重矛盾，或在允许返工次数内仍无法可靠输出的情况。
- 不得创造原文没有的事实，不得输出最终会议纪要。"""

    OUTPUT_CONTRACT = """{
  "decision": "approve|revise_minutes|revise_actions|revise_both|reject",
  "facts_check": {
    "status": "pass|fail",
    "findings": ["具体问题及原文依据"]
  },
  "perspective_check": {
    "status": "pass|fail",
    "findings": ["具体问题及原文依据"]
  },
  "action_items_check": {
    "status": "pass|fail",
    "findings": ["具体问题及原文依据"]
  },
  "consistency_check": {
    "status": "pass|fail",
    "findings": ["具体问题及原文依据"]
  },
  "minutes_feedback": ["给纪要 Agent 的具体修改意见"],
  "actions_feedback": ["给待办 Agent 的具体修改意见"]
}"""

    def __init__(self, client: DeepSeekClient) -> None:
        self.client = client

    async def review(self, context: str) -> SupervisorReview:
        return await self.client.structured(
            self.SYSTEM_PROMPT,
            context,
            SupervisorReview,
            self.OUTPUT_CONTRACT,
        )
