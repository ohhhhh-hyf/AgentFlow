"""LangGraph 工作流编排。

MeetingAgentSystem 负责：组装 Agent 依赖、构建多线并行 DAG、条件路由、启动运行。

架构（注册表驱动）：
- meeting_core：会议理解 + 视角建模（公共事实底座，先行并行执行）
- tasks/{线}：各任务线（生成 → 监督 → 返工闭环），互不阻塞
- 共享编排内核位于 ``tools/domain_engine.py``；渲染在 ``tools.runtime.render``。
  本文件只保留：sync_domain 管理的注册/挂载生成区、领域专属 core 节点、
  领域钩子覆写。render / fallback 由运行时一份函数生成，不再按线出样板。
"""
from __future__ import annotations

import logging

from langgraph.graph import START

from client import LLMClient
from perspective import PerspectiveModelingAgent
from .meeting_factory import MeetingAgentFactory
from .meeting_core import MeetingUnderstandingAgent
from .domain_config import LINE_CN_NAMES, LINE_KINDS

# 共享编排内核（领域无关）：纯函数 + DomainNodes 图节点 mixin
from tools.domain_engine import (
    DomainNodes,
    format_risk_item,
    json_dumps as _json,
    line as _line,
    line_cn as _engine_line_cn,
    line_draft_title as _engine_line_draft_title,
)
from tools.runtime.kinds import resolve_line_policies

# ── Report import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .reports import (
    ActionItemsReport,
    MindmapReport,
    MinutesReport,
    MinutesTraceReport,
    MultiStylesReport,
    RiskReport,
)
# ── Report import 生成区结束 ──

from .models import MeetingState
# ── 任务线 import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .tasks.actions import (
    ActionItemsAgent,
    ActionItemsRender,
    ActionItemsSupervisor,
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

from .tasks.minutes_trace import (
    MinutesTraceAgent,
    MinutesTraceRender,
    MinutesTraceSupervisor,
)

from .tasks.minutes_styles import (
    MultiStylesAgent,
    MultiStylesRender,
    MultiStylesSupervisor,
)

from .tasks.risks import (
    RiskAgent,
    RiskRender,
    RiskSupervisor,
)

# ── 任务线 import 生成区结束 ──

# ── FallbackRules import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .tasks.actions.contracts import ACTION_ITEMS_FALLBACK_RULES
from .tasks.mindmap.contracts import MINDMAP_FALLBACK_RULES
from .tasks.minutes.contracts import MINUTES_FALLBACK_RULES
from .tasks.minutes_trace.contracts import MINUTES_TRACE_FALLBACK_RULES
from .tasks.minutes_styles.contracts import MULTI_STYLES_FALLBACK_RULES
from .tasks.risks.contracts import RISK_FALLBACK_RULES

# ── FallbackRules import 生成区结束 ──

logger = logging.getLogger(__name__)

QUALITY_WARNING = "生成可能有误，请结合会议原文核对。"
QUALITY_DISCLAIMER = "（生成可能有误）"

# ── 空结构常量生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

_EMPTY_ACTION_ITEMS = {
    "my_actions": [],
    "delegated_actions": [],
    "unassigned_actions": [],
}

_EMPTY_MEETING_UNDERSTANDING = {
    "meeting_brief": "",
    "meeting_purpose": "",
    "scene": "通用",
    "topics": [],
    "decisions": [],
    "open_questions": [],
    "risks": [],
    "action_hints": [],
    "risk_hints": [],
    "dependencies": [],
}

_EMPTY_MINDMAP = {
    "title": "",
    "outline": "",
}

_EMPTY_MINUTES = {
    "headline": "",
    "executive_summary": [],
    "key_decisions": [],
    "personally_relevant_points": [],
    "risks_and_blockers": [],
    "unresolved_questions": [],
    "history_comparison": [],
}

_EMPTY_MINUTES_TRACE = {
    "scene": "通用",
    "minutes_md": "",
    "alignments": [],
}

_EMPTY_MULTI_STYLES = {
    "mode": "time",
    "title": "",
    "sections": [],
    "summary": "",
}

_EMPTY_RISK = {
    "risks": [],
}

# ── 空结构常量生成区结束 ──

# ── 拒绝审核常量生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

