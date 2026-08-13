from __future__ import annotations

from llm_client import LLMClient
from tools.hard_execution import (
    enforce_minutes_draft,
    extract_labeled_json,
)
from tools.memory.meeting import apply_memory_display
from ....models import Minutes
from ..prompts import (
    MINUTES_GENERATION_SYSTEM_PROMPT,
)
from ..contracts import MINUTES_GENERATION_OUTPUT_CONTRACT


class MinutesGenerationAgent:
    """基于会议理解和视角模型生成纪要草稿（个人视角或客观全员视角）。

    强执行：模型只负责提炼字段；key_decisions / risks_and_blockers /
    unresolved_questions 在返回前由程序从会议理解硬拷贝，杜绝模型改写。
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Minutes:
        raw = await self.client.structured(
            MINUTES_GENERATION_SYSTEM_PROMPT,
            shared_context,
            Minutes,
            MINUTES_GENERATION_OUTPUT_CONTRACT,
        )
        understanding = extract_labeled_json(shared_context, "会议理解")
        enforced = enforce_minutes_draft(raw, understanding)
        enforced = apply_memory_display(enforced, shared_context, understanding)
        return Minutes.validate(enforced)
