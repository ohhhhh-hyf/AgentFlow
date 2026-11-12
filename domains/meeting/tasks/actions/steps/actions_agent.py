from __future__ import annotations

from typing import Any

from domains.shared.supervisor import StructuredGenerationAgent

from ....models import ActionItems
from ..contracts import ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT
from ..prompts import ACTION_ITEMS_GENERATION_SYSTEM_PROMPT, build_actions_system_prompt

_INVALID_OWNERS = {
    "null",
    "none",
    "待定",
    "未分配",
    "待认领",
    "待确认",
    "无",
    "-",
    "未提及",
    "未明确",
    "大家",
    "全员",
    "所有人",
    "团队",
    "待落实",
    "待排期",
}


def is_valid_action(action: Any) -> bool:
    """判定单条待办是否为三要素（title、item、owner）齐全且有效的待办。"""
    if not isinstance(action, dict):
        return False
    title = str(action.get("title") or "").strip()
    item = str(action.get("item") or "").strip()
    owner = str(action.get("owner") or "").strip()

    # 1. 只要 owner、title、item 任何一个字段为空字符串或 null，直接剔除
    if not title or title.lower() in {"null", "none"}:
        return False
    if not item or item.lower() in {"null", "none"}:
        return False
    if not owner or owner.lower() in {"null", "none"}:
        return False

    # 2. owner 命中无效占位符，直接剔除
    if owner.lower() in _INVALID_OWNERS:
        return False

    return True


def filter_valid_actions(actions: list[Any]) -> list[dict]:
    """过滤待办列表，剔除 owner/title/item 为空或 owner 属于占位符的脏条目。"""
    if not isinstance(actions, list):
        return []
    return [dict(a) for a in actions if is_valid_action(a)]


class ActionItemsAgent(StructuredGenerationAgent):
    """提取客观待办：输出单一扁平 actions 数组。"""

    system_prompt = ACTION_ITEMS_GENERATION_SYSTEM_PROMPT
    output_model = ActionItems
    output_contract = ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT
    label = "actions/agent"

    async def run(self, shared_context: str) -> ActionItems:
        kwargs = dict(self.extra_kwargs)
        if "timeout" not in kwargs:
            kwargs["timeout"] = 60.0  # 防挂死硬超时防御
        result = await self.client.structured(
            build_actions_system_prompt(shared_context),
            shared_context,
            self.output_model,
            self.output_contract,
            label="actions/agent",
            **kwargs,
        )
        if hasattr(result, "actions") and isinstance(result.actions, list):
            result.actions = filter_valid_actions(result.actions)
        elif isinstance(result, dict) and isinstance(result.get("actions"), list):
            result["actions"] = filter_valid_actions(result["actions"])
        return result
