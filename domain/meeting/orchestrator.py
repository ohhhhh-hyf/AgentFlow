"""LangGraph 工作流编排。

MeetingAgentSystem 负责：组装 Agent 依赖、构建多线并行 DAG、条件路由、启动运行。

架构（注册表驱动）：
- meeting_core：会议理解 + 视角建模（公共事实底座，先行并行执行）
- tasks/{线}：各任务线（生成 → 监督 → 渲染/返工闭环），互不阻塞
- 共享编排内核位于 ``tools/domain_engine.py``（DomainNodes mixin + 纯函数）；
  本文件只保留：sync_domain.py 管理的生成区、领域专属 core 节点、
  领域钩子覆写（上下文文案 / 标题 / core / render 特判 / 降级绑定）。
- 每条任务线的同构节点（agent / supervisor / revision / route）由 ``TASK_LINES``
  注册表自动生成；render / fallback 为各线专属实现。
  新增任务线：写 agent/supervisor/render 三个类 + prompts，在 ``TASK_LINES``
  注册一行即可，state（MeetingState.lines）与节点逻辑零改动。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable

from langgraph.graph import START

from llm_client import LLMClient
from perspective import PerspectiveModelingAgent
from .meeting_factory import MeetingAgentFactory
from .meeting_core import MeetingUnderstandingAgent
from .domain_config import LINE_CN_NAMES

# 共享编排内核（领域无关）：纯函数 + DomainNodes 图节点 mixin
from tools.domain_engine import (
    DomainNodes,
    format_risk_item,
    json_dumps as _json,
    line as _line,
    line_cn as _engine_line_cn,
    line_draft_title as _engine_line_draft_title,
    make_fallback_text,
)

# ── Report import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .reports import (
    ActionItemsReport,
    MindmapReport,
    MinutesReport,
    MultiStylesReport,
    RiskReport,
)
# ── Report import 生成区结束 ──

from .models import (
    MeetingState,
    UserIdentity,
    is_objective_perspective,
)
# ── 任务线 import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .tasks.action_items import (
    ActionItemsAgent,
    ActionItemsRender,
    ActionItemsSupervisor,
)

from .tasks.mindmap import (
    MindmapAgent,
    MindmapRender,
    MindmapSupervisor,
)

from .tasks.minutes_generation import (
    MinutesGenerationAgent,
    MinutesGenerationRender,
    MinutesGenerationSupervisor,
)

from .tasks.multi_styles import (
    MultiStylesAgent,
    MultiStylesRender,
    MultiStylesSupervisor,
)

from .tasks.risk import (
    RiskAgent,
    RiskRender,
    RiskSupervisor,
)

# ── 任务线 import 生成区结束 ──

# ── FallbackRules import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .tasks.action_items.contracts import ACTION_ITEMS_FALLBACK_RULES
from .tasks.mindmap.contracts import MINDMAP_FALLBACK_RULES
from .tasks.minutes_generation.contracts import MINUTES_FALLBACK_RULES
from .tasks.multi_styles.contracts import MULTI_STYLES_FALLBACK_RULES
from .tasks.risk.contracts import RISK_FALLBACK_RULES

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
    "meeting_purpose": "",
    "topics": [],
    "decisions": [],
    "open_questions": [],
    "risks": [],
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
    "action_items_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
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


# ── 拒绝审核常量生成区结束 ──

# ── 任务线注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

TASK_LINES: dict[str, dict] = {
    "action_items": {
        "agent_attr": "action_items_agent",
        "supervisor_attr": "action_items_supervisor",
        "empty_draft": _EMPTY_ACTION_ITEMS,
        "reject_review": _REJECT_ACTION_ITEMS_REVIEW,
    },
    "mindmap": {
        "agent_attr": "mindmap_agent",
        "supervisor_attr": "mindmap_supervisor",
        "empty_draft": _EMPTY_MINDMAP,
        "reject_review": _REJECT_MINDMAP_REVIEW,
    },
    "minutes_generation": {
        "agent_attr": "minutes_generation_agent",
        "supervisor_attr": "minutes_generation_supervisor",
        "empty_draft": _EMPTY_MINUTES,
        "reject_review": _REJECT_MINUTES_REVIEW,
    },
    "multi_styles": {
        "agent_attr": "multi_styles_agent",
        "supervisor_attr": "multi_styles_supervisor",
        "empty_draft": _EMPTY_MULTI_STYLES,
        "reject_review": _REJECT_MULTI_STYLES_REVIEW,
    },
    "risk": {
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

def _format_multi_styles_section(index: int, item: dict) -> str:
    """把多样式纪要的一个组织段落格式化为文本行（确定性降级输出用）。"""
    title = str(item.get("title") or "").strip()
    content = str(item.get("content") or "").strip()
    if title:
        return f"{title}：{content}" if content else title
    return content

# Lines 段逐条格式化器注册表（线名 → 格式化函数(index, item) -> str）
# action_items / risk / multi_styles 的降级输出格式与各自 LLM 渲染 prompt 保持一致
_LINES_FORMATTERS: dict[str, object] = {
    "action_items": ActionItemsRender.format_action,
    "risk": format_risk_item,
    "multi_styles": _format_multi_styles_section,
}

def _empty_purpose(state) -> str:
    """empty_purpose 兜底时的「目的」文案（会议理解的目的）。"""
    purpose = (state.get("meeting_understanding") or {}).get(
        "meeting_purpose"
    ) or ""
    return f"会议目的：{purpose}" if purpose else ""

# 生成区骨架引用的模块级 _fallback_text（3 参版本，绑定领域 formatters）
_fallback_text = make_fallback_text(
    _LINES_FORMATTERS, _empty_purpose, QUALITY_DISCLAIMER
)

class _Nodes(DomainNodes):
    """meeting 图节点实现：共享内核（tools/domain_engine.DomainNodes）+ 领域专属。

    同构节点（agent / supervisor / revision / route）与流式生产 / 图构建 /
    运行由引擎提供；本类只保留领域钩子覆写与领域专属节点（会议理解）。
    专属节点方法生成区（fallback 节点）与渲染上下文生成区由
    sync_domain.py 管理。
    """

    # 领域钩子：降级文本绑定（引擎 _domain_fallback_text 读取）
    _fallback_formatters = _LINES_FORMATTERS
    _quality_disclaimer = QUALITY_DISCLAIMER

    # ── 领域钩子：视角标题 / 展示标题 ─────────────────────────

    def _compute_title(self, state) -> str:
        """视角标题（客观 → 客观会议纪要；个人 → 姓名视角会议纪要）。"""
        if bool(state.get("objective_perspective")):
            return "客观会议纪要"
        user = state.get("user") or {}
        return f"{user.get('name', '用户')}视角会议纪要"

    def _line_title(self, state, line_name: str) -> str:
        """线 → 展示标题（按视角模式区分；新线用通用默认）。"""
        objective = bool(state.get("objective_perspective"))
        user = state.get("user") or {}
        name = user.get("name") or "用户"
        if line_name == "minutes_generation":
            return "客观会议纪要" if objective else f"{name}视角会议纪要"
        if line_name == "action_items":
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
            f"说明：perspective=objective 时为客观全员口径；"
            f"缺省或其它值为个人用户口径。\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"会议理解：\n{_json(state['meeting_understanding'])}\n\n"
            f"用户视角模型：\n{_json(state['perspective_profile'])}\n\n"
            f"会议原文：\n{state['transcript']}"
        )

    def _supervisor_context(self, state, line_name: str) -> str:
        """审核上下文（会议原文为最高事实来源，含会议理解）。"""
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

    # ── 领域钩子：core 节点 ───────────────────────────────────

    def _build_core(self, builder) -> list[str]:
        """核心层：会议理解 + 视角建模（并行，任何任务线都需要）。"""
        builder.add_node(
            "meeting_understanding", self._meeting_understanding_node
        )
        builder.add_node(
            "perspective_modeling", self._perspective_modeling_node
        )
        builder.add_edge(START, "meeting_understanding")
        builder.add_edge(START, "perspective_modeling")
        return ["meeting_understanding", "perspective_modeling"]

    # ── 领域钩子：render 后特判 ───────────────────────────────

    def _post_render_hook(self, state, line_name: str) -> None:
        """render 后写回结构化列表：待办线用 extract_actions，其余走通用提取。"""
        if line_name == "action_items":
            _line(state, line_name)["structure"] = (
                self.action_items_render.extract_actions(state)
            )
            return
        super()._post_render_hook(state, line_name)

    # ── 核心节点：会议理解（公共事实底座）──────────────────────

    async def _meeting_understanding_node(self, state) -> dict:
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

    # ── 渲染上下文生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

    def _action_items_render_context(self, state: MeetingState) -> str:
        mode = self._mode_label(state)
        line = _line(state, "action_items")
        review = line.get("review") or {}
        return (
            f"视角模式：{mode}\n"
            f"objective_perspective：{bool(state.get('objective_perspective'))}\n\n"
            f"会议原文：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"已审核会议理解：\n{_json(state.get('meeting_understanding'))}\n\n"
            f"已审核用户视角：\n{_json(state.get('perspective_profile'))}\n\n"
            f"已批准待办草稿：\n{_json(line.get('draft'))}\n\n"
            f"待办审核结论：\n{_json(review)}"
        )

    def _mindmap_render_context(self, state: MeetingState) -> str:
        mode = self._mode_label(state)
        line = _line(state, "mindmap")
        review = line.get("review") or {}
        return (
            f"视角模式：{mode}\n"
            f"objective_perspective：{bool(state.get('objective_perspective'))}\n\n"
            f"会议原文：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"已审核会议理解：\n{_json(state.get('meeting_understanding'))}\n\n"
            f"已审核用户视角：\n{_json(state.get('perspective_profile'))}\n\n"
            f"已批准思维导图草稿：\n{_json(line.get('draft'))}\n\n"
            f"思维导图审核结论：\n{_json(review)}"
        )

    def _minutes_generation_render_context(self, state: MeetingState) -> str:
        mode = self._mode_label(state)
        line = _line(state, "minutes_generation")
        review = line.get("review") or {}
        return (
            f"视角模式：{mode}\n"
            f"objective_perspective：{bool(state.get('objective_perspective'))}\n\n"
            f"会议原文：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"已审核会议理解：\n{_json(state.get('meeting_understanding'))}\n\n"
            f"已审核用户视角：\n{_json(state.get('perspective_profile'))}\n\n"
            f"已批准纪要草稿：\n{_json(line.get('draft'))}\n\n"
            f"纪要审核结论：\n{_json(review)}"
        )

    def _multi_styles_render_context(self, state: MeetingState) -> str:
        mode = self._mode_label(state)
        line = _line(state, "multi_styles")
        review = line.get("review") or {}
        return (
            f"视角模式：{mode}\n"
            f"objective_perspective：{bool(state.get('objective_perspective'))}\n\n"
            f"会议原文：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"已审核会议理解：\n{_json(state.get('meeting_understanding'))}\n\n"
            f"已审核用户视角：\n{_json(state.get('perspective_profile'))}\n\n"
            f"已批准多样式纪要草稿：\n{_json(line.get('draft'))}\n\n"
            f"多样式纪要审核结论：\n{_json(review)}"
        )

    def _risk_render_context(self, state: MeetingState) -> str:
        mode = self._mode_label(state)
        line = _line(state, "risk")
        review = line.get("review") or {}
        return (
            f"视角模式：{mode}\n"
            f"objective_perspective：{bool(state.get('objective_perspective'))}\n\n"
            f"会议原文：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"已审核会议理解：\n{_json(state.get('meeting_understanding'))}\n\n"
            f"已审核用户视角：\n{_json(state.get('perspective_profile'))}\n\n"
            f"已批准风险分析草稿：\n{_json(line.get('draft'))}\n\n"
            f"风险分析审核结论：\n{_json(review)}"
        )

    # ── 渲染上下文生成区结束 ──

    # ── 专属节点方法生成区：由 tools/scripts/sync_domain.py 生成骨架，函数体可改 ──

    # ── 纪要线专属节点：降级 ──────────────────────────────────

    # ── 待办线专属节点：降级 ──────────────────────────────────

    async def _action_items_fallback_node(self, state: MeetingState) -> dict:
        text, structure = _fallback_text(
            state, "action_items", ACTION_ITEMS_FALLBACK_RULES)
        line_dict = {"rendered": text, "degraded": True}
        if structure is not None:
            line_dict["structure"] = structure
        return {"lines": {"action_items": line_dict}, "quality_degraded": True}

    async def _minutes_generation_fallback_node(self, state: MeetingState) -> dict:
        text, structure = _fallback_text(
            state, "minutes_generation", MINUTES_FALLBACK_RULES)
        line_dict = {"rendered": text, "degraded": True}
        if structure is not None:
            line_dict["structure"] = structure
        return {"lines": {"minutes_generation": line_dict}, "quality_degraded": True}

    async def _risk_fallback_node(self, state: MeetingState) -> dict:
        text, structure = _fallback_text(
            state, "risk", RISK_FALLBACK_RULES)
        line_dict = {"rendered": text, "degraded": True}
        if structure is not None:
            line_dict["structure"] = structure
        return {"lines": {"risk": line_dict}, "quality_degraded": True}

    async def _mindmap_fallback_node(self, state: MeetingState) -> dict:
        text, structure = _fallback_text(
            state, "mindmap", MINDMAP_FALLBACK_RULES)
        line_dict = {"rendered": text, "degraded": True}
        if structure is not None:
            line_dict["structure"] = structure
        return {"lines": {"mindmap": line_dict}, "quality_degraded": True}

    async def _multi_styles_fallback_node(self, state: MeetingState) -> dict:
        text, structure = _fallback_text(
            state, "multi_styles", MULTI_STYLES_FALLBACK_RULES)
        line_dict = {"rendered": text, "degraded": True}
        if structure is not None:
            line_dict["structure"] = structure
        return {"lines": {"multi_styles": line_dict}, "quality_degraded": True}

    # ── 专属节点方法生成区结束 ──

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

        self.action_items_agent: ActionItemsAgent = agents["action_items_agent"]
        self.action_items_supervisor: ActionItemsSupervisor = agents["action_items_supervisor"]
        self.action_items_render: ActionItemsRender = agents["action_items_render"]
        self.mindmap_agent: MindmapAgent = agents["mindmap_agent"]
        self.mindmap_supervisor: MindmapSupervisor = agents["mindmap_supervisor"]
        self.mindmap_render: MindmapRender = agents["mindmap_render"]
        self.minutes_generation_agent: MinutesGenerationAgent = agents["minutes_generation_agent"]
        self.minutes_generation_supervisor: MinutesGenerationSupervisor = agents["minutes_generation_supervisor"]
        self.minutes_generation_render: MinutesGenerationRender = agents["minutes_generation_render"]
        self.multi_styles_agent: MultiStylesAgent = agents["multi_styles_agent"]
        self.multi_styles_supervisor: MultiStylesSupervisor = agents["multi_styles_supervisor"]
        self.multi_styles_render: MultiStylesRender = agents["multi_styles_render"]
        self.risk_agent: RiskAgent = agents["risk_agent"]
        self.risk_supervisor: RiskSupervisor = agents["risk_supervisor"]
        self.risk_render: RiskRender = agents["risk_render"]

        # ── Agent 挂载生成区结束 ──

        # 各线专属的渲染 / 降级节点（同构节点由注册表在 _build_graph 中生成）
        # ── 节点映射生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._fallback_nodes: dict[str, object] = {}
        self._fallback_nodes["action_items"] = self._action_items_fallback_node
        self._fallback_nodes["mindmap"] = self._mindmap_fallback_node
        self._fallback_nodes["minutes_generation"] = self._minutes_generation_fallback_node
        self._fallback_nodes["multi_styles"] = self._multi_styles_fallback_node
        self._fallback_nodes["risk"] = self._risk_fallback_node

        # ── 节点映射生成区结束 ──

        # 各线 Report 组装器：线名 → Report 类（脚本生成，键 = 线名与 chunk.line 一致）
        # ── Report 组装器生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._report_assemblers = {
            "action_items": ActionItemsReport,
            "mindmap": MindmapReport,
            "minutes_generation": MinutesReport,
            "multi_styles": MultiStylesReport,
            "risk": RiskReport,
        }

        # ── Report 组装器生成区结束 ──

        # 各线降级规则：线名 → FallbackRules 实例（脚本生成，图异常兜底用）
        # ── FallbackRules 注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._fallback_rules = {
            "action_items": ACTION_ITEMS_FALLBACK_RULES,
            "mindmap": MINDMAP_FALLBACK_RULES,
            "minutes_generation": MINUTES_FALLBACK_RULES,
            "multi_styles": MULTI_STYLES_FALLBACK_RULES,
            "risk": RISK_FALLBACK_RULES,
        }

        # ── FallbackRules 注册生成区结束 ──

        # 共享编排内核所需实例属性（引擎通过 self 读取；值来自领域注册表）
        self._task_lines = TASK_LINES
        self._line_cn_names = LINE_CN_NAMES
        self._state_class = MeetingState
        self._quality_warning = QUALITY_WARNING