_REJECT_MINUTES_REVIEW = {
    "decision": "reject",
    "facts_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "perspective_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "consistency_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_ACTION_ITEMS_REVIEW = {
    "decision": "reject",
    "actions_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_RISK_REVIEW = {
    "decision": "reject",
    "risk_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_MINDMAP_REVIEW = {
    "decision": "reject",
    "mindmap_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_MULTI_STYLES_REVIEW = {
    "decision": "reject",
    "mode_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "facts_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "consistency_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_MINUTES_TRACE_REVIEW = {
    "decision": "reject",
    "facts_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "template_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "trace_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

# ── 拒绝审核常量生成区结束 ──

# ── 任务线注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

TASK_LINES: dict[str, dict] = {
    "actions": {
        "agent_attr": "actions_agent",
        "supervisor_attr": "actions_supervisor",
        "empty_draft": _EMPTY_ACTION_ITEMS,
        "reject_review": _REJECT_ACTION_ITEMS_REVIEW,
    },
    "mindmap": {
        "agent_attr": "mindmap_agent",
        "supervisor_attr": "mindmap_supervisor",
        "empty_draft": _EMPTY_MINDMAP,
        "reject_review": _REJECT_MINDMAP_REVIEW,
    },
    "minutes": {
        "agent_attr": "minutes_agent",
        "supervisor_attr": "minutes_supervisor",
        "empty_draft": _EMPTY_MINUTES,
        "reject_review": _REJECT_MINUTES_REVIEW,
    },
    "minutes_trace": {
        "agent_attr": "minutes_trace_agent",
        "supervisor_attr": "minutes_trace_supervisor",
        "empty_draft": _EMPTY_MINUTES_TRACE,
        "reject_review": _REJECT_MINUTES_TRACE_REVIEW,
    },
    "minutes_styles": {
        "agent_attr": "minutes_styles_agent",
        "supervisor_attr": "minutes_styles_supervisor",
        "empty_draft": _EMPTY_MULTI_STYLES,
        "reject_review": _REJECT_MULTI_STYLES_REVIEW,
    },
    "risks": {
        "agent_attr": "risk_agent",
        "supervisor_attr": "risk_supervisor",
        "empty_draft": _EMPTY_RISK,
        "reject_review": _REJECT_RISK_REVIEW,
    },
}

# ── 任务线注册生成区结束 ──

def _line_cn(line_name: str) -> str:
    """线名 → 中文名（查共享注册表，未注册则回退英文线名）。"""
    return _engine_line_cn(line_name, LINE_CN_NAMES)

def _line_draft_title(line_name: str) -> str:
    """线名 → 草稿标题（自动推导为「中文名草稿」）。"""
    return _engine_line_draft_title(line_name, LINE_CN_NAMES)

def _format_minutes_styles_section(index: int, item: dict) -> str:
    """把多样式纪要的一个组织段落格式化为文本行（确定性降级输出用）。"""
    title = str(item.get("title") or "").strip()
    content = str(item.get("content") or "").strip()
    if title:
        return f"{title}：{content}" if content else title
    return content

# Lines 段逐条格式化器注册表（线名 → 格式化函数(index, item) -> str）
# actions / risks / minutes_styles 的降级输出格式与各自 LLM 渲染 prompt 保持一致
_LINES_FORMATTERS: dict[str, object] = {
    "actions": ActionItemsRender.format_action,
    "risks": format_risk_item,
    "minutes_styles": _format_minutes_styles_section,
}

# 理解层按线裁剪：单线运行时跳过的字段（输出 []，字段契约与下游读取不变）。
# 多线并行共享理解时保持全量，裁剪只在单线场景生效（避免一条线白付其它线字段）。
UNDERSTANDING_SKIP_FIELDS: dict[str, frozenset[str]] = {
    "actions": frozenset({"topics", "risks", "open_questions", "risk_hints"}),
    "risks": frozenset({"topics", "action_hints"}),
    "minutes": frozenset({"risk_hints"}),
}

def _empty_purpose(state) -> str:
    """empty_purpose 兜底时的「目的」文案（会议理解的目的）。"""
    purpose = (state.get("meeting_understanding") or {}).get(
        "meeting_purpose"
    ) or ""
    return f"会议目的：{purpose}" if purpose else ""

class _Nodes(DomainNodes):
    """meeting 图节点实现：共享内核 + 领域专属钩子与会议理解节点。"""

    _fallback_formatters = _LINES_FORMATTERS
    _quality_disclaimer = QUALITY_DISCLAIMER
    _understanding_key = "meeting_understanding"
    _understanding_label = "已审核会议理解"
    _transcript_label = "会议原文"
    _line_cn_names = LINE_CN_NAMES
    _line_policies = resolve_line_policies(LINE_KINDS)

    # 理解层参与审核摘录的字段白名单（线名 → 保留字段）。
    # 该线不消费的字段不进原文摘录，命中点从遍布全文收敛到相关段落；
    # 未列出的线（minutes_styles / mindmap 等）走默认全字段。
    _understanding_needle_keep: dict[str, frozenset[str]] = {
        "actions": frozenset({
            "meeting_brief", "meeting_purpose", "scene", "decisions",
            "action_hints", "dependencies",
        }),
        "risks": frozenset({
            "meeting_brief", "meeting_purpose", "scene", "risks",
            "open_questions", "risk_hints", "dependencies",
        }),
        "minutes": frozenset({
            "meeting_brief", "meeting_purpose", "scene", "topics",
            "decisions", "risks", "open_questions", "dependencies",
        }),
        "minutes_trace": frozenset({
            "meeting_brief", "meeting_purpose", "scene", "topics",
            "decisions", "risks", "open_questions", "dependencies",
        }),
    }

    def _understanding_needle_fields(self, line_name: str) -> set[str] | None:
        """审核摘录时理解层的 needle 字段白名单（与按线裁剪同源）。"""
        keep = self._understanding_needle_keep.get(line_name)
        return set(keep) if keep else None

    # ── 领域钩子：视角标题 / 展示标题 ─────────────────────────

    def _compute_title(self, state) -> str:
        """标题：优先用纪要草稿的 headline（根据会议内容总结的主题标题），回退视角标题。"""
        try:
            draft = _line(state, "minutes").get("draft") or {}
            headline = str(draft.get("headline") or "").strip()
            if headline:
                return headline
        except Exception:  # noqa: BLE001 - 取 headline 失败回退视角标题
            pass
        if bool(state.get("objective_perspective")):
            return "客观会议纪要"
        user = state.get("user") or {}
        return f"{user.get('name', '用户')}视角会议纪要"

    def _line_title(self, state, line_name: str) -> str:
        """线 → 展示标题（按视角模式区分；新线用通用默认）。"""
        objective = bool(state.get("objective_perspective"))
        user = state.get("user") or {}
        name = user.get("name") or "用户"
        if line_name == "minutes":
            return "客观会议纪要" if objective else f"{name}视角会议纪要"
        if line_name == "actions":
            return "客观待办事项（全员）" if objective else "待办事项"
        return f"{_line_cn(line_name)}输出"

    def _empty_purpose(self, state) -> str:
        return _empty_purpose(state)

    # ── 领域钩子：共享上下文（含会议理解）──────────────────────

    def _shared_context(self, state) -> str:
        """agent 共享上下文（视角模式 + 画像 + 会议理解 + 视角模型 + 原文）。"""
        mode = self._mode_label(state)
        return (
            f"视角模式：{mode}\n"
            f"说明：objective=客观全员；role_template=职业模板（name 是职业名，不是会场真人）；"
            f"personal=真人个人（name 是真实姓名）。"
            f"裁剪时同时遵守画像 focus_areas / interests / principles / constraints / output_style。"
            f"职业/真人对决策、风险、未决从上游下采（只删不改），关注域内的数字、时限、承诺、口径、范围边界不得省略。\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"会议理解：\n{_json(state['meeting_understanding'])}\n\n"
            f"用户视角模型：\n{_json(state.get('perspective_profile') or {})}\n\n"
            f"会议原文：\n{state['transcript']}"
        )

    @staticmethod
    def _compact_user(user: dict) -> dict:
        """给任务 Agent 的瘦身画像，只保留会影响视角裁剪的字段。"""
        keys = (
            "name",
            "role",
            "department",
            "perspective",
            "persona_type",
            "responsibilities",
            "interests",
            "focus_areas",
            "constraints",
            "output_style",
        )
        return {key: user.get(key) for key in keys if user.get(key)}

    @staticmethod
    def _compact_perspective(profile: dict | None) -> dict:
        """视角模型瘦身：保留与任务相关性判断有关的字段。"""
        if not isinstance(profile, dict):
            return {}
        keys = (
            "personal_summary",
            "attention_points",
            "responsibilities",
            "goals",
            "concerns",
            "relevant_topics",
            "evidence",
        )
        return {key: profile.get(key) for key in keys if profile.get(key)}

    @staticmethod
    def _topic_brief(topic: dict) -> dict:
        title = str(topic.get("title") or "").strip()
        conclusion = topic.get("conclusion")
        discussion = str(topic.get("discussion") or "").strip()
        # 兼容未来 key_points 字段；当前模型仍可能只有 discussion。
        key_points = topic.get("key_points")
        if not isinstance(key_points, list):
            key_points = []
        if discussion and not key_points:
            key_points = [discussion[:500]]
        return {
            "title": title,
            "key_points": key_points[:6],
            "conclusion": conclusion,
            "participants": topic.get("participants") or [],
        }

    def _meeting_pack(self, state: dict, line_name: str) -> dict:
        """为每条任务线构造最小必要会议理解包，减少重复上下文。"""
        u = state.get("meeting_understanding") or {}
        topics = [
            self._topic_brief(item)
            for item in (u.get("topics") or [])
            if isinstance(item, dict)
        ]
        base = {
            "meeting_brief": u.get("meeting_brief") or u.get("meeting_purpose") or "",
            "meeting_purpose": u.get("meeting_purpose") or "",
            "scene": u.get("scene") or "通用",
        }
        if line_name == "actions":
            directive_decisions = [
                item for item in (u.get("decisions") or [])
                if any(word in str(item) for word in ("要求", "必须", "务必", "请", "需", "整改", "落实"))
            ]
            return {
                **base,
                "action_hints": u.get("action_hints") or [],
                "directive_decisions": directive_decisions,
                "dependencies": u.get("dependencies") or [],
            }
        if line_name == "risks":
            return {
                **base,
                "risk_hints": u.get("risk_hints") or [],
                "risks": u.get("risks") or [],
                "dependencies": u.get("dependencies") or [],
                "risk_related_open_questions": u.get("open_questions") or [],
            }
        if line_name == "minutes_trace":
            return {
                **base,
                "topics": topics,
                "decisions": u.get("decisions") or [],
                "risks": u.get("risks") or [],
                "open_questions": u.get("open_questions") or [],
                "dependencies": u.get("dependencies") or [],
            }
        if line_name == "minutes_styles":
            # 多样式纪要重写全文(上下文另有完整原文),pack 只给理解摘要;
            # 不需要 action_hints/risk_hints(那是待办/风险线的线索)
            return {
                **base,
                "topics": topics,
                "decisions": u.get("decisions") or [],
                "risks": u.get("risks") or [],
                "open_questions": u.get("open_questions") or [],
                "dependencies": u.get("dependencies") or [],
            }
        if line_name == "minutes":
            return {
                **base,
                "topics": topics,
                "decisions": u.get("decisions") or [],
                "risks": u.get("risks") or [],
                "open_questions": u.get("open_questions") or [],
                "key_action_hints": (u.get("action_hints") or [])[:12],
            }
        return {
            **base,
            "topics": topics,
            "decisions": u.get("decisions") or [],
            "risks": u.get("risks") or [],
            "open_questions": u.get("open_questions") or [],
            "action_hints": u.get("action_hints") or [],
            "risk_hints": u.get("risk_hints") or [],
            "dependencies": u.get("dependencies") or [],
        }

    def _line_shared_context(self, state: dict, line_name: str) -> str:
        """按任务线裁剪后的 Agent 上下文。

        仍保留「会议理解」标签，兼容 minutes 的硬执行对齐。
        """
        mode = self._mode_label(state)
        pack = self._meeting_pack(state, line_name)
        parts = [
            f"视角模式：{mode}",
            "说明：仅使用本任务上下文包中的事实；需要裁剪视角时参考用户画像和用户视角模型。"
            "不要从未提供的完整原文中补造事实。",
            f"用户画像：\n{_json(self._compact_user(state.get('user') or {}))}",
            f"会议理解：\n{_json(pack)}",
        ]
        perspective = self._compact_perspective(state.get("perspective_profile") or {})
        if perspective:
            parts.append(f"用户视角模型：\n{_json(perspective)}")
        # 溯源纪要和多样式纪要仍需要较强的原文/场景依据；其它线优先依赖 evidence。
        if line_name in {"minutes_trace", "minutes_styles", "mindmap"}:
            parts.append(f"会议原文：\n{state.get('transcript') or ''}")
        return "\n\n".join(parts)

    def _make_agent_node(self, line_name: str):
        """会议域生成节点：给不同任务线注入专属瘦身上下文。"""
        cfg = self._task_lines[line_name]
        cn = _line_cn(line_name)

        async def node(state: dict) -> dict:
            agent = getattr(self, cfg["agent_attr"])
            context = self._line_shared_context(state, line_name)
            mode = (state.get("line_modes") or {}).get(line_name)
            if mode and self._line_policy(line_name).cli_mode:
                context = f"组织模式：{mode}\n\n{context}"
            extra = (state.get("line_extra") or {}).get(line_name)
            if extra:
                context = f"{context}\n\n{extra}"
            try:
                result = await agent.run(
                    self._revision_context(
                        context,
                        _line(state, line_name).get("revision_feedback", []),
                        f"{cn}返工意见",
                    )
                )
            except Exception:  # noqa: BLE001 - 有意的降级设计
                logger.warning(f"{cn}生成失败，使用空草稿继续", exc_info=True)
                return {
                    "lines": {
                        line_name: {
                            "draft": cfg["empty_draft"],
                            "degraded": True,
                        }
                    },
                    "quality_degraded": True,
                }
            return {
                "lines": {
                    line_name: {
                        "draft": result.model_dump(),
                        "degraded": False,
                    }
                }
            }

        return node

    def _supervisor_context(self, state, line_name: str) -> str:
        """审核上下文：原文按草稿事实点摘录，理解只给摘要。"""
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
            f"{self._supervisor_source_pack(state, line_name)}\n\n"
            f"{_line_draft_title(line_name)}：\n{_json(sub['draft'])}"
        )

    def _render_context(self, state: dict, line_name: str) -> str:
        """会议域渲染上下文：默认不给完整原文，避免渲染阶段重复吃大输入。"""
        from tools.runtime.context import build_render_context

        sub = _line(state, line_name)
        extra = (state.get("line_extra") or {}).get(line_name) or ""
        blocks: list[tuple[str, object, str]] = [
            ("用户画像", self._compact_user(state.get("user") or {}), "json"),
            ("会议理解", self._meeting_pack(state, line_name), "json"),
        ]
        perspective = self._compact_perspective(state.get("perspective_profile") or {})
        if perspective:
            blocks.append(("已审核用户视角", perspective, "json"))
        if line_name in {"minutes_trace", "minutes_styles", "mindmap"}:
            blocks.insert(0, ("会议原文", state.get("transcript") or "", "raw"))
        return build_render_context(
            mode=self._mode_label(state),
            objective=bool(state.get("objective_perspective")),
            blocks=blocks,
            draft=sub.get("draft"),
            review=sub.get("review") or {},
            line_cn=_line_cn(line_name),
            extra=extra,
            dumps=_json,
        )

    # ── 领域钩子：core 节点 ───────────────────────────────────

    def _build_core(self, builder, line_names=None) -> list[str]:
        """核心层：会议理解（所有线都需要）+ 视角建模（按线按需）。

        minutes_trace 是 deterministic 溯源线，不消费视角 → 跳过视角建模
        （省一次 LLM 调用 + 省大输入 token）。
        """
        builder.add_node(
            "meeting_understanding",
            self._make_meeting_understanding_node(line_names),
        )
        builder.add_edge(START, "meeting_understanding")
        cores = ["meeting_understanding"]
        selected = [name for name in (line_names or []) if name]
        skip_perspective = frozenset({"minutes_trace"})
        need_perspective = (not selected) or any(
            name not in skip_perspective for name in selected
        )
        if need_perspective:
            builder.add_node(
                "perspective_modeling", self._perspective_modeling_node
            )
            builder.add_edge(START, "perspective_modeling")
            cores.append("perspective_modeling")
        return cores

    # ── 核心节点：会议理解（公共事实底座）──────────────────────

    async def _perspective_modeling_node(self, state: dict) -> dict:
        """客观全员模式跳过视角建模，省一次核心 LLM 调用。"""
        if bool(state.get("objective_perspective")):
            from perspective import EMPTY_PERSPECTIVE_MODELING

            return {"perspective_profile": EMPTY_PERSPECTIVE_MODELING}
        return await super()._perspective_modeling_node(state)

    def _understanding_skip(self, line_names) -> frozenset[str]:
        """单线运行时的理解输出裁剪集合；多线 / 未注册线保持全量。"""
        selected = [name for name in (line_names or []) if name]
        if len(selected) == 1 and selected[0] in UNDERSTANDING_SKIP_FIELDS:
            return UNDERSTANDING_SKIP_FIELDS[selected[0]]
        return frozenset()

    def _make_meeting_understanding_node(self, line_names):
        """会议理解节点：按本次选线裁剪输出（单线 API 场景省输出 token）。

        裁剪只影响理解层输出（跳过字段为 []），不改变字段契约，
        下游 pack / 审核 / 记忆读取逻辑零改动。
        """
        skip = self._understanding_skip(line_names)
        selected = [name for name in (line_names or []) if name]
        focus = selected[0] if (skip and selected) else ""

        async def node(state: dict) -> dict:
            try:
                result = await self.meeting_understanding_agent.run(
                    state["transcript"],
                    focus_line=focus,
                    skip_fields=skip,
                )
            except Exception:
                logger.warning("会议理解失败，使用空理解继续", exc_info=True)
                return {
                    "meeting_understanding": _EMPTY_MEETING_UNDERSTANDING,
                    "quality_degraded": True,
                }
            return {"meeting_understanding": result.model_dump()}

        return node

