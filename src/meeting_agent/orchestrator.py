from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .agents import (
    ActionItemsAgent,
    FinalRenderer,
    MeetingUnderstandingAgent,
    MinutesGenerationAgent,
    PerspectiveModelingAgent,
    SupervisorAgent,
)
from .client import DeepSeekClient
from .models import FinalReport, UserIdentity
from .state import MeetingState
from .validation import validate_payload


ReviewHandler = Callable[[FinalReport], Awaitable[str]]
ProgressHandler = Callable[[str, str], None]


def _json(value) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return json.dumps(value, ensure_ascii=False, indent=2)


class MeetingAgentSystem:
    """使用 LangGraph 编排会议分析、审核、返工和最终渲染。"""

    MAX_REVISIONS = 1

    def __init__(
        self,
        client: DeepSeekClient | None = None,
        progress_handler: ProgressHandler | None = None,
    ) -> None:
        self.client = client or DeepSeekClient()
        self.progress_handler = progress_handler

        self.meeting_understanding_agent = MeetingUnderstandingAgent(self.client)
        self.perspective_modeling_agent = PerspectiveModelingAgent(self.client)
        self.minutes_generation_agent = MinutesGenerationAgent(self.client)
        self.action_items_agent = ActionItemsAgent(self.client)
        self.supervisor_agent = SupervisorAgent(self.client)
        self.final_renderer = FinalRenderer(self.client)
        self.checkpointer = InMemorySaver()
        self.graph = self._build_graph()

    def _progress(self, event: str, label: str) -> None:
        if self.progress_handler:
            self.progress_handler(event, label)

    async def _meeting_understanding_node(
        self,
        state: MeetingState,
    ) -> dict:
        label = "MeetingUnderstandingAgent｜理解会议内容"
        self._progress("start", label)
        result = await self.meeting_understanding_agent.run(state["transcript"])
        self._progress("done", label)
        return {"meeting_understanding": result.model_dump()}

    async def _perspective_modeling_node(
        self,
        state: MeetingState,
    ) -> dict:
        label = "PerspectiveModelingAgent｜建立用户视角"
        self._progress("start", label)
        result = await self.perspective_modeling_agent.run(
            state["transcript"],
            _json(state["user"]),
        )
        self._progress("done", label)
        return {"perspective_profile": result.model_dump()}

    @staticmethod
    def _shared_context(state: MeetingState) -> str:
        return (
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"会议理解：\n{_json(state['meeting_understanding'])}\n\n"
            f"用户视角模型：\n{_json(state['perspective_profile'])}\n\n"
            f"会议原文：\n{state['transcript']}"
        )

    @staticmethod
    def _revision_context(context: str, feedback: list[str], label: str) -> str:
        if not feedback:
            return context
        return f"{context}\n\nSupervisor {label}：\n{_json(feedback)}"

    async def _minutes_generation_node(self, state: MeetingState) -> dict:
        label = "MinutesGenerationAgent｜生成用户视角纪要"
        self._progress("start", label)
        result = await self.minutes_generation_agent.run(
            self._revision_context(
                self._shared_context(state),
                state.get("minutes_revision_feedback", []),
                "纪要返工意见",
            )
        )
        self._progress("done", label)
        return {"minutes_draft": result.model_dump()}

    async def _action_items_node(self, state: MeetingState) -> dict:
        label = "ActionItemsAgent｜提取待办事项"
        self._progress("start", label)
        result = await self.action_items_agent.run(
            self._revision_context(
                self._shared_context(state),
                state.get("actions_revision_feedback", []),
                "待办返工意见",
            )
        )
        self._progress("done", label)
        return {"extracted_action_items": result.model_dump()}

    def _supervisor_context(self, state: MeetingState) -> str:
        revision_count = state.get("revision_count", 0)
        allowed = (
            "本轮可以选择 approve、revise_minutes、revise_actions、"
            "revise_both 或 reject。"
            if revision_count < self.MAX_REVISIONS
            else "返工次数已用完，本轮只能选择 approve 或 reject。"
        )
        return (
            f"返工次数：{revision_count}/{self.MAX_REVISIONS}\n{allowed}\n\n"
            f"会议原文（最高事实来源）：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"会议理解：\n{_json(state['meeting_understanding'])}\n\n"
            f"用户视角模型：\n{_json(state['perspective_profile'])}\n\n"
            f"个性化纪要草稿：\n{_json(state['minutes_draft'])}\n\n"
            f"待办提取结果：\n{_json(state['extracted_action_items'])}"
        )

    async def _supervisor_review_node(self, state: MeetingState) -> dict:
        label = "SupervisorAgent｜审核结果质量"
        self._progress("start", label)
        review = await self.supervisor_agent.review(
            self._supervisor_context(state)
        )
        self._progress("done", label)
        return {
            "supervisor_review": review.model_dump(),
            "minutes_revision_feedback": review.minutes_feedback,
            "actions_revision_feedback": review.actions_feedback,
        }

    def _route_after_supervision(self, state: MeetingState) -> str:
        decision = state["supervisor_review"]["decision"]
        if decision == "approve":
            return "final_render"
        if decision == "reject" or state.get("revision_count", 0) >= self.MAX_REVISIONS:
            return "quality_failure"
        return "revision"

    async def _revision_node(self, state: MeetingState) -> dict:
        decision = state["supervisor_review"]["decision"]
        self._progress("start", "Revision｜根据审核意见返工")
        updates: dict = {
            "revision_count": state.get("revision_count", 0) + 1,
        }

        if decision == "revise_minutes":
            updates.update(await self._minutes_generation_node(state))
        elif decision == "revise_actions":
            updates.update(await self._action_items_node(state))
        elif decision == "revise_both":
            minutes, actions = await asyncio.gather(
                self._minutes_generation_node(state),
                self._action_items_node(state),
            )
            updates.update(minutes)
            updates.update(actions)
        else:
            raise RuntimeError(f"不支持的 Supervisor 返工决定：{decision}")

        self._progress("done", "Revision｜根据审核意见返工")
        return updates

    @staticmethod
    async def _quality_failure_node(state: MeetingState) -> dict:
        review = state["supervisor_review"]
        findings = []
        for key in (
            "facts_check",
            "perspective_check",
            "action_items_check",
            "consistency_check",
        ):
            findings.extend(review[key]["findings"])
        detail = "；".join(findings) or "Supervisor 未批准当前结果"
        raise RuntimeError(
            f"会议结果未通过 Supervisor 审核（最多允许一次返工）：{detail}"
        )

    async def _final_render_node(self, state: MeetingState) -> dict:
        label = "FinalRenderer｜整理最终展示内容"
        self._progress("start", label)
        context = (
            f"会议原文：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"已审核会议理解：\n{_json(state['meeting_understanding'])}\n\n"
            f"已审核用户视角：\n{_json(state['perspective_profile'])}\n\n"
            f"已批准纪要草稿：\n{_json(state['minutes_draft'])}\n\n"
            f"已批准待办结果：\n{_json(state['extracted_action_items'])}\n\n"
            f"Supervisor 审核结论：\n{_json(state['supervisor_review'])}"
        )
        result = await self.final_renderer.run(context)
        self._progress("done", label)
        return {"final_report": result.model_dump()}

    @staticmethod
    def _human_review_node(state: MeetingState) -> dict:
        return {"human_decision": "pass"}

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
        builder.add_node("quality_failure", self._quality_failure_node)
        builder.add_node("final_render", self._final_render_node)
        builder.add_node("human_review", self._human_review_node)

        builder.add_edge(START, "meeting_understanding")
        builder.add_edge(START, "perspective_modeling")

        first_layer = ["meeting_understanding", "perspective_modeling"]
        builder.add_edge(first_layer, "minutes_generation")
        builder.add_edge(first_layer, "action_items")

        builder.add_edge(
            ["minutes_generation", "action_items"],
            "supervisor_review",
        )
        builder.add_conditional_edges(
            "supervisor_review",
            self._route_after_supervision,
            {
                "final_render": "final_render",
                "revision": "revision",
                "quality_failure": "quality_failure",
            },
        )
        builder.add_edge("revision", "supervisor_review")
        builder.add_edge("quality_failure", END)
        builder.add_edge("final_render", "human_review")
        builder.add_edge("human_review", END)

        return builder.compile(
            checkpointer=self.checkpointer,
            interrupt_before=["human_review"],
        )

    async def run(
        self,
        transcript: str,
        user: UserIdentity | None = None,
        review_handler: ReviewHandler | None = None,
    ) -> FinalReport:
        if not transcript.strip():
            raise ValueError("会议文字不能为空")

        initial_state: MeetingState = {
            "transcript": transcript,
            "user": (user or UserIdentity()).model_dump(),
            "revision_count": 0,
        }
        config = {
            "configurable": {
                "thread_id": str(uuid4()),
            }
        }
        state = await self.graph.ainvoke(initial_state, config=config)

        if review_handler is None:
            raise RuntimeError("工作流正在等待人工审核，但没有提供 review_handler")

        preview = validate_payload(FinalReport, state["final_report"])
        decision = await review_handler(preview)
        if decision.strip().lower() != "pass":
            raise RuntimeError("人工审核未通过，最终结果没有正式发布")

        state = await self.graph.ainvoke(None, config=config)

        return validate_payload(
            FinalReport,
            state["final_report"],
        )
