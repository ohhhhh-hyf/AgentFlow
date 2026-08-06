"""Agent 工厂 —— 组装全部 Agent 依赖。

统一创建核心 Agent（meeting_core）与两条任务线（tasks）的全部组件，
供 MeetingAgentSystem（orchestrator.py）注入使用。
"""
from __future__ import annotations

from typing import Any

from llm_client import LLMClient
from .meeting_core import (
    MeetingUnderstandingAgent,
    PerspectiveModelingAgent,
)
from .tasks.action_items import (
    ActionItemsAgent,
    ActionItemsRender,
    ActionItemsSupervisor,
)
from .tasks.minutes_generation import (
    MinutesGenerationAgent,
    MinutesGenerationRender,
    MinutesGenerationSupervisor,
)


class MeetingAgentFactory:
    """组装 Agent 依赖的工厂。"""

    @staticmethod
    def create(client: LLMClient) -> dict[str, Any]:
        """创建全部 Agent，返回按角色命名的字典。

        Keys:
            meeting_understanding / perspective_modeling —— 核心层
            minutes_generation / minutes_supervisor / minutes_render —— 纪要线
            action_items / actions_supervisor / actions_render —— 待办线
        """
        return {
            # 核心层
            "meeting_understanding": MeetingUnderstandingAgent(client),
            "perspective_modeling": PerspectiveModelingAgent(client),
            # 纪要线
            "minutes_generation": MinutesGenerationAgent(client),
            "minutes_supervisor": MinutesGenerationSupervisor(client),
            "minutes_render": MinutesGenerationRender(client),
            # 待办线
            "action_items": ActionItemsAgent(client),
            "actions_supervisor": ActionItemsSupervisor(client),
            # 待办渲染：无模板时确定性逻辑，有模板时需 LLM
            "actions_render": ActionItemsRender(client),
        }


__all__ = ["MeetingAgentFactory"]
