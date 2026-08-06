from __future__ import annotations

from supervisor import GlobalSupervisor

from llm_client import LLMClient
from ...models import MinutesSupervisorReview
from .prompts import (
    MINUTES_SUPERVISOR_DOMAIN_PROMPT,
    MINUTES_SUPERVISOR_OUTPUT_CONTRACT,
)


class MinutesGenerationSupervisor:
    """纪要生成任务的领域监督者。

    prompt = 全局整体标准（注入） + 纪要领域审核规则，
    一次 LLM 调用完成双重评判，决定 approve / revise / reject。
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            MINUTES_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> MinutesSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            MinutesSupervisorReview,
            MINUTES_SUPERVISOR_OUTPUT_CONTRACT,
        )
