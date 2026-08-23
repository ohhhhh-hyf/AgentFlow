"""NotesAgentFactory —— 组装 notes 域全部 Agent 依赖。"""
from __future__ import annotations

from typing import Any

from client import LLMClient
from perspective import PerspectiveModelingAgent
from .notes_core import NotesUnderstandingAgent
# 领域核心 Agent（如"笔记理解"）在此 import：
# from .notes_core import XxxAgent

# ── 任务线 import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .tasks.catalog import (
    CatalogAgent,
    CatalogRender,
    CatalogSupervisor,
)

from .tasks.checklist import (
    ChecklistAgent,
    ChecklistRender,
    ChecklistSupervisor,
)

from .tasks.knowledge_graph import (
    KnowledgeGraphAgent,
    KnowledgeGraphRender,
    KnowledgeGraphSupervisor,
)

from .tasks.library import (
    LibraryAgent,
    LibraryRender,
    LibrarySupervisor,
)

from .tasks.quiz import (
    QuizAgent,
    QuizRender,
    QuizSupervisor,
)

from .tasks.review import (
    ReviewAgent,
    ReviewRender,
    ReviewSupervisor,
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

            "catalog_agent": CatalogAgent(client),
            "catalog_supervisor": CatalogSupervisor(client),
            "catalog_render": CatalogRender(client),
            "checklist_agent": ChecklistAgent(client),
            "checklist_supervisor": ChecklistSupervisor(client),
            "checklist_render": ChecklistRender(client),
            "knowledge_graph_agent": KnowledgeGraphAgent(client),
            "knowledge_graph_supervisor": KnowledgeGraphSupervisor(client),
            "knowledge_graph_render": KnowledgeGraphRender(client),
            "library_agent": LibraryAgent(client),
            "library_supervisor": LibrarySupervisor(client),
            "library_render": LibraryRender(client),
            "quiz_agent": QuizAgent(client),
            "quiz_supervisor": QuizSupervisor(client),
            "quiz_render": QuizRender(client),
            "review_agent": ReviewAgent(client),
            "review_supervisor": ReviewSupervisor(client),
            "review_render": ReviewRender(client),

            # ── 任务线装配生成区结束 ──
        }

__all__ = ["NotesAgentFactory"]

