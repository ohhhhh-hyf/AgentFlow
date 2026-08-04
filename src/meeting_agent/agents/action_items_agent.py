from __future__ import annotations

from ..client import LLMClient
from ..models import ActionItems


class ActionItemsAgent:
    """提取待办：个人模式筛本人待办；客观模式覆盖各方待办。"""

    SYSTEM_PROMPT = """你是待办事项 Agent。请根据视角模式提取可执行行动。

先读取上下文中的「视角模式」以及用户画像的 perspective 字段：

【视角模式 = objective，或 perspective = "objective"】客观全员视角
- 目标是输出“会议全量待办视图”，供客观纪要与全员协同使用；
- my_actions：在此模式下表示「已明确负责人的待办全集」
  （字段名沿用契约；逐条填写真实 owner，不要用画像角色顶替，不要只保留某一人）；
- delegated_actions：固定输出 []（避免与 my_actions 重复分类）；
- unassigned_actions：任务明确但原文未指明负责人的事项，owner 必须为 null；
- 覆盖全体参会人与相关方，不要只提取某一个角色；
- 不得根据职位、部门或惯例推断负责人。

【视角模式 = personal，或 perspective 缺省】个人用户视角（默认）
- my_actions 只能包含原文明示当前用户负责，或当前用户本人明确承诺完成的事项；
- 不得仅凭用户角色、职责、关注点或会议上下文推断当前用户是负责人；
- 他人明确负责的事项放入 delegated_actions；
- 原文没有明确负责人的事项放入 unassigned_actions，owner 必须为 null；
- 会议决策、风险关注和条件触发本身不等于个人待办。

通用规则：
- 一个待办只描述一个可独立完成的动作；
- 同一句发言中包含多个动作，或动作具有不同截止时间时，必须拆成多条待办；
- 截止时间无明确证据时使用 null；
- 每项必须提供能证明任务内容（及负责人，若有）的简短原文依据 evidence；
- status 使用 explicit（原文明示）或 inferred（仅允许对优先级等软属性谨慎标注，不得推断负责人）；
- 避免把一般讨论、建议、已完成事实误判为任务；
- 条件性任务（如“如果下雨则通知”）在原文已明确责任人与触发条件时可保留，并在 task 中写清条件。"""

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

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> ActionItems:
        return await self.client.structured(
            self.SYSTEM_PROMPT,
            shared_context,
            ActionItems,
            self.OUTPUT_CONTRACT,
        )
