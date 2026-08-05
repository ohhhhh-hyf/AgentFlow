"""LangGraph 工作流编排。

MeetingAgentSystem 负责：构建 DAG 图、注册节点、条件路由、启动运行。
具体的图节点实现位于 nodes.py（_Nodes mixin）。
"""
from __future__ import annotations

from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from .agents import (
    ActionItemsAgent,
    FinalRenderer,
    MeetingUnderstandingAgent,
    MinutesGenerationAgent,
    PerspectiveModelingAgent,
    SupervisorAgent,
)
from .client import LLMClient
from .models import FinalReport, UserIdentity, is_objective_perspective
from .nodes import _Nodes
from .state import MeetingState
from .validation import validate_payload

ProgressHandler = Callable[[str, str], None]


class MeetingAgentSystem(_Nodes):
    """使用 LangGraph 编排会议分析、审核、返工和最终渲染。"""

    MAX_REVISIONS = 1

    def __init__(
        self,
        client: LLMClient | None = None,
        progress_handler: ProgressHandler | None = None,
    ) -> None:
        self.client = client or LLMClient()
        self.progress_handler = progress_handler

        self.meeting_understanding_agent = MeetingUnderstandingAgent(self.client)
        self.perspective_modeling_agent = PerspectiveModelingAgent(self.client)
        self.minutes_generation_agent = MinutesGenerationAgent(self.client)
        self.action_items_agent = ActionItemsAgent(self.client)
        self.supervisor_agent = SupervisorAgent(self.client)
        self.final_renderer = FinalRenderer(self.client)
        self.graph = self._build_graph()

    # ── 进度回调 ──────────────────────────────────────────────

    def _progress(self, event: str, label: str) -> None:
        if self.progress_handler:
            self.progress_handler(event, label)

    # ── 图构建 ────────────────────────────────────────────────

    def _build_graph(self) -> object:
        builder = StateGraph(MeetingState)

        builder.add_node(
            "meeting_understanding",
            self._meeting_understanding_node,
        )
        builder.add_node(
            "perspective_modeling",
            self._perspective_modeling_node,
        )
        builder.add_node(
            "minutes_generation",
            self._minutes_generation_node,
        )
        builder.add_node(
            "action_items",
            self._action_items_node,
        )
        builder.add_node("supervisor_review", self._supervisor_review_node)
        builder.add_node("revision", self._revision_node)
        builder.add_node("fallback_render", self._fallback_render_node)
        builder.add_node("final_render", self._final_render_node)

        # 第一层并行：会议理解 + 视角建模
        builder.add_edge(START, "meeting_understanding")
        builder.add_edge(START, "perspective_modeling")

        # 第一层汇合 → 第二层并行：纪要生成 + 待办提取
        first_layer = ["meeting_understanding", "perspective_modeling"]
        builder.add_edge(first_layer, "minutes_generation")
        builder.add_edge(first_layer, "action_items")

        # 第二层汇合 → 审核
        builder.add_edge(
            ["minutes_generation", "action_items"],
            "supervisor_review",
        )

        # 审核后条件路由
        builder.add_conditional_edges(
            "supervisor_review",
            self._route_after_supervision,
            {
                "final_render": "final_render",
                "revision": "revision",
                "fallback_render": "fallback_render",
            },
        )

        # 返工后重新审核
        builder.add_edge("revision", "supervisor_review")

        # 终点
        builder.add_edge("fallback_render", END)
        builder.add_edge("final_render", END)

        return builder.compile()

    # ── 启动入口 ──────────────────────────────────────────────

    async def run(
        self,
        transcript: str,
        user: UserIdentity | None = None,
        template: str = "",
    ) -> FinalReport:
        if not transcript.strip():
            raise ValueError("会议文字不能为空")

        user = user or UserIdentity()
        objective_mode = is_objective_perspective(user)
        user_data = user.model_dump()
        if objective_mode and not user_data.get("perspective"):
            user_data["perspective"] = "objective"

        initial_state: MeetingState = {
            "transcript": transcript,
            "user": user_data,
            "objective_perspective": objective_mode,
            "revision_count": 0,
            "template": template,
        }
        state = await self.graph.ainvoke(initial_state)

        return validate_payload(
            FinalReport,
            state["final_report"],
        )
