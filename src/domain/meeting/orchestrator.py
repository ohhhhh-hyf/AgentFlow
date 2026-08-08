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
from collections.abc import AsyncIterator, Iterable
from dataclasses import fields

from langgraph.graph import END, START, StateGraph

from llm_client import LLMClient
from .meeting_core import (
    MeetingUnderstandingAgent,
    PerspectiveModelingAgent,
)
from .meeting_factory import MeetingAgentFactory
from .line_registry import LINE_CN_NAMES
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

QUALITY_WARNING = "生成可能有误，请结合会议原文核对。"
QUALITY_DISCLAIMER = "（生成可能有误）"

# ── 空结构常量生成区：由 tools/scripts/generation_contract.py 生成，勿手改 ──

_EMPTY_ACTION_ITEMS = {
    "my_actions": [],
    "delegated_actions": [],
    "unassigned_actions": [],
}

_EMPTY_MEETING_UNDERSTANDING = {
    "meeting_purpose": "",
    "topics": [],
    "decisions": [],
    "open_questions": [],
    "risks": [],
}

_EMPTY_MINUTES = {
    "headline": "",
    "executive_summary": [],
    "key_decisions": [],
    "personally_relevant_points": [],
    "risks_and_blockers": [],
    "unresolved_questions": [],
}

_EMPTY_PERSPECTIVE_MODELING = {
    "confidence": "high",
    "name": None,
    "inferred_role": None,
    "responsibilities": [],
    "goals": [],
    "concerns": [],
    "relevant_topics": [],
    "evidence": [],
}


# ── 空结构常量生成区结束 ──

# ── 拒绝审核常量生成区：由 tools/scripts/supervisor_contract.py 生成，勿手改 ──

