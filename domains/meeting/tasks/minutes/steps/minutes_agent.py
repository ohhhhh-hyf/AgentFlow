from __future__ import annotations

from infra.llm import LLMClient
from core.execution.hard_execution import (
    enforce_minutes_draft,
    extract_labeled_json,
    parse_perspective_mode,
)
from ....models import Minutes
from ..prompts import (
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    MINUTES_PERSONAL_GENERATION_PROMPT,
)
from ..contracts import MINUTES_GENERATION_OUTPUT_CONTRACT


class MinutesGenerationAgent:
    """基于会议理解和视角模型生成纪要草稿（个人视角或客观全员视角）。

    双轨分流架构：
    - 客观模式：挂载 MINUTES_OBJECTIVE_GENERATION_PROMPT，纯粹第三人称公文体；
    - 个人模式：挂载 MINUTES_PERSONAL_GENERATION_PROMPT，作战秘书看板体。
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Minutes:
        mode = parse_perspective_mode(shared_context)
        system_prompt = (
            MINUTES_PERSONAL_GENERATION_PROMPT
            if mode == "personal"
            else MINUTES_OBJECTIVE_GENERATION_PROMPT
        )
        raw = await self.client.structured(
            system_prompt,
            shared_context,
            Minutes,
            MINUTES_GENERATION_OUTPUT_CONTRACT,
            label=f"minutes/agent/{mode}",
        )
        understanding = extract_labeled_json(shared_context, "会议理解")
        perspective = extract_labeled_json(shared_context, "用户视角模型")
        enforced = enforce_minutes_draft(raw, understanding, mode=mode, perspective=perspective)
        return Minutes.validate(enforced)
