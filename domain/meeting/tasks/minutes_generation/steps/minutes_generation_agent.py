from __future__ import annotations

from client import LLMClient
from tools.hard_execution import (
    enforce_minutes_draft,
    extract_labeled_json,
    parse_perspective_mode,
)
from tools.memory.meeting import apply_memory_display
from ....models import Minutes
from ..prompts import (
    MINUTES_GENERATION_SYSTEM_PROMPT,
)
from ..contracts import MINUTES_GENERATION_OUTPUT_CONTRACT


class MinutesGenerationAgent:
    """基于会议理解和视角模型生成纪要草稿（个人视角或客观全员视角）。

    强执行：搬运字段措辞对齐会议理解。客观全量拷贝；职业/真人按下采
    （只删不改，对不上则回退全量），杜绝改写与臆造。
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Minutes:
        raw = await self.client.structured(
            MINUTES_GENERATION_SYSTEM_PROMPT,
            shared_context,
            Minutes,
            MINUTES_GENERATION_OUTPUT_CONTRACT,
            label="minutes_generation/agent",
        )
        understanding = extract_labeled_json(shared_context, "会议理解")
        mode = parse_perspective_mode(shared_context)
        enforced = enforce_minutes_draft(raw, understanding, mode=mode)
        enforced = apply_memory_display(enforced, shared_context, understanding)
        return Minutes.validate(enforced)

