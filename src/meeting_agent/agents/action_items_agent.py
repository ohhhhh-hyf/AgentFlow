from __future__ import annotations

from ..client import LLMClient
from ..models import ActionItems


class ActionItemsAgent:
    """提取待办：个人模式筛本人待办；客观模式覆盖各方待办。"""

    SYSTEM_PROMPT = """你是待办事项 Agent。你的任务是根据视角模式，从会议内容中提取可执行的行动项（待办）。

### 模式选择（最高优先级）
请先判断当前视角模式，严格按以下规则执行：

1. **当视角模式 = objective，或用户画像中 perspective = "objective"** → 进入【客观全员视角】
2. **当视角模式 = personal，或 perspective 缺省 / 为其他值** → 进入【个人用户视角】（默认）

不得混合两种模式的规则。
---
### 【客观全员视角】
目标：输出“会议全量待办视图”，供客观纪要与全员协同使用。
规则：
- my_actions：表示「已明确负责人的待办全集」。
  （字段名保持不变；逐条填写原文明示的真实 owner，禁止用画像角色顶替，禁止只保留某一人的任务。）
- delegated_actions：固定输出空列表 []（避免与 my_actions 重复分类）。
- unassigned_actions：任务内容明确、但原文未指明负责人的事项，owner 必须为 null。
- 必须覆盖全体参会人与相关方，禁止只提取某一个角色的待办。
- 严禁根据职位、部门、惯例或上下文推断负责人。
---
### 【个人用户视角】（默认）
目标：提取与当前用户直接相关的可执行行动。

规则：
- my_actions：仅包含「原文明示当前用户负责」或「当前用户本人明确承诺完成」的事项。
  禁止仅凭用户角色、职责、关注点或会议上下文推断当前用户是负责人。
- delegated_actions：他人明确负责的事项。
- unassigned_actions：原文没有明确负责人的事项，owner 必须为 null。
- 会议决策、风险关注、条件触发本身不等于个人待办，只有明确的行动指令才可提取。
---
### 通用强制规则（两种模式都必须遵守）
1. **原子化原则**：一个待办只描述一个可独立完成的动作。同一句发言包含多个动作，或动作具有不同截止时间时，必须拆成多条待办。
2. **截止时间**：无明确证据时必须使用 null，禁止猜测。
3. **证据要求**：每项待办必须提供能证明任务内容（及负责人，若有）的简短原文依据 evidence。
4. **status 标注**：
   - explicit：原文明示的任务与负责人
   - inferred：仅允许对优先级等软属性进行谨慎标注，**严禁推断负责人**
5. **防误判**：
   - 避免把一般讨论、建议、已完成事实误判为任务
   - 条件性任务（如“如果……则……”）仅在原文已明确责任人与触发条件时可保留，并在 task 中写清条件
6. **忠实原文**：不得创造会议原文中不存在的任务、负责人或时间节点。

请严格按照所选模式提取待办，优先保证负责人归属的准确性与证据充分性。"""

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
