"""Agent 工厂 —— 组装全部 Agent 依赖。

统一创建核心 Agent（meeting_core）与两条任务线（tasks）的全部组件，
供 MeetingAgentSystem（orchestrator.py）注入使用。
"""
from __future__ import annotations

from typing import Any

from client import LLMClient
from perspective import PerspectiveModelingAgent
from .meeting_core import MeetingUnderstandingAgent

# ── 任务线 import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .tasks.actions import (
    ActionItemsAgent,
    ActionItemsRender,
    ActionItemsSupervisor,
)

from .tasks.mindmap import (
    MindmapAgent,
    MindmapRender,
    MindmapSupervisor,
)

from .tasks.minutes import (
    MinutesGenerationAgent,
    MinutesGenerationRender,
    MinutesGenerationSupervisor,
)

from .tasks.minutes_trace import (
    MinutesTraceAgent,
    MinutesTraceRender,
    MinutesTraceSupervisor,
)

from .tasks.minutes_styles import (
    MultiStylesAgent,
    MultiStylesRender,
    MultiStylesSupervisor,
)

from .tasks.risks import (
    RiskAgent,
    RiskRender,
    RiskSupervisor,
)

# ── 任务线 import 生成区结束 ──

class MeetingAgentFactory:
    """组装 Agent 依赖的工厂。"""

    @staticmethod
    def create(client: LLMClient) -> dict[str, Any]:
        """创建全部 Agent，返回按角色命名的字典。

        Keys:
            meeting_understanding / perspective_modeling —— 核心层
            minutes / minutes_supervisor / minutes_render —— 纪要线
            actions / actions_supervisor / actions_render —— 待办线
        """
        return {
            # 核心层（键 = 属性名，与任务线统一：{角色}_agent）
            "meeting_understanding_agent": MeetingUnderstandingAgent(client),
            "perspective_modeling_agent": PerspectiveModelingAgent(client),
            # ── 任务线装配生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

            "actions_agent": ActionItemsAgent(client),
            "actions_supervisor": ActionItemsSupervisor(client),
            "actions_render": ActionItemsRender(client),
            "mindmap_agent": MindmapAgent(client),
            "mindmap_supervisor": MindmapSupervisor(client),
            "mindmap_render": MindmapRender(client),
            "minutes_agent": MinutesGenerationAgent(client),
            "minutes_supervisor": MinutesGenerationSupervisor(client),
            "minutes_render": MinutesGenerationRender(client),
            "minutes_trace_agent": MinutesTraceAgent(client),
            "minutes_trace_supervisor": MinutesTraceSupervisor(client),
            "minutes_trace_render": MinutesTraceRender(client),
            "minutes_styles_agent": MultiStylesAgent(client),
            "minutes_styles_supervisor": MultiStylesSupervisor(client),
            "minutes_styles_render": MultiStylesRender(client),
            "risk_agent": RiskAgent(client),
            "risk_supervisor": RiskSupervisor(client),
            "risk_render": RiskRender(client),

            # ── 任务线装配生成区结束 ──
        }

__all__ = ["MeetingAgentFactory"]

