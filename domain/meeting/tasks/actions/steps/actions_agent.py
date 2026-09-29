from __future__ import annotations

from domain._shared import StructuredGenerationAgent

from ....models import ActionItems
from ..contracts import ACTION_ITEMS_GENERATION_OUTPUT_CONTRACT
from ..prompts import ACTION_ITEMS_GENERATION_SYSTEM_PROMPT


class ActionItemsAgent(StructuredGenerationAgent):
    """提取待办：个人模式筛本人待办；客观模式覆盖各方待办。"""

    system_prompt = ACTION_ITEMS_GENERATION_SYSTEM_PROMPT
    output_model = ActionItems
    output_contract = ACTION_ITEMS_GENERATION_OUTPUT_CONTRACT
    label = "actions/agent"