class MeetingAgentSystem(_Nodes):
    """使用 LangGraph 编排会议分析、多线并行审核返工与最终输出。"""

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

        # ── Agent 挂载生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self.actions_agent: ActionItemsAgent = agents["actions_agent"]
        self.actions_supervisor: ActionItemsSupervisor = agents["actions_supervisor"]
        self.actions_render: ActionItemsRender = agents["actions_render"]
        self.mindmap_agent: MindmapAgent = agents["mindmap_agent"]
        self.mindmap_supervisor: MindmapSupervisor = agents["mindmap_supervisor"]
        self.mindmap_render: MindmapRender = agents["mindmap_render"]
        self.minutes_agent: MinutesGenerationAgent = agents["minutes_agent"]
        self.minutes_supervisor: MinutesGenerationSupervisor = agents["minutes_supervisor"]
        self.minutes_render: MinutesGenerationRender = agents["minutes_render"]
        self.minutes_trace_agent: MinutesTraceAgent = agents["minutes_trace_agent"]
        self.minutes_trace_supervisor: MinutesTraceSupervisor = agents["minutes_trace_supervisor"]
        self.minutes_trace_render: MinutesTraceRender = agents["minutes_trace_render"]
        self.minutes_styles_agent: MultiStylesAgent = agents["minutes_styles_agent"]
        self.minutes_styles_supervisor: MultiStylesSupervisor = agents["minutes_styles_supervisor"]
        self.minutes_styles_render: MultiStylesRender = agents["minutes_styles_render"]
        self.risk_agent: RiskAgent = agents["risk_agent"]
        self.risk_supervisor: RiskSupervisor = agents["risk_supervisor"]
        self.risk_render: RiskRender = agents["risk_render"]

        # ── Agent 挂载生成区结束 ──

        # 兼容别名：线名 risks（复数）与属性 risk_*（单数）的历史映射，
        # 引擎按 f"{line_name}_render" 取值，需与线名对齐
        self.risks_agent = self.risk_agent
        self.risks_supervisor = self.risk_supervisor
        self.risks_render = self.risk_render

        # 各线 Report 组装器：线名 → Report 类（脚本生成，键 = 线名与 chunk.line 一致）
        # ── Report 组装器生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._report_assemblers = {
            "actions": ActionItemsReport,
            "mindmap": MindmapReport,
            "minutes": MinutesReport,
            "minutes_trace": MinutesTraceReport,
            "minutes_styles": MultiStylesReport,
            "risks": RiskReport,
        }

        # ── Report 组装器生成区结束 ──

        # 各线降级规则：线名 → FallbackRules 实例（脚本生成，图异常兜底用）
        # ── FallbackRules 注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._fallback_rules = {
            "actions": ACTION_ITEMS_FALLBACK_RULES,
            "mindmap": MINDMAP_FALLBACK_RULES,
            "minutes": MINUTES_FALLBACK_RULES,
            "minutes_trace": MINUTES_TRACE_FALLBACK_RULES,
            "minutes_styles": MULTI_STYLES_FALLBACK_RULES,
            "risks": RISK_FALLBACK_RULES,
        }

        # ── FallbackRules 注册生成区结束 ──

        # 共享编排内核所需实例属性（引擎通过 self 读取；值来自领域注册表）
        self._task_lines = TASK_LINES
        self._line_cn_names = LINE_CN_NAMES
        self._state_class = MeetingState
        self._quality_warning = QUALITY_WARNING

