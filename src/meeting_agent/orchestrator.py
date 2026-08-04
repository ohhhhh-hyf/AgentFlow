from __future__ import annotations

import asyncio
import json
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
from .state import MeetingState
from .validation import validate_payload


ProgressHandler = Callable[[str, str], None]

QUALITY_WARNING = "生成可能有误，请结合会议原文核对。"
QUALITY_DISCLAIMER = "（生成可能有误）"


def _json(value) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return json.dumps(value, ensure_ascii=False, indent=2)


class MeetingAgentSystem:
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
        objective = bool(state.get("objective_perspective"))
        label = (
            "PerspectiveModelingAgent｜建立客观全员视角"
            if objective
            else "PerspectiveModelingAgent｜建立用户视角"
        )
        self._progress("start", label)
        result = await self.perspective_modeling_agent.run(
            state["transcript"],
            _json(state["user"]),
        )
        self._progress("done", label)
        return {"perspective_profile": result.model_dump()}

    @staticmethod
    def _mode_label(state: MeetingState) -> str:
        return "objective" if state.get("objective_perspective") else "personal"

    @staticmethod
    def _shared_context(state: MeetingState) -> str:
        mode = MeetingAgentSystem._mode_label(state)
        return (
            f"视角模式：{mode}\n"
            f"说明：perspective=objective 时为客观全员口径；"
            f"缺省或其它值为个人用户口径。\n\n"
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
        objective = bool(state.get("objective_perspective"))
        label = (
            "MinutesGenerationAgent｜生成客观会议纪要草稿"
            if objective
            else "MinutesGenerationAgent｜生成用户视角纪要"
        )
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
        objective = bool(state.get("objective_perspective"))
        label = (
            "ActionItemsAgent｜提取全员客观待办"
            if objective
            else "ActionItemsAgent｜提取待办事项"
        )
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
        mode = self._mode_label(state)
        allowed = (
            "本轮可以选择 approve、revise_minutes、revise_actions、"
            "revise_both 或 reject。"
            if revision_count < self.MAX_REVISIONS
            else "返工次数已用完，本轮只能选择 approve 或 reject。"
        )
        return (
            f"视角模式：{mode}\n"
            f"返工次数：{revision_count}/{self.MAX_REVISIONS}\n{allowed}\n\n"
            f"会议原文（最高事实来源）：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"会议理解：\n{_json(state['meeting_understanding'])}\n\n"
            f"用户视角模型：\n{_json(state['perspective_profile'])}\n\n"
            f"纪要草稿：\n{_json(state['minutes_draft'])}\n\n"
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
        # reject，或返工额度已用尽仍未通过：走兜底输出，保证一定有结果
        if decision == "reject" or state.get("revision_count", 0) >= self.MAX_REVISIONS:
            return "fallback_render"
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
    def _collect_supervisor_findings(state: MeetingState) -> list[str]:
        review = state.get("supervisor_review") or {}
        findings: list[str] = []
        for key in (
            "facts_check",
            "perspective_check",
            "action_items_check",
            "consistency_check",
        ):
            check = review.get(key) or {}
            findings.extend(check.get("findings") or [])
        return findings

    @staticmethod
    def _apply_quality_disclaimer(report: FinalReport) -> FinalReport:
        """为降级输出附加醒目提示，保证用户一定看到风险说明。"""
        minutes = (report.personalized_minutes or "").rstrip()
        if QUALITY_DISCLAIMER not in minutes:
            minutes = f"{minutes}\n\n{QUALITY_DISCLAIMER}" if minutes else QUALITY_DISCLAIMER

        title = (report.title or "会议纪要").strip()
        if QUALITY_DISCLAIMER not in title:
            title = f"{title}{QUALITY_DISCLAIMER}"

        return FinalReport(
            title=title,
            personalized_minutes=minutes,
            action_items=list(report.action_items or []),
            quality_warning=QUALITY_WARNING,
        )

    @staticmethod
    def _assemble_report_from_drafts(state: MeetingState) -> FinalReport:
        """不依赖 LLM 的确定性兜底：从中间草稿拼出可读结果。"""
        minutes = state.get("minutes_draft") or {}
        actions = state.get("extracted_action_items") or {}
        user = state.get("user") or {}
        objective = bool(state.get("objective_perspective"))
        user_name = user.get("name") or ("客观记录" if objective else "用户")

        sections: list[str] = []
        headline = minutes.get("headline")
        if headline:
            sections.append(str(headline))

        section_map = (
            ("executive_summary", "会议要点"),
            ("key_decisions", "关键决策"),
            (
                "personally_relevant_points",
                "全员执行要点" if objective else "职责相关事项",
            ),
            ("risks_and_blockers", "风险与阻塞"),
            ("unresolved_questions", "未决问题"),
        )
        for key, label in section_map:
            items = minutes.get(key) or []
            if not items:
                continue
            body = "；".join(str(item) for item in items if item)
            if body:
                sections.append(f"{label}：{body}")

        if sections:
            text = "\n".join(sections)
        else:
            purpose = (state.get("meeting_understanding") or {}).get("meeting_purpose")
            text = (
                f"系统未能通过质量审核，以下为基于现有材料的粗略整理。"
                f"{f'会议目的：{purpose}' if purpose else '请直接参考会议原文。'}"
            )

        if objective:
            action_items = list(actions.get("my_actions") or [])
            action_items.extend(actions.get("unassigned_actions") or [])
            title = "客观会议纪要"
        else:
            action_items = list(actions.get("my_actions") or [])
            title = f"{user_name}视角会议纪要"

        return FinalReport(
            title=title,
            personalized_minutes=text,
            action_items=action_items,
        )

    def _render_context(self, state: MeetingState, *, fallback: bool) -> str:
        mode = self._mode_label(state)
        header = ""
        if fallback:
            findings = self._collect_supervisor_findings(state)
            findings_text = "；".join(findings) if findings else "Supervisor 未批准当前结果"
            decision = (state.get("supervisor_review") or {}).get("decision", "reject")
            header = (
                "注意：以下结果未通过 Supervisor 审核，你仍需基于现有草稿整理可读输出，"
                "不得编造草稿和原文中没有的事实；优先保留有明确证据的内容。"
                f"\n未通过原因摘要：{findings_text}"
                f"\nSupervisor 决定：{decision}\n\n"
            )
        return (
            f"{header}"
            f"视角模式：{mode}\n"
            f"objective_perspective：{bool(state.get('objective_perspective'))}\n\n"
            f"会议原文：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"已审核会议理解：\n{_json(state.get('meeting_understanding'))}\n\n"
            f"已审核用户视角：\n{_json(state.get('perspective_profile'))}\n\n"
            f"已批准纪要草稿：\n{_json(state.get('minutes_draft'))}\n\n"
            f"已批准待办结果：\n{_json(state.get('extracted_action_items'))}\n\n"
            f"Supervisor 审核结论：\n{_json(state.get('supervisor_review'))}"
        )

    async def _final_render_node(self, state: MeetingState) -> dict:
        label = "FinalRenderer｜整理最终展示内容"
        self._progress("start", label)
        result = await self.final_renderer.run(
            self._render_context(state, fallback=False)
        )
        self._progress("done", label)
        return {
            "quality_degraded": False,
            "final_report": result.model_dump(),
        }

    async def _fallback_render_node(self, state: MeetingState) -> dict:
        """Supervisor 未批准时的兜底：尽量渲染现有草稿，并标注可能有误。"""
        label = "FallbackRenderer｜降级输出（生成可能有误）"
        self._progress("start", label)

        context = self._render_context(state, fallback=True)

        try:
            rendered = await self.final_renderer.run(context)
        except Exception:
            # 渲染也失败时，用中间草稿确定性拼装，确保一定有输出
            rendered = MeetingAgentSystem._assemble_report_from_drafts(state)

        report = self._apply_quality_disclaimer(rendered)
        self._progress("done", label)
        return {
            "quality_degraded": True,
            "final_report": report.model_dump(),
        }

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
                "fallback_render": "fallback_render",
            },
        )
        builder.add_edge("revision", "supervisor_review")
        builder.add_edge("fallback_render", END)
        builder.add_edge("final_render", END)

        return builder.compile()

    async def run(
        self,
        transcript: str,
        user: UserIdentity | None = None,
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
        }
        state = await self.graph.ainvoke(initial_state)

        return validate_payload(
            FinalReport,
            state["final_report"],
        )
