"""LangGraph 工作流编排。

MeetingAgentSystem 负责：组装 Agent 依赖、构建双线并行 DAG、条件路由、启动运行。

架构（注册表驱动）：
- meeting_core：会议理解 + 视角建模（公共事实底座，先行并行执行）
- tasks/minutes_generation：纪要线（生成 → 监督 → 渲染/返工闭环）
- tasks/action_items：待办线（提取 → 监督 → 格式化/返工闭环）
- 两条任务线并行执行，互不阻塞；全局监督标准由 src/supervisor 注入各任务 supervisor。
- 每条任务线的同构节点（agent / supervisor / revision / route）由 ``TASK_LINES``
  注册表自动生成；render / fallback 为各线专属实现。
  新增任务线：写 agent/supervisor/render 三个类 + prompts，在 ``TASK_LINES``
  注册一行即可，state（MeetingState.lines）与节点逻辑零改动。
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable

from langgraph.graph import END, START, StateGraph

from llm_client import LLMClient
from .meeting_core import (
    MeetingUnderstandingAgent,
    PerspectiveModelingAgent,
)
from .meeting_factory import MeetingAgentFactory
from .models import (
    ActionsReport,
    MinutesReport,
    MeetingState,
    UserIdentity,
    is_objective_perspective,
)
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
from tools.validation import validate_payload

logger = logging.getLogger(__name__)

ProgressHandler = Callable[[str, str], None]

QUALITY_WARNING = "生成可能有误，请结合会议原文核对。"
QUALITY_DISCLAIMER = "（生成可能有误）"

# ── 节点降级兜底用的最小空结构（LLM 调用失败时保证图继续运行）──
_EMPTY_UNDERSTANDING = {
    "meeting_purpose": "",
    "topics": [],
    "decisions": [],
    "open_questions": [],
    "risks": [],
}
_EMPTY_PROFILE = {
    "confidence": "low",
    "name": None,
    "inferred_role": None,
    "responsibilities": [],
    "goals": [],
    "concerns": [],
    "relevant_topics": [],
    "evidence": [],
}
_EMPTY_MINUTES_DRAFT = {
    "headline": "",
    "executive_summary": [],
    "key_decisions": [],
    "personally_relevant_points": [],
    "risks_and_blockers": [],
    "unresolved_questions": [],
}
_EMPTY_ACTIONS = {
    "my_actions": [],
    "delegated_actions": [],
    "unassigned_actions": [],
}
# decision=reject 且至少一个检查项失败，满足模型校验约束，路由到 fallback
_REJECT_MINUTES_REVIEW = {
    "decision": "reject",
    "facts_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "perspective_check": {
        "status": "fail",
        "findings": ["LLM 调用失败，未完成审核"],
    },
    "consistency_check": {
        "status": "fail",
        "findings": ["LLM 调用失败，未完成审核"],
    },
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}
_REJECT_ACTIONS_REVIEW = {
    "decision": "reject",
    "action_items_check": {
        "status": "fail",
        "findings": ["LLM 调用失败，未完成审核"],
    },
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

# ── 任务线注册表 ──────────────────────────────────────────────
# 每条任务线的同构节点（agent/supervisor/revision/route）据此自动生成；
# render/fallback 为各线专属实现（见 _render_nodes / _fallback_nodes）。
# 新增任务线：写三个类 + prompts 后在此注册一行即可，state 与节点逻辑零改动。
TASK_LINES: dict[str, dict] = {
    "minutes_generation": {
        "cn_name": "纪要",
        "draft_title": "纪要草稿",
        "agent_attr": "minutes_generation_agent",
        "supervisor_attr": "minutes_supervisor",
        "empty_draft": _EMPTY_MINUTES_DRAFT,
        "reject_review": _REJECT_MINUTES_REVIEW,
        "agent_labels": (
            "MinutesGenerationAgent｜生成客观会议纪要草稿",
            "MinutesGenerationAgent｜生成用户视角纪要",
        ),
        "supervisor_label": "MinutesSupervisorAgent｜审核纪要质量",
        "revision_label": "MinutesRevision｜纪要返工",
    },
    "action_items": {
        "cn_name": "待办",
        "draft_title": "待办提取结果",
        "agent_attr": "action_items_agent",
        "supervisor_attr": "actions_supervisor",
        "empty_draft": _EMPTY_ACTIONS,
        "reject_review": _REJECT_ACTIONS_REVIEW,
        "agent_labels": (
            "ActionItemsAgent｜提取全员客观待办",
            "ActionItemsAgent｜提取待办事项",
        ),
        "supervisor_label": "ActionsSupervisorAgent｜审核待办质量",
        "revision_label": "ActionsRevision｜待办返工",
    },
}


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


def _json(value: object) -> str:
    """将模型或字典序列化为 JSON 字符串。"""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return json.dumps(value, ensure_ascii=False, indent=2)


def _line(state: MeetingState, line_name: str) -> dict:
    """读取某条任务线的子空间（未初始化时返回空 dict）。"""
    return (state.get("lines") or {}).get(line_name) or {}


class _Nodes:
    """图节点实现（mixin，供 MeetingAgentSystem 继承）。

    同构节点（agent / supervisor / revision / route）由 TASK_LINES 注册表
    通过工厂方法生成；render / fallback 为各线专属方法。

    每个节点方法签名与 LangGraph 节点要求一致：
    接收 state，返回部分更新的 dict。
    """

    MAX_REVISIONS = 1

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

    def _supervisor_context(self, state: MeetingState, line_name: str) -> str:
        cfg = TASK_LINES[line_name]
        sub = _line(state, line_name)
        revision_count = sub.get("revision_count", 0)
        mode = self._mode_label(state)
        allowed = (
            "本轮可以选择 approve、revise 或 reject。"
            if revision_count < self.MAX_REVISIONS
            else "返工次数已用完，本轮只能选择 approve 或 reject。"
        )
        return (
            f"视角模式：{mode}\n"
            f"{cfg['cn_name']}返工次数：{revision_count}/{self.MAX_REVISIONS}\n"
            f"{allowed}\n\n"
            f"会议原文（最高事实来源）：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"会议理解：\n{_json(state['meeting_understanding'])}\n\n"
            f"用户视角模型：\n{_json(state['perspective_profile'])}\n\n"
            f"{cfg['draft_title']}：\n{_json(sub['draft'])}"
        )

    def _minutes_render_context(
        self, state: MeetingState, *, fallback: bool
    ) -> str:
        mode = self._mode_label(state)
        minutes_line = _line(state, "minutes_generation")
        review = minutes_line.get("supervisor_review") or {}
        header = ""
        if fallback:
            findings = self._collect_supervisor_findings(review)
            findings_text = (
                "；".join(findings) if findings
                else "Supervisor 未批准当前纪要"
            )
            decision = review.get("decision", "reject")
            header = (
                "注意：以下纪要未通过 Supervisor 审核，你仍需基于现有草稿整理可读输出，"
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
            f"已批准纪要草稿：\n{_json(minutes_line.get('draft'))}\n\n"
            f"纪要审核结论：\n{_json(review)}"
        )

    @staticmethod
    def _collect_supervisor_findings(review: dict) -> list[str]:
        findings: list[str] = []
        for key in ("facts_check", "perspective_check", "consistency_check"):
            check = review.get(key) or {}
            findings.extend(check.get("findings") or [])
        return findings

    @staticmethod
    def _assemble_report_from_drafts(
        state: MeetingState,
    ) -> tuple[MinutesReport, ActionsReport]:
        """不依赖 LLM 的确定性兜底：从中间草稿分别拼出纪要、待办两个输出。"""
        minutes = _line(state, "minutes_generation").get("draft") or {}
        actions = _line(state, "action_items").get("draft") or {}
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

        return (
            MinutesReport(title=title, personalized_minutes=text),
            ActionsReport(action_items=action_items),
        )

    # ── 核心节点：会议理解 + 视角建模 ─────────────────────────

    async def _meeting_understanding_node(
        self, state: MeetingState
    ) -> dict:
        label = "MeetingUnderstandingAgent｜理解会议内容"
        self._progress("start", label)
        try:
            result = await self.meeting_understanding_agent.run(
                state["transcript"]
            )
        except Exception as exc:
            logger.warning("会议理解失败，使用空理解继续", exc_info=True)
            self._progress("done", label)
            return {
                "meeting_understanding": _EMPTY_UNDERSTANDING,
                "quality_degraded": True,
            }
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
        try:
            result = await self.perspective_modeling_agent.run(
                state["transcript"],
                _json(state["user"]),
            )
        except Exception as exc:
            logger.warning("视角建模失败，使用空视角继续", exc_info=True)
            self._progress("done", label)
            return {
                "perspective_profile": _EMPTY_PROFILE,
                "quality_degraded": True,
            }
        self._progress("done", label)
        return {"perspective_profile": result.model_dump()}

    # ── 同构节点工厂（由 TASK_LINES 注册表生成）───────────────

    def _make_agent_node(self, line_name: str):
        """生成某任务线的「生成/提取」节点（agent → 草稿）。"""
        cfg = TASK_LINES[line_name]

        async def node(state: MeetingState) -> dict:
            objective = bool(state.get("objective_perspective"))
            label = (
                cfg["agent_labels"][0] if objective else cfg["agent_labels"][1]
            )
            self._progress("start", label)
            agent = getattr(self, cfg["agent_attr"])
            try:
                result = await agent.run(
                    self._revision_context(
                        self._shared_context(state),
                        _line(state, line_name).get("revision_feedback", []),
                        f"{cfg['cn_name']}返工意见",
                    )
                )
            except Exception as exc:
                logger.warning(
                    f"{cfg['cn_name']}生成失败，使用空草稿继续", exc_info=True
                )
                self._progress("done", label)
                return {
                    "lines": {
                        line_name: {
                            "draft": cfg["empty_draft"],
                            "degraded": True,
                        }
                    },
                    "quality_degraded": True,
                }
            self._progress("done", label)
            return {"lines": {line_name: {"draft": result.model_dump()}}}

        return node

    def _make_supervisor_node(self, line_name: str):
        """生成某任务线的「审核」节点（supervisor → approve/revise/reject）。"""
        cfg = TASK_LINES[line_name]

        async def node(state: MeetingState) -> dict:
            self._progress("start", cfg["supervisor_label"])
            supervisor = getattr(self, cfg["supervisor_attr"])
            try:
                review = await supervisor.review(
                    self._supervisor_context(state, line_name)
                )
            except Exception as exc:
                logger.warning(
                    f"{cfg['cn_name']}审核失败，按 reject 转降级", exc_info=True
                )
                self._progress("done", cfg["supervisor_label"])
                return {
                    "lines": {
                        line_name: {
                            "supervisor_review": cfg["reject_review"],
                            "revision_feedback": list(
                                cfg["reject_review"]["feedback"]
                            ),
                            "degraded": True,
                        }
                    },
                    "quality_degraded": True,
                }
            self._progress("done", cfg["supervisor_label"])
            return {
                "lines": {
                    line_name: {
                        "supervisor_review": review.model_dump(),
                        "revision_feedback": review.feedback,
                    }
                }
            }

        return node

    def _make_revision_node(self, line_name: str, agent_node):
        """生成某任务线的「返工」节点：重跑 agent 并累计返工次数。"""
        cfg = TASK_LINES[line_name]

        async def node(state: MeetingState) -> dict:
            self._progress("start", cfg["revision_label"])
            updates = await agent_node(state)
            line_patch = updates.setdefault("lines", {}).setdefault(
                line_name, {}
            )
            line_patch["revision_count"] = (
                _line(state, line_name).get("revision_count", 0) + 1
            )
            self._progress("done", cfg["revision_label"])
            return updates

        return node

    def _make_route(self, line_name: str):
        """生成某任务线的条件路由（approve→render / reject或超限→fallback / 否则返工）。"""

        def route(state: MeetingState) -> str:
            decision = _line(state, line_name)["supervisor_review"]["decision"]
            if decision == "approve":
                return f"{line_name}_render"
            if decision == "reject" or _line(state, line_name).get(
                "revision_count", 0
            ) >= self.MAX_REVISIONS:
                return f"{line_name}_fallback"
            return f"{line_name}_revision"

        return route

    # ── 纪要线专属节点：渲染 + 降级 ───────────────────────────

    async def _minutes_render_node(self, state: MeetingState) -> dict:
        label = "RenderMinutes｜渲染纪要正文"
        self._progress("start", label)
        if state.get("streaming"):
            # 流式模式：图内不调用 LLM，由 run_streaming 接管流式输出
            self._progress("done", label)
            return {"rendered_minutes": ""}
        try:
            minutes = await self.minutes_render.run(
                self._minutes_render_context(state, fallback=False),
                template=state.get("template", ""),
            )
        except Exception as exc:
            logger.warning("纪要渲染失败，使用确定性拼装", exc_info=True)
            minutes_report, _ = self._assemble_report_from_drafts(state)
            minutes = minutes_report.personalized_minutes
            self._progress("done", label)
            return {
                "rendered_minutes": minutes,
                "quality_degraded": True,
            }
        self._progress("done", label)
        # 渲染本身成功不写 degraded（由 supervisor 判定或 fallback 标记）
        return {"rendered_minutes": minutes}

    async def _minutes_fallback_node(self, state: MeetingState) -> dict:
        """纪要线降级：先尝试 LLM 渲染，失败则确定性拼装。"""
        label = "FallbackMinutes｜降级渲染纪要"
        self._progress("start", label)
        if state.get("streaming"):
            # 流式模式：图内不调用 LLM，由 run_streaming 接管降级输出
            self._progress("done", label)
            return {
                "rendered_minutes": "",
                "quality_degraded": True,
                "lines": {"minutes_generation": {"degraded": True}},
            }
        context = self._minutes_render_context(state, fallback=True)
        try:
            minutes = await self.minutes_render.run(
                context, template=state.get("template", "")
            )
        except Exception as exc:
            logger.warning("降级渲染纪要失败，使用确定性拼装", exc_info=True)
            minutes_report, _ = self._assemble_report_from_drafts(state)
            minutes = minutes_report.personalized_minutes
        if QUALITY_DISCLAIMER not in (minutes or ""):
            minutes = (
                f"{minutes}\n\n{QUALITY_DISCLAIMER}"
                if minutes
                else QUALITY_DISCLAIMER
            )
        self._progress("done", label)
        return {
            "rendered_minutes": minutes,
            "quality_degraded": True,
            "lines": {"minutes_generation": {"degraded": True}},
        }

    # ── 待办线专属节点：格式化 + 降级 ─────────────────────────

    async def _actions_render_node(self, state: MeetingState) -> dict:
        label = "FormatActions｜格式化待办事项"
        self._progress("start", label)
        items = self.action_items_render.extract_actions(state)
        item_template = state.get("item_template", "")
        if item_template.strip() and not state.get("streaming"):
            # 指定了待办模板：LLM 按模板渲染文本（流式模式由 run_streaming 接管）
            try:
                text = await self.action_items_render.render_with_template(
                    state, item_template
                )
            except Exception as exc:
                logger.warning(
                    "待办模板渲染失败，退化为确定性列表", exc_info=True
                )
                self._progress("done", label)
                return {
                    "formatted_actions": items,
                    "quality_degraded": True,
                    "lines": {"action_items": {"degraded": True}},
                }
            self._progress("done", label)
            return {"formatted_actions": items, "formatted_actions_text": text}
        self._progress("done", label)
        return {"formatted_actions": items}

    async def _actions_fallback_node(self, state: MeetingState) -> dict:
        """待办线降级：确定性提取（不调 LLM）。"""
        label = "FallbackActions｜降级提取待办"
        self._progress("start", label)
        items = self.action_items_render.extract_actions(state)
        self._progress("done", label)
        return {
            "formatted_actions": items,
            "quality_degraded": True,
            "lines": {"action_items": {"degraded": True}},
        }


class MeetingAgentSystem(_Nodes):
    """使用 LangGraph 编排会议分析、双线并行审核返工与最终输出。"""

    def __init__(
        self,
        client: LLMClient | None = None,
        progress_handler: ProgressHandler | None = None,
    ) -> None:
        self.client = client or LLMClient()
        self.progress_handler = progress_handler

        # 通过工厂组装全部 Agent 依赖
        agents = MeetingAgentFactory.create(self.client)
        self.meeting_understanding_agent: MeetingUnderstandingAgent = agents[
            "meeting_understanding"
        ]
        self.perspective_modeling_agent: PerspectiveModelingAgent = agents[
            "perspective_modeling"
        ]
        self.minutes_generation_agent: MinutesGenerationAgent = agents[
            "minutes_generation"
        ]
        self.minutes_supervisor: MinutesGenerationSupervisor = agents[
            "minutes_supervisor"
        ]
        self.minutes_render: MinutesGenerationRender = agents[
            "minutes_render"
        ]
        self.action_items_agent: ActionItemsAgent = agents["action_items"]
        self.actions_supervisor: ActionItemsSupervisor = agents[
            "actions_supervisor"
        ]
        self.action_items_render: ActionItemsRender = agents[
            "actions_render"
        ]

        # 各线专属的渲染 / 降级节点（同构节点由注册表在 _build_graph 中生成）
        self._render_nodes = {
            "minutes_generation": self._minutes_render_node,
            "action_items": self._actions_render_node,
        }
        self._fallback_nodes = {
            "minutes_generation": self._minutes_fallback_node,
            "action_items": self._actions_fallback_node,
        }
        self.graph = self._build_graph()

    # ── 进度回调 ──────────────────────────────────────────────

    def _progress(self, event: str, label: str) -> None:
        if self.progress_handler:
            self.progress_handler(event, label)

    # ── 图构建（注册表驱动，双线并行）─────────────────────────

    def _build_graph(self) -> object:
        builder = StateGraph(MeetingState)

        # 核心层：会议理解 + 视角建模（并行）
        builder.add_node(
            "meeting_understanding", self._meeting_understanding_node
        )
        builder.add_node(
            "perspective_modeling", self._perspective_modeling_node
        )
        builder.add_edge(START, "meeting_understanding")
        builder.add_edge(START, "perspective_modeling")
        core = ["meeting_understanding", "perspective_modeling"]

        # 任务线：由注册表生成同构节点（agent/supervisor/revision/route）
        for line_name in TASK_LINES:
            agent_node = self._make_agent_node(line_name)
            supervisor_node = self._make_supervisor_node(line_name)
            revision_node = self._make_revision_node(line_name, agent_node)
            route = self._make_route(line_name)

            builder.add_node(f"{line_name}_agent", agent_node)
            builder.add_node(f"{line_name}_supervisor", supervisor_node)
            builder.add_node(f"{line_name}_revision", revision_node)
            builder.add_node(f"{line_name}_render", self._render_nodes[line_name])
            builder.add_node(
                f"{line_name}_fallback", self._fallback_nodes[line_name]
            )

            # 核心层汇合 → 本线 agent → supervisor → 条件路由
            builder.add_edge(core, f"{line_name}_agent")
            builder.add_edge(f"{line_name}_agent", f"{line_name}_supervisor")
            builder.add_conditional_edges(
                f"{line_name}_supervisor",
                route,
                {
                    f"{line_name}_render": f"{line_name}_render",
                    f"{line_name}_revision": f"{line_name}_revision",
                    f"{line_name}_fallback": f"{line_name}_fallback",
                },
            )
            builder.add_edge(f"{line_name}_revision", f"{line_name}_supervisor")
            builder.add_edge(f"{line_name}_render", END)
            builder.add_edge(f"{line_name}_fallback", END)

        return builder.compile()

    # ── 启动入口 ──────────────────────────────────────────────

    async def run(
        self,
        transcript: str,
        user: UserIdentity | None = None,
        template: str = "",
        item_template: str = "",
    ) -> tuple[MinutesReport, ActionsReport]:
        if not transcript.strip():
            raise ValueError("会议文字不能为空")

        # 规范化文本：合并段落内的硬换行（PDF/OCR 常见问题），保留段落间空行
        transcript = _normalize_transcript(transcript)

        template = template or ""
        item_template = item_template or ""
        user = user or UserIdentity()
        objective_mode = is_objective_perspective(user)
        user_data = user.model_dump()
        if objective_mode and not user_data.get("perspective"):
            user_data["perspective"] = "objective"

        initial_state: MeetingState = {
            "transcript": transcript,
            "user": user_data,
            "objective_perspective": objective_mode,
            "template": template,
            "item_template": item_template,
        }
        try:
            state = await self.graph.ainvoke(initial_state)
        except Exception as exc:
            # 最后防线：图内任何未接住的异常都不让运行崩溃，走确定性兜底
            logger.warning("图执行失败，使用确定性兜底输出", exc_info=True)
            minutes_fb, actions_fb = self._assemble_report_from_drafts(
                initial_state
            )
            minutes_fb.quality_warning = QUALITY_WARNING
            actions_fb.quality_warning = QUALITY_WARNING
            return minutes_fb, actions_fb

        # 从并行渲染结果分别组装纪要、待办两个独立输出
        minutes = state.get("rendered_minutes") or ""
        actions = state.get("formatted_actions") or []
        actions_text = state.get("formatted_actions_text")
        quality_degraded = bool(state.get("quality_degraded"))

        if objective_mode:
            title = "客观会议纪要"
        else:
            title = f"{user_data.get('name', '用户')}视角会议纪要"

        warning = QUALITY_WARNING if quality_degraded else None
        minutes_report = MinutesReport(
            title=title,
            personalized_minutes=minutes,
            quality_warning=warning,
        )
        actions_report = ActionsReport(
            action_items=actions,
            quality_warning=warning,
            personalized_text=actions_text,
        )
        try:
            return (
                validate_payload(MinutesReport, minutes_report.model_dump()),
                validate_payload(ActionsReport, actions_report.model_dump()),
            )
        except Exception:
            logger.warning("输出校验失败，退回确定性兜底", exc_info=True)
            minutes_fb, actions_fb = self._assemble_report_from_drafts(state)
            minutes_fb.quality_warning = QUALITY_WARNING
            actions_fb.quality_warning = QUALITY_WARNING
            return minutes_fb, actions_fb

    # ── 流式并行输出 ─────────────────────────────────────────

    async def run_streaming(
        self,
        transcript: str,
        user: UserIdentity | None = None,
        template: str = "",
        item_template: str = "",
    ) -> AsyncIterator[dict]:
        """流式版本：纪要 LLM token 逐块推送、待办即时推送，两者并行互不等待。

        事件协议（async generator，按产出顺序 yield dict）：

        - ``{"type": "actions", "items": [待办 dict, ...]}``
          待办列表（无待办模板时确定性拼装，秒出；有模板时先发结构化数据）
        - ``{"type": "actions_chunk", "text": str}``
          待办模板渲染流式块（指定 --item_template 时，LLM 按模板流式渲染，
          与 minutes_chunk 对称；逐块追加即为完整待办文本）
        - ``{"type": "minutes_chunk", "text": str}``
          纪要流式增量块（LLM SSE token 流，逐块追加即为全文）
        - ``{"type": "done", "quality_warning": str | None}``
          结束标记；quality_warning 非空表示输出降级，需提示核对

        与 ``run()`` 的区别：``run()`` 返回 ``(MinutesReport, ActionsReport)`` 两个独立对象；
        本方法把纪要与待办作为两条并行事件流分别产出。
        """
        if not transcript.strip():
            raise ValueError("会议文字不能为空")

        # 前置阶段与 run() 完全一致：归一化 → 图执行（分析 + 双线审核 + 返工）
        transcript = _normalize_transcript(transcript)
        template = template or ""
        item_template = item_template or ""
        user = user or UserIdentity()
        objective_mode = is_objective_perspective(user)
        user_data = user.model_dump()
        if objective_mode and not user_data.get("perspective"):
            user_data["perspective"] = "objective"

        initial_state: MeetingState = {
            "transcript": transcript,
            "user": user_data,
            "objective_perspective": objective_mode,
            "template": template,
            "item_template": item_template,
            "streaming": True,  # 图内渲染节点跳过 LLM，由本方法接管流式输出
        }
        try:
            state = await self.graph.ainvoke(initial_state)
        except Exception as exc:
            # 最后防线：图内任何未接住的异常都不让运行崩溃，走确定性兜底
            logger.warning("图执行失败，使用确定性兜底输出", exc_info=True)
            minutes_fb, actions_fb = self._assemble_report_from_drafts(
                initial_state
            )
            yield {
                "type": "minutes_chunk",
                "text": minutes_fb.personalized_minutes,
            }
            yield {"type": "actions", "items": actions_fb.action_items}
            yield {"type": "done", "quality_warning": QUALITY_WARNING}
            return

        actions = state.get("formatted_actions") or []
        # 按线隔离的降级标记：一条线降级不牵连另一条的渲染方式
        minutes_degraded = bool(
            _line(state, "minutes_generation").get("degraded")
        )
        actions_degraded = bool(
            _line(state, "action_items").get("degraded")
        )
        quality_warning = (
            QUALITY_WARNING
            if (
                minutes_degraded
                or actions_degraded
                or bool(state.get("quality_degraded"))
            )
            else None
        )

        # 并行启动两个事件源，通过队列合并：纪要流式生成期间待办已可交付
        queue: asyncio.Queue = asyncio.Queue()

        async def _produce_actions() -> None:
            try:
                if item_template.strip() and not actions_degraded:
                    # 待办模板 + 待办线未降级：先发结构化列表，再 LLM 流式渲染文本
                    await queue.put({"type": "actions", "items": actions})
                    async for chunk in (
                        self.action_items_render.stream_with_template(
                            state, item_template
                        )
                    ):
                        await queue.put(
                            {"type": "actions_chunk", "text": chunk}
                        )
                else:
                    await queue.put({"type": "actions", "items": actions})
            except Exception as exc:
                await queue.put(exc)  # 异常对象作为事件传出，由主循环抛出
            finally:
                await queue.put(None)

        async def _produce_minutes() -> None:
            try:
                if minutes_degraded:
                    # 纪要线降级：确定性拼装，一次性整段交付
                    minutes_report, _ = self._assemble_report_from_drafts(state)
                    await queue.put(
                        {
                            "type": "minutes_chunk",
                            "text": minutes_report.personalized_minutes,
                        }
                    )
                    return
                context = self._minutes_render_context(state, fallback=False)
                async for chunk in self.minutes_render.stream(
                    context, template
                ):
                    await queue.put({"type": "minutes_chunk", "text": chunk})
            except Exception as exc:
                await queue.put(exc)  # 异常对象作为事件传出，由主循环抛出
            finally:
                await queue.put(None)

        tasks = [
            asyncio.create_task(_produce_actions()),
            asyncio.create_task(_produce_minutes()),
        ]
        remaining = len(tasks)
        while remaining:
            event = await queue.get()
            if event is None:
                remaining -= 1
                continue
            if isinstance(event, Exception):
                raise event
            yield event
        yield {"type": "done", "quality_warning": quality_warning}
