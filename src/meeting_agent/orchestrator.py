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
from .nodes import QUALITY_WARNING, _Nodes
from .state import MeetingState
from .validation import validate_payload

ProgressHandler = Callable[[str, str], None]


def _normalize_transcript(text: str) -> str:
    """规范化会议文本：合并段落内硬换行，保留段落间空行。

    处理 PDF 复制、OCR 等场景产生的段内换行问题：
    - 连续两个以上换行 → 段落分隔（保留为空行）
    - 单个换行且在中文/日文/英文小写上下文中 → 合并为同一段落
    """
    import re

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 保护段落间空行：\n\n+ → 占位符
    text = re.sub(r"\n{2,}", "\x00", text)
    # 合并段落内换行
    text = text.replace("\n", "")
    # 恢复段落分隔
    text = text.replace("\x00", "\n\n")
    return text.strip()


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

        # Fork 节点（条件路由只能去一个目标，由 fork 再分叉到并行节点）
        builder.add_node("final_render", self._final_render_fork)
        builder.add_node("fallback_render", self._fallback_render_fork)

        # 最终输出：纪要 + 待办 并行
        builder.add_node("render_minutes", self._render_minutes_node)
        builder.add_node("format_actions", self._format_actions_node)
        builder.add_node("fallback_minutes", self._fallback_minutes_node)
        builder.add_node("fallback_actions", self._fallback_actions_node)

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

        # 审核后条件路由 → fork 节点
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

        # Fork → 并行渲染（纪要 + 待办同时跑）
        builder.add_edge("final_render", "render_minutes")
        builder.add_edge("final_render", "format_actions")
        builder.add_edge("render_minutes", END)
        builder.add_edge("format_actions", END)

        # Fork → 并行降级（纪要 + 待办同时跑）
        builder.add_edge("fallback_render", "fallback_minutes")
        builder.add_edge("fallback_render", "fallback_actions")
        builder.add_edge("fallback_minutes", END)
        builder.add_edge("fallback_actions", END)

        return builder.compile()

    # ── Fork 节点（空操作，仅用于分叉到并行子节点）───────────

    async def _final_render_fork(self, state: MeetingState) -> dict:
        return {}

    async def _fallback_render_fork(self, state: MeetingState) -> dict:
        return {}

    # ── 启动入口 ──────────────────────────────────────────────

    async def run(
        self,
        transcript: str,
        user: UserIdentity | None = None,
        template: str = "",
    ) -> FinalReport:
        if not transcript.strip():
            raise ValueError("会议文字不能为空")

        # 规范化文本：合并段落内的硬换行（PDF/OCR 常见问题），保留段落间空行
        transcript = _normalize_transcript(transcript)

        template = template or ""
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

        # 从并行渲染结果组装 FinalReport
        minutes = state.get("rendered_minutes") or ""
        actions = state.get("formatted_actions") or []
        quality_degraded = bool(state.get("quality_degraded"))

        if objective_mode:
            title = "客观会议纪要"
        else:
            title = f"{user_data.get('name', '用户')}视角会议纪要"

        report = FinalReport(
            title=title,
            personalized_minutes=minutes,
            action_items=actions,
            quality_warning=QUALITY_WARNING if quality_degraded else None,
        )
        try:
            return validate_payload(FinalReport, report.model_dump())
        except Exception:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning("FinalReport 校验失败，退回确定性兜底")
            fallback = self._assemble_report_from_drafts(state)
            fallback.quality_warning = QUALITY_WARNING
            return fallback
