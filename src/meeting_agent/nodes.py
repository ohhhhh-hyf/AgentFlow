"""MeetingAgentSystem 的图节点实现。

提取为独立的 mixin 类，使 orchestrator.py 专注于编排与路由。
"""
from __future__ import annotations

import asyncio
import json

from .models import FinalReport, is_objective_perspective
from .state import MeetingState

QUALITY_WARNING = "生成可能有误，请结合会议原文核对。"
QUALITY_DISCLAIMER = "（生成可能有误）"


def _json(value: object) -> str:
    """将模型或字典序列化为 JSON 字符串。"""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return json.dumps(value, ensure_ascii=False, indent=2)


class _Nodes:
    """图节点实现（mixin，供 MeetingAgentSystem 继承）。

    每个节点方法签名与 LangGraph 节点要求一致：
    接收 state，返回部分更新的 dict。
    """

    # ── 辅助方法 ──────────────────────────────────────────────

    @staticmethod
    def _mode_label(state: MeetingState) -> str:
        return "objective" if state.get("objective_perspective") else "personal"

    @staticmethod
    def _shared_context(state: MeetingState) -> str:
        mode = _Nodes._mode_label(state)
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
    def _revision_context(
        context: str, feedback: list[str], label: str
    ) -> str:
        if not feedback:
            return context
        return f"{context}\n\nSupervisor {label}：\n{_json(feedback)}"

    def _supervisor_context(self, state: MeetingState) -> str:
        revision_count = state.get("revision_count", 0)
        mode = self._mode_label(state)
        max_revisions: int = getattr(self, "MAX_REVISIONS", 1)
        allowed = (
            "本轮可以选择 approve、revise_minutes、revise_actions、"
            "revise_both 或 reject。"
            if revision_count < max_revisions
            else "返工次数已用完，本轮只能选择 approve 或 reject。"
        )
        return (
            f"视角模式：{mode}\n"
            f"返工次数：{revision_count}/{max_revisions}\n{allowed}\n\n"
            f"会议原文（最高事实来源）：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"会议理解：\n{_json(state['meeting_understanding'])}\n\n"
            f"用户视角模型：\n{_json(state['perspective_profile'])}\n\n"
            f"纪要草稿：\n{_json(state['minutes_draft'])}\n\n"
            f"待办提取结果：\n{_json(state['extracted_action_items'])}"
        )

    def _render_context(
        self, state: MeetingState, *, fallback: bool
    ) -> str:
        mode = self._mode_label(state)
        header = ""
        if fallback:
            findings = self._collect_supervisor_findings(state)
            findings_text = (
                "；".join(findings) if findings
                else "Supervisor 未批准当前结果"
            )
            decision = (
                (state.get("supervisor_review") or {}).get("decision", "reject")
            )
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
            minutes = (
                f"{minutes}\n\n{QUALITY_DISCLAIMER}"
                if minutes
                else QUALITY_DISCLAIMER
            )

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
            purpose = (state.get("meeting_understanding") or {}).get(
                "meeting_purpose"
            )
            text = (
                "系统未能通过质量审核，以下为基于现有材料的粗略整理。"
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

    # ── 图节点 ────────────────────────────────────────────────

    async def _meeting_understanding_node(
        self, state: MeetingState
    ) -> dict:
        label = "MeetingUnderstandingAgent｜理解会议内容"
        self._progress("start", label)
        result = await self.meeting_understanding_agent.run(
            state["transcript"]
        )
        self._progress("done", label)
        return {"meeting_understanding": result.model_dump()}

    async def _perspective_modeling_node(
        self, state: MeetingState
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

    async def _minutes_generation_node(
        self, state: MeetingState
    ) -> dict:
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

    async def _supervisor_review_node(
        self, state: MeetingState
    ) -> dict:
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
        max_revisions: int = getattr(self, "MAX_REVISIONS", 1)
        if decision == "reject" or state.get("revision_count", 0) >= max_revisions:
            return "fallback_render"
        return "revision"

    async def _revision_node(self, state: MeetingState) -> dict:
        import logging
        _logger = logging.getLogger(__name__)

        decision = state["supervisor_review"]["decision"]
        self._progress("start", "Revision｜根据审核意见返工")
        max_revisions: int = getattr(self, "MAX_REVISIONS", 1)
        updates: dict = {
            "revision_count": state.get("revision_count", 0) + 1,
        }

        if decision == "revise_minutes":
            updates.update(
                await self._minutes_generation_node(state)
            )
        elif decision == "revise_actions":
            updates.update(
                await self._action_items_node(state)
            )
        elif decision == "revise_both":
            minutes, actions = await asyncio.gather(
                self._minutes_generation_node(state),
                self._action_items_node(state),
            )
            updates.update(minutes)
            updates.update(actions)
        else:
            # 意外的 decision（理论上不应到达，validation 已拦截），不崩溃，走降级
            _logger.warning(
                "Revision 收到不支持的 Supervisor 决定：%s，跳过返工，标记降级",
                decision,
            )
            updates["quality_degraded"] = True
            # 确保下次路由走到 fallback
            updates["revision_count"] = max_revisions + 1

        self._progress("done", "Revision｜根据审核意见返工")
        return updates

    # ── 最终输出（并行：纪要 + 待办）──────────────────────────

    @staticmethod
    def _extract_actions(state: MeetingState) -> list[dict]:
        """从 state 中提取最终待办列表（确定性，不需 LLM）。"""
        actions = state.get("extracted_action_items") or {}
        if state.get("objective_perspective"):
            items = list(actions.get("my_actions") or [])
            items.extend(actions.get("unassigned_actions") or [])
        else:
            items = list(actions.get("my_actions") or [])
        return items

    async def _render_minutes_node(self, state: MeetingState) -> dict:
        label = "RenderMinutes｜渲染纪要正文"
        self._progress("start", label)
        if state.get("streaming"):
            # 流式模式：图内不调用 LLM，由 run_streaming 接管流式输出
            self._progress("done", label)
            return {"rendered_minutes": "", "quality_degraded": False}
        minutes = await self.final_renderer.run_minutes_only(
            self._render_context(state, fallback=False),
            template=state.get("template", ""),
        )
        self._progress("done", label)
        return {"rendered_minutes": minutes, "quality_degraded": False}

    async def _format_actions_node(self, state: MeetingState) -> dict:
        label = "FormatActions｜格式化待办事项"
        self._progress("start", label)
        items = self._extract_actions(state)
        self._progress("done", label)
        return {"formatted_actions": items}

    async def _fallback_minutes_node(self, state: MeetingState) -> dict:
        """降级渲染纪要正文。"""
        label = "FallbackMinutes｜降级渲染纪要"
        self._progress("start", label)
        if state.get("streaming"):
            # 流式模式：图内不调用 LLM，由 run_streaming 接管降级输出
            self._progress("done", label)
            return {"rendered_minutes": "", "quality_degraded": True}
        context = self._render_context(state, fallback=True)
        try:
            minutes = await self.final_renderer.run_minutes_only(
                context, template=state.get("template", "")
            )
        except Exception:
            report = self._assemble_report_from_drafts(state)
            minutes = report.personalized_minutes
        if QUALITY_DISCLAIMER not in (minutes or ""):
            minutes = f"{minutes}\n\n{QUALITY_DISCLAIMER}" if minutes else QUALITY_DISCLAIMER
        self._progress("done", label)
        return {"rendered_minutes": minutes, "quality_degraded": True}

    async def _fallback_actions_node(self, state: MeetingState) -> dict:
        """降级提取待办（确定性）。"""
        label = "FallbackActions｜降级提取待办"
        self._progress("start", label)
        items = self._extract_actions(state)
        self._progress("done", label)
        return {"formatted_actions": items}
