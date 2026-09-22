"""Agent 工厂 —— 组装全部 Agent 依赖。

统一创建核心 Agent（meeting_core）与全部任务线（tasks，当前 7 条）的组件，
供 MeetingAgentSystem（orchestrator.py）注入使用。
"""
from __future__ import annotations

from typing import Any

from tools.llm import LLMClient
from perspective import PerspectiveModelingAgent
from .meeting_core import MeetingUnderstandingAgent

# ── 任务线 import 生成区：由 tools/codegen/sync_domain.py 生成，勿手改 ──

from .tasks.actions import (
    ActionItemsAgent,
    ActionItemsRender,
    ActionItemsSupervisor,
)

from .tasks.consensus_decision import (
    ConsensusDecisionAgent,
    ConsensusDecisionRender,
    ConsensusDecisionSupervisor,
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

from .tasks.minutes_styles import (
    MultiStylesAgent,
    MultiStylesRender,
    MultiStylesSupervisor,
)

from .tasks.minutes_trace import (
    MinutesTraceAgent,
    MinutesTraceRender,
    MinutesTraceSupervisor,
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
            meeting_understanding_agent / perspective_modeling_agent —— 核心层
            其余按 ``{线名}_{角色}`` 命名（角色 ∈ agent / supervisor / render），
            线名见下方"任务线装配生成区"（由 sync_domain 生成，勿手改）。
        """
        return {
            # 核心层（键 = 属性名，与任务线统一：{角色}_agent）
            "meeting_understanding_agent": MeetingUnderstandingAgent(client),
            "perspective_modeling_agent": PerspectiveModelingAgent(client),
            # ── 任务线装配生成区：由 tools/codegen/sync_domain.py 生成，勿手改 ──

            "actions_agent": ActionItemsAgent(client),
            "actions_supervisor": ActionItemsSupervisor(client),
            "actions_render": ActionItemsRender(client),
            "consensus_decision_agent": ConsensusDecisionAgent(client),
            "consensus_decision_supervisor": ConsensusDecisionSupervisor(client),
            "consensus_decision_render": ConsensusDecisionRender(client),
            "mindmap_agent": MindmapAgent(client),
            "mindmap_supervisor": MindmapSupervisor(client),
            "mindmap_render": MindmapRender(client),
            "minutes_agent": MinutesGenerationAgent(client),
            "minutes_supervisor": MinutesGenerationSupervisor(client),
            "minutes_render": MinutesGenerationRender(client),
            "minutes_styles_agent": MultiStylesAgent(client),
            "minutes_styles_supervisor": MultiStylesSupervisor(client),
            "minutes_styles_render": MultiStylesRender(client),
            "minutes_trace_agent": MinutesTraceAgent(client),
            "minutes_trace_supervisor": MinutesTraceSupervisor(client),
            "minutes_trace_render": MinutesTraceRender(client),
            "risks_agent": RiskAgent(client),
            "risks_supervisor": RiskSupervisor(client),
            "risks_render": RiskRender(client),

            # ── 任务线装配生成区结束 ──
        }

__all__ = ["MeetingAgentFactory"]

