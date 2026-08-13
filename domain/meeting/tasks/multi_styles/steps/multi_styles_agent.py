from __future__ import annotations

import re

from llm_client import LLMClient

from ....models import MultiStyles
from ..contracts import MULTI_STYLES_GENERATION_OUTPUT_CONTRACT
from ..prompts import (
    MULTI_STYLES_GENERATION_SYSTEM_PROMPT,
    MODE_CAUSAL_RULES,
    MODE_LOGIC_RULES,
    MODE_PARTY_RULES,
    MODE_TIME_RULES,
    MODE_URGENCY_RULES,
)

# 组织模式 → 对应规则块（运行时按模式选择，LLM 只执行当前模式规则）
_MODE_RULES = {
    "time": MODE_TIME_RULES,
    "logic": MODE_LOGIC_RULES,
    "causal": MODE_CAUSAL_RULES,
    "party": MODE_PARTY_RULES,
    "urgency": MODE_URGENCY_RULES,
}


def _extract_mode(shared_context: str) -> str:
    """从上下文读取「组织模式」行（time / logic / causal / party / urgency）。"""
    m = re.search(r"组织模式[:：]\s*([a-zA-Z]+)", shared_context or "")
    return m.group(1).lower() if m else ""


class MultiStylesAgent:
    """按所选组织模式生成多样式纪要草稿。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> MultiStyles:
        mode = _extract_mode(shared_context)
        rules = _MODE_RULES.get(mode, MODE_LOGIC_RULES)  # 缺省逻辑顺序
        system = MULTI_STYLES_GENERATION_SYSTEM_PROMPT + "\n" + rules
        return await self.client.structured(
            system,
            shared_context,
            MultiStyles,
            MULTI_STYLES_GENERATION_OUTPUT_CONTRACT,
        )
