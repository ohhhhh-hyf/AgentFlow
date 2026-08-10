"""NotesAgentFactory —— 组装 notes 域全部 Agent 依赖。"""
from __future__ import annotations

from typing import Any

from llm_client import LLMClient
from perspective import PerspectiveModelingAgent
from .notes_core import NotesUnderstandingAgent
# 领域核心 Agent（如"笔记理解"）在此 import：
# from .notes_core import XxxAgent

# ── 任务线 import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .tasks.points import (
    PointsAgent,
    PointsRender,
    PointsSupervisor,
)

# ── 任务线 import 生成区结束 ──

class NotesAgentFactory:
    """组装 Agent 依赖的工厂（键名 = orchestrator 挂载的属性名）。"""

    @staticmethod
    def create(client: LLMClient) -> dict[str, Any]:
        """创建全部 Agent，返回按角色命名的字典。"""
        return {
            # 核心层（perspective 公共组件；领域核心 Agent 在此追加）
            "perspective_modeling_agent": PerspectiveModelingAgent(client),
            "notes_understanding_agent": NotesUnderstandingAgent(client),
            # ── 任务线装配生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

            "points_agent": PointsAgent(client),
            "points_supervisor": PointsSupervisor(client),
            "points_render": PointsRender(client),

            # ── 任务线装配生成区结束 ──
        }

__all__ = ["NotesAgentFactory"]
