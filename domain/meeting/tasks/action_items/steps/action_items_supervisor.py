from __future__ import annotations

from supervisor import GlobalSupervisor

from llm_client import LLMClient
from ....models import ActionItemsSupervisorReview
from ..prompts import (
    ACTION_ITEMS_SUPERVISOR_DOMAIN_PROMPT,
)
from ..contracts import ACTION_ITEMS_SUPERVISOR_OUTPUT_CONTRACT


class ActionItemsSupervisor:
    """待办提取任务的领域监督者。

    prompt = 全局整体标准（注入） + 待办领域审核规则，
    一次 LLM 调用完成双重评判，决定 approve / revise / reject。
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            ACTION_ITEMS_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> ActionItemsSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            ActionItemsSupervisorReview,
            ACTION_ITEMS_SUPERVISOR_OUTPUT_CONTRACT,
            label="action_items/supervisor",
        )
