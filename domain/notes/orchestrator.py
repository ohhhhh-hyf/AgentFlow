"""notes 编排层：LangGraph 图 + 节点 + 流式输出（笔记 域）。

手写区 = 领域钩子覆写（共享上下文 / core 节点 / render 前特判）；
生成区（由 tools/scripts/sync_domain.py 生成）：任务线注册 / Agent 挂载 /
节点映射 / 渲染上下文 / 各类 import / Report 组装器 / FallbackRules /
专属节点骨架。

共享编排内核位于 ``tools/domain_engine.py``（DomainNodes mixin + 纯函数），
与 meeting 域共用同一套图节点 / 流式生产 / 图构建 / 运行逻辑，
本文件只保留领域差异：笔记理解 core 节点、含 notes 理解的上下文、
knowledge_graph 线 render 前特判、降级格式化器。

新增任务线流程：register_task.py --domain notes --task xxx --name "中文名"
→ 手写 tasks/xxx/prompts.py + reports.py 追加 Report 类
→ sync_domain.py --domain notes 全量生成 → --check 校验。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable

from langgraph.graph import START

from llm_client import LLMClient
from perspective import PerspectiveModelingAgent
from .domain_config import LINE_CN_NAMES
from .models import (
    NotesState,
    UserIdentity,
    is_objective_perspective,
)
from .notes_factory import NotesAgentFactory
from .notes_core import NotesUnderstandingAgent

# 共享编排内核（领域无关）：纯函数 + DomainNodes 图节点 mixin
from tools.domain_engine import (
    DomainNodes,
    format_graph_node,
    json_dumps as _json,
    line as _line,
    line_cn as _engine_line_cn,
    line_draft_title as _engine_line_draft_title,
    line_template as _line_template,
    make_fallback_text,
)

# ── Report import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .reports import (
    KnowledgeGraphReport,
    PointsReport,
)
# ── Report import 生成区结束 ──

# ── 任务线 import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .tasks.knowledge_graph import (
    KnowledgeGraphAgent,
    KnowledgeGraphRender,
    KnowledgeGraphSupervisor,
)

from .tasks.points import (
    PointsAgent,
    PointsRender,
    PointsSupervisor,
)

# ── 任务线 import 生成区结束 ──

# ── FallbackRules import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .tasks.knowledge_graph.contracts import KNOWLEDGE_GRAPH_FALLBACK_RULES
from .tasks.points.contracts import POINTS_FALLBACK_RULES

# ── FallbackRules import 生成区结束 ──

logger = logging.getLogger(__name__)

QUALITY_WARNING = "生成可能有误，请结合原文核对。"
QUALITY_DISCLAIMER = "（生成可能有误）"

# ── 空结构常量生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

_EMPTY_KNOWLEDGE_GRAPH = {
    "title": "",
    "nodes": [],
    "edges": [],
}

_EMPTY_NOTES_UNDERSTANDING = {
    "note_purpose": "",
    "sections": [],
    "key_terms": [],
    "open_questions": [],
}

_EMPTY_POINTS = {
    "points": [],
}

# ── 空结构常量生成区结束 ──

# ── 拒绝审核常量生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

_REJECT_POINTS_REVIEW = {
    "decision": "reject",
    "points_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_KNOWLEDGE_GRAPH_REVIEW = {
    "decision": "reject",
    "graph_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

# ── 拒绝审核常量生成区结束 ──

# ── 任务线注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

TASK_LINES: dict[str, dict] = {
    "knowledge_graph": {
        "agent_attr": "knowledge_graph_agent",
        "supervisor_attr": "knowledge_graph_supervisor",
        "empty_draft": _EMPTY_KNOWLEDGE_GRAPH,
        "reject_review": _REJECT_KNOWLEDGE_GRAPH_REVIEW,
    },
    "points": {
        "agent_attr": "points_agent",
        "supervisor_attr": "points_supervisor",
        "empty_draft": _EMPTY_POINTS,
        "reject_review": _REJECT_POINTS_REVIEW,
    },
}

# ── 任务线注册生成区结束 ──

def _line_cn(line_name: str) -> str:
    """线名 → 中文名（查共享注册表，未注册则回退英文线名）。"""
    return _engine_line_cn(line_name, LINE_CN_NAMES)

def _line_draft_title(line_name: str) -> str:
    """线名 → 草稿标题（自动推导为「中文名草稿」）。"""
    return _engine_line_draft_title(line_name, LINE_CN_NAMES)

# Lines 段逐条格式化器注册表（domain 按需填写）
# 例：lines 段需要逐条格式化时注册 {线名: 格式化函数(index, item) -> str}
_LINES_FORMATTERS: dict[str, object] = {
    "knowledge_graph": format_graph_node,
}

def _empty_purpose(state) -> str:
    """empty_purpose 兜底时的「目的」文案（领域有核心理解时覆写）。"""
    return ""

# 生成区骨架引用的模块级 _fallback_text（3 参版本，绑定领域 formatters）
_fallback_text = make_fallback_text(
    _LINES_FORMATTERS, _empty_purpose, QUALITY_DISCLAIMER
)

class _Nodes(DomainNodes):
    """notes 图节点实现：共享内核（tools/domain_engine.DomainNodes）+ 领域专属。

    同构节点（agent / supervisor / revision / route）与流式生产 / 图构建 /
    运行由引擎提供；本类只保留领域钩子覆写与领域专属节点（笔记理解）。
    """

    # 领域钩子：降级文本绑定（引擎 _domain_fallback_text 读取）
    _fallback_formatters = _LINES_FORMATTERS
    _quality_disclaimer = QUALITY_DISCLAIMER

    # ── 领域钩子：共享上下文（含笔记理解）──────────────────────

    def _shared_context(self, state) -> str:
        """agent 共享上下文（视角模式 + 画像 + 视角模型 + 原文 + 笔记理解）。"""
        mode = self._mode_label(state)
        return (
            f"视角模式：{mode}\n"
            f"说明：perspective=objective 时为客观全员口径；"
            f"缺省或其它值为个人用户口径。\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"用户视角模型：\n{_json(state.get('perspective_profile'))}\n\n"
            f"notes理解：\n{_json(state.get('notes_understanding'))}\n\n"
            f"原文：\n{state['transcript']}"
        )

    def _supervisor_context(self, state, line_name: str) -> str:
        """审核上下文（原文为最高事实来源，含笔记理解）。"""
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
            f"notes理解：\n{_json(state.get('notes_understanding'))}\n\n"
            f"原文（最高事实来源）：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"用户视角模型：\n{_json(state.get('perspective_profile'))}\n\n"
            f"{_line_draft_title(line_name)}：\n{_json(sub['draft'])}"
        )

    # ── 领域钩子：core 节点 ───────────────────────────────────

    def _build_core(self, builder) -> list[str]:
        """核心层：笔记理解 + 视角建模（并行，任何任务线都需要）。"""
        builder.add_node("notes_understanding", self._notes_understanding_node)
        builder.add_node(
            "perspective_modeling", self._perspective_modeling_node
        )
        builder.add_edge(START, "notes_understanding")
        builder.add_edge(START, "perspective_modeling")
        return ["notes_understanding", "perspective_modeling"]

    # ── 领域钩子：render 前特判（knowledge_graph 无模板直接写标题）──

    def _pre_render_hook(self, state, line_name: str) -> bool:
        """knowledge_graph 未传模板时跳过 LLM 渲染：直接以草稿标题作为大纲。"""
        if line_name == "knowledge_graph" and not _line_template(state, line_name):
            draft = _line(state, line_name).get("draft") or {}
            _line(state, line_name)["rendered"] = (
                f"# {draft.get('title') or _line_cn(line_name)}"
            )
            return True
        return False

    # ── 核心节点：笔记理解（公共事实底座）──────────────────────

    async def _notes_understanding_node(self, state) -> dict:
        """notes理解：提取主题、结构、术语和待澄清问题。"""
        try:
            result = await self.notes_understanding_agent.run(state["transcript"])
        except Exception as exc:
            logger.warning("notes理解失败，使用空理解继续", exc_info=True)
            return {
                "notes_understanding": _EMPTY_NOTES_UNDERSTANDING,
                "quality_degraded": True,
            }
        return {"notes_understanding": result.model_dump()}

    # ── 渲染上下文生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

    def _knowledge_graph_render_context(self, state: NotesState) -> str:
        mode = self._mode_label(state)
        line = _line(state, "knowledge_graph")
        review = line.get("review") or {}
        return (
            f"视角模式：{mode}\n"
            f"objective_perspective：{bool(state.get('objective_perspective'))}\n\n"
            f"原文：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"已审核用户视角：\n{_json(state.get('perspective_profile'))}\n\n"
            f"已批准知识图谱草稿：\n{_json(line.get('draft'))}\n\n"
            f"知识图谱审核结论：\n{_json(review)}"
        )

    def _points_render_context(self, state: NotesState) -> str:
        mode = self._mode_label(state)
        line = _line(state, "points")
        review = line.get("review") or {}
        return (
            f"视角模式：{mode}\n"
            f"objective_perspective：{bool(state.get('objective_perspective'))}\n\n"
            f"原文：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"已审核用户视角：\n{_json(state.get('perspective_profile'))}\n\n"
            f"已批准知识点总结草稿：\n{_json(line.get('draft'))}\n\n"
            f"知识点总结审核结论：\n{_json(review)}"
        )

    # ── 渲染上下文生成区结束 ──

    # ── 专属节点方法生成区：由 tools/scripts/sync_domain.py 生成骨架，函数体可改 ──

    async def _points_fallback_node(self, state: NotesState) -> dict:
        text, structure = _fallback_text(
            state, "points", POINTS_FALLBACK_RULES)
        line_dict = {"rendered": text, "degraded": True}
        if structure is not None:
            line_dict["structure"] = structure
        return {"lines": {"points": line_dict}, "quality_degraded": True}

    async def _knowledge_graph_fallback_node(self, state: NotesState) -> dict:
        text, structure = _fallback_text(
            state, "knowledge_graph", KNOWLEDGE_GRAPH_FALLBACK_RULES)
        line_dict = {"rendered": text, "degraded": True}
        if structure is not None:
            line_dict["structure"] = structure
        return {"lines": {"knowledge_graph": line_dict}, "quality_degraded": True}

    # ── 专属节点方法生成区结束 ──

class NotesAgentSystem(_Nodes):
    """使用 LangGraph 编排核心层、任务线审核返工与最终输出。"""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

        # 通过工厂组装全部 Agent 依赖（键名 = 属性名，与 TASK_LINES 的 *_attr 对齐）
        agents = NotesAgentFactory.create(self.client)

        # core 层挂载（perspective 公共组件；领域核心 Agent 在此追加）
        self.perspective_modeling_agent: PerspectiveModelingAgent = agents[
            "perspective_modeling_agent"
        ]
        self.notes_understanding_agent: NotesUnderstandingAgent = agents[
            "notes_understanding_agent"
        ]

        # ── Agent 挂载生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self.knowledge_graph_agent: KnowledgeGraphAgent = agents["knowledge_graph_agent"]
        self.knowledge_graph_supervisor: KnowledgeGraphSupervisor = agents["knowledge_graph_supervisor"]
        self.knowledge_graph_render: KnowledgeGraphRender = agents["knowledge_graph_render"]
        self.points_agent: PointsAgent = agents["points_agent"]
        self.points_supervisor: PointsSupervisor = agents["points_supervisor"]
        self.points_render: PointsRender = agents["points_render"]

        # ── Agent 挂载生成区结束 ──

        # 各线专属的渲染 / 降级节点（同构节点由注册表在 _build_graph 中生成）
        # ── 节点映射生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._fallback_nodes: dict[str, object] = {}
        self._fallback_nodes["knowledge_graph"] = self._knowledge_graph_fallback_node
        self._fallback_nodes["points"] = self._points_fallback_node

        # ── 节点映射生成区结束 ──

        # ── Report 组装器生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._report_assemblers = {
            "knowledge_graph": KnowledgeGraphReport,
            "points": PointsReport,
        }

        # ── Report 组装器生成区结束 ──

        # ── FallbackRules 注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._fallback_rules = {
            "knowledge_graph": KNOWLEDGE_GRAPH_FALLBACK_RULES,
            "points": POINTS_FALLBACK_RULES,
        }

        # ── FallbackRules 注册生成区结束 ──

        # 共享编排内核所需实例属性（引擎通过 self 读取；值来自领域注册表）
        self._task_lines = TASK_LINES
        self._line_cn_names = LINE_CN_NAMES
        self._state_class = NotesState
        self._quality_warning = QUALITY_WARNING
