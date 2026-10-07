from __future__ import annotations

import re

from infra.llm import LLMClient

from ....models import MultiStyles
from ..contracts import MULTI_STYLES_GENERATION_OUTPUT_CONTRACT
from ..prompts import (
    MULTI_STYLES_GENERATION_SYSTEM_PROMPT,
    MODE_ALIGNMENT_RULES,
    MODE_BRIEF_RULES,
    MODE_RETRO_RULES,
    MODE_REVIEW_RULES,
    MODE_TOPIC_RULES,
)

# 组织模式 → 对应规则块（运行时按模式选择，LLM 只执行当前模式规则）
_MODE_RULES = {
    "brief": MODE_BRIEF_RULES,
    "topic": MODE_TOPIC_RULES,
    "review": MODE_REVIEW_RULES,
    "retro": MODE_RETRO_RULES,
    "alignment": MODE_ALIGNMENT_RULES,
}


def _extract_mode(shared_context: str) -> str:
    """从上下文读取「组织模式」行（brief / topic / review / retro / alignment）。"""
    m = re.search(r"组织模式[:：]\s*([a-zA-Z]+)", shared_context or "")
    mode = m.group(1).lower() if m else ""
    return mode if mode in _MODE_RULES else "topic"


class MultiStylesAgent:
    """按所选组织模式生成多样式纪要草稿。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> MultiStyles:
        mode = _extract_mode(shared_context)
        rules = _MODE_RULES.get(mode, MODE_TOPIC_RULES)  # 缺省业务归类
        system = MULTI_STYLES_GENERATION_SYSTEM_PROMPT + "\n" + rules
        return await self.client.structured(
            system,
            shared_context,
            MultiStyles,
            MULTI_STYLES_GENERATION_OUTPUT_CONTRACT,
            label="minutes_styles/agent",
        )
