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

# ── 任务线 import 生成区：由 tools/scripts/codegen.py 生成，勿手改 ──

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

# ── 任务线 import 生成区结束 ──

class MeetingAgentFactory:
    """组装 Agent 依赖的工厂。"""

    @staticmethod
    def create(client: LLMClient) -> dict[str, Any]:
        """创建全部 Agent，返回按角色命名的字典。

        Keys:
            meeting_understanding / perspective_modeling —— 核心层
            minutes_generation / minutes_generation_supervisor / minutes_generation_render —— 纪要线
            action_items / action_items_supervisor / action_items_render —— 待办线
        """
        return {
            # 核心层（键 = 属性名，与任务线统一：{角色}_agent）
            "meeting_understanding_agent": MeetingUnderstandingAgent(client),
            "perspective_modeling_agent": PerspectiveModelingAgent(client),
            # ── 任务线装配生成区：由 tools/scripts/codegen.py 生成，勿手改 ──

            "action_items_agent": ActionItemsAgent(client),
            "action_items_supervisor": ActionItemsSupervisor(client),
            "action_items_render": ActionItemsRender(client),
            "minutes_generation_agent": MinutesGenerationAgent(client),
            "minutes_generation_supervisor": MinutesGenerationSupervisor(client),
            "minutes_generation_render": MinutesGenerationRender(client),

            # ── 任务线装配生成区结束 ──
        }


__all__ = ["MeetingAgentFactory"]