_REJECT_MINUTES_REVIEW = {
    "decision": "reject",
    "facts_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "perspective_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "consistency_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_ACTION_ITEMS_REVIEW = {
    "decision": "reject",
    "action_items_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}


# ── 拒绝审核常量生成区结束 ──

# ── 任务线注册生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──

TASK_LINES: dict[str, dict] = {
    "action_items": {
        "agent_attr": "action_items_agent",
        "supervisor_attr": "action_items_supervisor",
        "empty_draft": _EMPTY_ACTION_ITEMS,
        "reject_review": _REJECT_ACTION_ITEMS_REVIEW,
    },
    "minutes_generation": {
        "agent_attr": "minutes_generation_agent",
        "supervisor_attr": "minutes_generation_supervisor",
        "empty_draft": _EMPTY_MINUTES,
        "reject_review": _REJECT_MINUTES_REVIEW,
    },
}

# ── 任务线注册生成区结束 ──


def _line_cn(line_name: str) -> str:
    """线名 → 中文名（查共享注册表，未注册则回退英文线名）。"""
    return LINE_CN_NAMES.get(line_name, line_name)


def _line_draft_title(line_name: str) -> str:
    """线名 → 草稿标题（自动推导为「中文名草稿」）。"""
    return f"{_line_cn(line_name)}草稿"


def _normalize_templates(
    template: str,
    item_template: str,
    templates: dict[str, str] | None,
) -> dict[str, str]:
    """按线统一收纳输出模板：``templates`` 优先，便捷参数兜底。

    ``template`` → ``templates["minutes_generation"]``；
    ``item_template`` → ``templates["action_items"]``；
    两者同时传时以 ``templates`` 中的对应键为准。
    """
    result = dict(templates or {})
    if template and "minutes_generation" not in result:
        result["minutes_generation"] = template
    if item_template and "action_items" not in result:
        result["action_items"] = item_template
    return result


def _compute_title(state: MeetingState) -> str:
    """视角标题（通用规则：客观 → 客观会议纪要；个人 → 姓名视角会议纪要）。"""
    if bool(state.get("objective_perspective")):
        return "客观会议纪要"
    user = state.get("user") or {}
    return f"{user.get('name', '用户')}视角会议纪要"


def _assemble_report(
    state: MeetingState,
    warning: str | None,
    report_cls: type,
    line_name: str,
) -> object:
    """通用 Report 组装器：按字段 metadata["source"] 从 state 抽屉取值。

    source 约定：
    - ``title`` → 视角标题（_compute_title 通用计算）
    - ``rendered`` → lines[线名]["rendered"]（渲染正文/列表）
    - ``rendered_text`` → lines[线名]["rendered_text"]（模板文本）
    - ``draft.xxx`` → lines[线名]["draft"]["xxx"]（草稿字段）
    - 无 source → 不赋值（留给 dataclass default）
    - quality_warning 固定填 warning（降级状态）
    """
    data: dict = {}
    for f in fields(report_cls):
        src = f.metadata.get("source")
        if src is None:
            continue
        if src == "title":
            data[f.name] = _compute_title(state)
        elif src == "rendered":
            data[f.name] = _line(state, line_name).get("rendered")
        elif src == "rendered_text":
            data[f.name] = _line(state, line_name).get("rendered_text")
        elif src.startswith("draft."):
            draft = _line(state, line_name).get("draft") or {}
            data[f.name] = draft.get(src[len("draft."):])
    names = {f.name for f in fields(report_cls)}
    if "quality_warning" in names:
        data["quality_warning"] = warning
    return report_cls(**data)


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
            f"{_line_cn(line_name)}返工次数：{revision_count}/{self.MAX_REVISIONS}\n"
            f"{allowed}\n\n"
            f"会议原文（最高事实来源）：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"会议理解：\n{_json(state['meeting_understanding'])}\n\n"
            f"用户视角模型：\n{_json(state['perspective_profile'])}\n\n"
            f"{_line_draft_title(line_name)}：\n{_json(sub['draft'])}"
        )

    def _minutes_generation_render_context(
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
        try:
            result = await self.meeting_understanding_agent.run(
                state["transcript"]
            )
        except Exception as exc:
            logger.warning("会议理解失败，使用空理解继续", exc_info=True)
            return {
                "meeting_understanding": _EMPTY_MEETING_UNDERSTANDING,
                "quality_degraded": True,
            }
        return {"meeting_understanding": result.model_dump()}

    async def _perspective_modeling_node(
        self, state: MeetingState
    ) -> dict:
        try:
            result = await self.perspective_modeling_agent.run(
                state["transcript"],
                _json(state["user"]),
            )
        except Exception as exc:
            logger.warning("视角建模失败，使用空视角继续", exc_info=True)
            return {
                "perspective_profile": _EMPTY_PERSPECTIVE_MODELING,
                "quality_degraded": True,
            }
        return {"perspective_profile": result.model_dump()}

    # ── 同构节点工厂（由 TASK_LINES 注册表生成）───────────────

    def _make_agent_node(self, line_name: str):
        """生成某任务线的「生成/提取」节点（agent → 草稿）。"""
        cfg = TASK_LINES[line_name]

        async def node(state: MeetingState) -> dict:
            agent = getattr(self, cfg["agent_attr"])
            try:
                result = await agent.run(
                    self._revision_context(
                        self._shared_context(state),
                        _line(state, line_name).get("revision_feedback", []),
                        f"{_line_cn(line_name)}返工意见",
                    )
                )
            except Exception as exc:
                logger.warning(
                    f"{_line_cn(line_name)}生成失败，使用空草稿继续", exc_info=True
                )
                return {
                    "lines": {
                        line_name: {
                            "draft": cfg["empty_draft"],
                            "degraded": True,
                        }
                    },
                    "quality_degraded": True,
                }
            return {"lines": {line_name: {"draft": result.model_dump()}}}

        return node

    def _make_supervisor_node(self, line_name: str):
        """生成某任务线的「审核」节点（supervisor → approve/revise/reject）。"""
        cfg = TASK_LINES[line_name]

        async def node(state: MeetingState) -> dict:
            supervisor = getattr(self, cfg["supervisor_attr"])
            try:
                review = await supervisor.review(
                    self._supervisor_context(state, line_name)
                )
            except Exception as exc:
                logger.warning(
                    f"{_line_cn(line_name)}审核失败，按 reject 转降级", exc_info=True
                )
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
            updates = await agent_node(state)
            line_patch = updates.setdefault("lines", {}).setdefault(
                line_name, {}
            )
            line_patch["revision_count"] = (
                _line(state, line_name).get("revision_count", 0) + 1
            )
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

    # ── 专属节点方法生成区：由 tools/scripts/factory_contract.py 生成骨架，函数体可改 ──

    # ── 纪要线专属节点：渲染 + 降级 ───────────────────────────

    async def _minutes_generation_render_node(
        self, state: MeetingState
    ) -> dict:
        if state.get("streaming"):
            # 流式模式：图内不调用 LLM，由 run_streaming 接管流式输出
            return {"lines": {"minutes_generation": {"rendered": ""}}}
        try:
            minutes = await self.minutes_generation_render.run(
                self._minutes_generation_render_context(state, fallback=False),
                template=state.get("templates", {}).get(
                    "minutes_generation", ""
                ),
            )
        except Exception as exc:
            logger.warning("纪要渲染失败，使用确定性拼装", exc_info=True)
            minutes_report, _ = self._assemble_report_from_drafts(state)
            minutes = minutes_report.personalized_minutes
            return {
                "lines": {"minutes_generation": {"rendered": minutes}},
                "quality_degraded": True,
            }
        # 渲染本身成功不写 degraded（由 supervisor 判定或 fallback 标记）
        return {"lines": {"minutes_generation": {"rendered": minutes}}}

    async def _minutes_generation_fallback_node(
        self, state: MeetingState
    ) -> dict:
        """纪要线降级：先尝试 LLM 渲染，失败则确定性拼装。"""
        if state.get("streaming"):
            # 流式模式：图内不调用 LLM，由 run_streaming 接管降级输出
            return {
                "lines": {
                    "minutes_generation": {"rendered": "", "degraded": True}
                },
                "quality_degraded": True,
            }
        context = self._minutes_generation_render_context(state, fallback=True)
        try:
            minutes = await self.minutes_generation_render.run(
                context,
                template=state.get("templates", {}).get(
                    "minutes_generation", ""
                ),
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
        return {
            "lines": {
                "minutes_generation": {"rendered": minutes, "degraded": True}
            },
            "quality_degraded": True,
        }

    # ── 待办线专属节点：格式化 + 降级 ─────────────────────────

    async def _action_items_render_node(
        self, state: MeetingState
    ) -> dict:
        items = self.action_items_render.extract_actions(state)
        item_template = state.get("templates", {}).get(
            "action_items", ""
        )
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
                return {
                    "lines": {
                        "action_items": {
                            "rendered": items,
                            "degraded": True,
                        }
                    },
                    "quality_degraded": True,
                }
            return {
                "lines": {
                    "action_items": {"rendered": items, "rendered_text": text}
                }
            }
        return {"lines": {"action_items": {"rendered": items}}}

    async def _action_items_fallback_node(
        self, state: MeetingState
    ) -> dict:
        """待办线降级：确定性提取（不调 LLM）。"""
        items = self.action_items_render.extract_actions(state)
        return {
            "lines": {
                "action_items": {"rendered": items, "degraded": True}
            },
            "quality_degraded": True,
        }

    # ── 专属节点方法生成区结束 ──

    @staticmethod
    def _pack_fallback(
        line_names: list[str],
        minutes_fb: MinutesReport,
        actions_fb: ActionsReport,
    ) -> dict:
        """兜底路径按线过滤：只返回选中线的 Report（未选中的不输出）。"""
        reports: dict = {}
        if "minutes_generation" in line_names:
            reports["minutes"] = minutes_fb
        if "action_items" in line_names:
            reports["actions"] = actions_fb
        return reports

    async def _produce(
        self,
        line_name: str,
        state: MeetingState,
        queue: asyncio.Queue,
    ) -> None:
        """通用流式生产者：把指定任务线的文本流式塞进队列（并行事件源）。

        线 → 事件映射（注册表驱动）：
        - 输出键 ``output_key`` → 事件类型 ``{output_key}_chunk``（如 minutes_chunk）
        - ``emit_items=True`` 的线先发结构化列表事件 ``{output_key}``（如 actions）
        - render 实例按命名约定取 ``self.{line_name}_render``
        - 上下文方法按命名约定取 ``self._{line_name}_render_context``
        - render.stream 签名统一 ``(context, template="")``
        """
        output_key, _report_cls, emit_items = self._report_assemblers[line_name]
        render = getattr(self, f"{line_name}_render")
        event_type = f"{output_key}_chunk"
        degraded = bool(_line(state, line_name).get("degraded"))
        templates = state.get("templates", {}) or {}
        template = templates.get(line_name, "") or ""
        item_template = templates.get("action_items", "") or ""
        try:
            if emit_items:
                # 结构化列表事件（如待办）：程序消费 + 文本流式化
                items = _line(state, line_name).get("rendered") or []
                await queue.put({"type": output_key, "items": items})
                if item_template.strip() and not degraded:
                    async for chunk in render.stream_with_template(
                        state, item_template
                    ):
                        await queue.put({"type": event_type, "text": chunk})
                else:
                    for index, item in enumerate(items, start=1):
                        await queue.put(
                            {
                                "type": event_type,
                                "text": render.format_action(index, item)
                                + "\n",
                            }
                        )
                return
            if degraded:
                # 降级：确定性兜底文本一次性整段交付
                await queue.put(
                    {
                        "type": event_type,
                        "text": _line(state, line_name).get("rendered") or "",
                    }
                )
                return
            # 正常：调该线 Render 的 stream 流式渲染
            context_fn = getattr(self, f"_{line_name}_render_context")
            context = context_fn(state, fallback=False)
            async for chunk in render.stream(context, template):
                await queue.put({"type": event_type, "text": chunk})
        except Exception as exc:
            await queue.put(exc)  # 异常对象作为事件传出，由主循环抛出
        finally:
            await queue.put(None)


class MeetingAgentSystem(_Nodes):
    """使用 LangGraph 编排会议分析、双线并行审核返工与最终输出。"""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

        # 通过工厂组装全部 Agent 依赖（键名 = 属性名，与 TASK_LINES 的 *_attr 对齐）
        agents = MeetingAgentFactory.create(self.client)

        # core 层挂载（手写，生成区外——不属于任务线，脚本扫描不到）
        self.meeting_understanding_agent: MeetingUnderstandingAgent = agents[
            "meeting_understanding_agent"
        ]
        self.perspective_modeling_agent: PerspectiveModelingAgent = agents[
            "perspective_modeling_agent"
        ]

        # ── Agent 挂载生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──

        self.action_items_agent: ActionItemsAgent = agents["action_items_agent"]
        self.action_items_supervisor: ActionItemsSupervisor = agents["action_items_supervisor"]
        self.action_items_render: ActionItemsRender = agents["action_items_render"]
        self.minutes_generation_agent: MinutesGenerationAgent = agents["minutes_generation_agent"]
        self.minutes_generation_supervisor: MinutesGenerationSupervisor = agents["minutes_generation_supervisor"]
        self.minutes_generation_render: MinutesGenerationRender = agents["minutes_generation_render"]

        # ── Agent 挂载生成区结束 ──

        # 各线专属的渲染 / 降级节点（同构节点由注册表在 _build_graph 中生成）
        # ── 节点映射生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──

        self._render_nodes: dict[str, object] = {}
        self._render_nodes["action_items"] = self._action_items_render_node
        self._render_nodes["minutes_generation"] = self._minutes_generation_render_node
        self._fallback_nodes: dict[str, object] = {}
        self._fallback_nodes["action_items"] = self._action_items_fallback_node
        self._fallback_nodes["minutes_generation"] = self._minutes_generation_fallback_node

        # ── 节点映射生成区结束 ──

        # 各线 Report 组装器：线名 → (输出键, Report 类, emit_items)
        # emit_items=True 的线（如待办）先发结构化列表事件；其余仅文本流
        self._report_assemblers = {
            "minutes_generation": ("minutes", MinutesReport, False),
            "action_items": ("actions", ActionsReport, True),
        }

    # ── 图构建（注册表驱动，双线并行）─────────────────────────

    def _normalize_lines(
        self, lines: Iterable[str] | None
    ) -> list[str]:
        """规范化 lines 参数：None → 全部任务线；校验未知/空值。"""
        if lines is None:
            return list(TASK_LINES)
        result = list(lines)
        unknown = [name for name in result if name not in TASK_LINES]
        if unknown:
            raise ValueError(
                f"未知任务线 {unknown}，可用：{list(TASK_LINES)}"
            )
        if not result:
            raise ValueError("lines 不能为空，至少指定一条任务线")
        return result

    def _build_graph(
        self, line_names: Iterable[str] | None = None
    ) -> object:
        """构建 LangGraph：core（会议理解/视角建模）+ 指定任务线。

        ``line_names`` 为 None 时构建全部任务线；否则只构建选中的线
        （core 始终构建——任何任务线都需要会议理解与视角建模）。
        """
        line_names = self._normalize_lines(line_names)
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
        for line_name in line_names:
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
        templates: dict[str, str] | None = None,
        lines: Iterable[str] | None = None,
    ) -> dict[str, "MinutesReport | ActionsReport"]:
        """运行会议分析流水线，按线交付结果。

        ``lines`` 指定要执行的任务线（默认全部）：None 或省略 = 全部任务线；
        只传部分线名（如 ``["minutes_generation"]``）时，未选中的线完全跳过
        （不构建节点、不调用 LLM），对应键为空的 Report。

        ``templates`` 按线指定输出模板：``{线名: 模板文本}``（如
        ``{"minutes_generation": "【纪要】[描述]"}``）。便捷参数 ``template``
        等价于 ``templates["minutes_generation"]``，``item_template`` 等价于
        ``templates["action_items"]``，两者同时传时以 ``templates`` 为准。

        返回 dict（键 = 任务线名，值 = 该线的 Report）：
        - ``{"minutes": MinutesReport, "actions": ActionsReport}``
        - 只跑纪要：``{"minutes": MinutesReport}``
        - 只跑待办：``{"actions": ActionsReport}``

        纪要/待办两条线互不依赖、并行执行，需要哪条就跑哪条。
        """
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
        # 模板按线统一收纳（须在 initial_state 前）：templates 优先，便捷参数兜底
        templates = _normalize_templates(template, item_template, templates)

        initial_state: MeetingState = {
            "transcript": transcript,
            "user": user_data,
            "objective_perspective": objective_mode,
            "templates": templates,
        }
        # lines 校验放在 try 外：非法线名/空列表直接抛给调用方，不走兜底
        line_names = self._normalize_lines(lines)
        try:
            graph = self._build_graph(line_names)
            state = await graph.ainvoke(initial_state)
        except Exception as exc:
            # 最后防线：图内任何未接住的异常都不让运行崩溃，走确定性兜底
            logger.warning("图执行失败，使用确定性兜底输出", exc_info=True)
            minutes_fb, actions_fb = self._assemble_report_from_drafts(
                initial_state
            )
            minutes_fb.quality_warning = QUALITY_WARNING
            actions_fb.quality_warning = QUALITY_WARNING
            return self._pack_fallback(
                line_names, minutes_fb, actions_fb
            )

        # 从并行渲染结果按线组装 Report（通用组装器按字段 metadata 读取抽屉）
        quality_degraded = bool(state.get("quality_degraded"))
        warning = QUALITY_WARNING if quality_degraded else None
        reports: dict = {}
        for line_name in line_names:
            output_key, report_cls, _emit_items = self._report_assemblers[
                line_name
            ]
            reports[output_key] = _assemble_report(
                state, warning, report_cls, line_name
            )

        try:
            return {
                key: validate_payload(type(report), report.model_dump())
                for key, report in reports.items()
            }
        except Exception:
            logger.warning("输出校验失败，退回确定性兜底", exc_info=True)
            minutes_fb, actions_fb = self._assemble_report_from_drafts(state)
            minutes_fb.quality_warning = QUALITY_WARNING
            actions_fb.quality_warning = QUALITY_WARNING
            return self._pack_fallback(line_names, minutes_fb, actions_fb)

    # ── 流式并行输出 ─────────────────────────────────────────

    async def run_streaming(
        self,
        transcript: str,
        user: UserIdentity | None = None,
        template: str = "",
        item_template: str = "",
        templates: dict[str, str] | None = None,
        lines: Iterable[str] | None = None,
    ) -> AsyncIterator[dict]:
        """流式版本：纪要 LLM token 逐块推送、待办即时推送，两者并行互不等待。

        ``lines`` 指定要执行的任务线（默认全部）：只传部分线名时，
        未选中的线不构建节点、不调用 LLM，也不会产出对应事件。

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
        # 模板按线统一收纳（须在 initial_state 前）：templates 优先，便捷参数兜底
        templates = _normalize_templates(template, item_template, templates)

        initial_state: MeetingState = {
            "transcript": transcript,
            "user": user_data,
            "objective_perspective": objective_mode,
            "templates": templates,
            "streaming": True,  # 图内渲染节点跳过 LLM，由本方法接管流式输出
        }
        # lines 校验放在 try 外：非法线名/空列表直接抛给调用方，不走兜底
        line_names = self._normalize_lines(lines)
        minutes_in = "minutes_generation" in line_names
        actions_in = "action_items" in line_names
        try:
            graph = self._build_graph(line_names)
            state = await graph.ainvoke(initial_state)
        except Exception as exc:
            # 最后防线：图内任何未接住的异常都不让运行崩溃，走确定性兜底
            logger.warning("图执行失败，使用确定性兜底输出", exc_info=True)
            minutes_fb, actions_fb = self._assemble_report_from_drafts(
                initial_state
            )
            if minutes_in:
                yield {
                    "type": "minutes_chunk",
                    "text": minutes_fb.personalized_minutes,
                }
            if actions_in:
                yield {"type": "actions", "items": actions_fb.action_items}
            yield {"type": "done", "quality_warning": QUALITY_WARNING}
            return

        actions = _line(state, "action_items").get("rendered") or []
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

        # 并行启动各线事件源，通过队列合并：纪要流式生成期间待办已可交付
        queue: asyncio.Queue = asyncio.Queue()

        tasks = []
        for line_name in line_names:
            tasks.append(
                asyncio.create_task(self._produce(line_name, state, queue))
            )
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
