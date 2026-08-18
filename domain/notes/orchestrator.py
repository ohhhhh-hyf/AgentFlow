"""notes 编排层：LangGraph 图 + 节点 + 流式输出（笔记 域）。

手写区 = 领域钩子覆写（共享上下文 / core 节点 / render 前特判）；
生成区（由 tools/scripts/sync_domain.py 生成）：任务线注册 / Agent 挂载 /
各类 import / Report 组装器 / FallbackRules。render / fallback 由运行时一份函数生成。

共享编排内核位于 ``tools/domain_engine.py``，渲染在 ``tools.runtime.render``。
本文件只保留领域差异：笔记理解 core 节点、含 notes 理解的上下文、
knowledge_graph 线 render 前特判、降级格式化器。

新增任务线流程：register_task.py --domain notes --task xxx --name "中文名"
→ 手写 tasks/xxx/prompts.py + reports.py 追加 Report 类
→ sync_domain.py --domain notes 全量生成 → --check 校验。
"""
from __future__ import annotations

import logging

from langgraph.graph import START

from llm_client import LLMClient
from perspective import PerspectiveModelingAgent
from .domain_config import LINE_CN_NAMES, LINE_KINDS
from .models import NotesState
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
)
from tools.runtime.kinds import resolve_line_policies

# ── Report import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .reports import (
    CatalogReport,
    ChecklistReport,
    KnowledgeGraphReport,
    LastClassReport,
    LibraryReport,
    QuizReport,
    ReviewReport,
)
# ── Report import 生成区结束 ──

# ── 任务线 import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .tasks.catalog import (
    CatalogAgent,
    CatalogRender,
    CatalogSupervisor,
)

from .tasks.checklist import (
    ChecklistAgent,
    ChecklistRender,
    ChecklistSupervisor,
)

from .tasks.knowledge_graph import (
    KnowledgeGraphAgent,
    KnowledgeGraphRender,
    KnowledgeGraphSupervisor,
)

from .tasks.last_class import (
    LastClassAgent,
    LastClassRender,
    LastClassSupervisor,
)

from .tasks.library import (
    LibraryAgent,
    LibraryRender,
    LibrarySupervisor,
)

from .tasks.quiz import (
    QuizAgent,
    QuizRender,
    QuizSupervisor,
)

from .tasks.review import (
    ReviewAgent,
    ReviewRender,
    ReviewSupervisor,
)

# ── 任务线 import 生成区结束 ──

# ── FallbackRules import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .tasks.catalog.contracts import CATALOG_FALLBACK_RULES
from .tasks.checklist.contracts import CHECKLIST_FALLBACK_RULES
from .tasks.knowledge_graph.contracts import KNOWLEDGE_GRAPH_FALLBACK_RULES
from .tasks.last_class.contracts import LAST_CLASS_FALLBACK_RULES
from .tasks.library.contracts import LIBRARY_FALLBACK_RULES
from .tasks.quiz.contracts import QUIZ_FALLBACK_RULES
from .tasks.review.contracts import REVIEW_FALLBACK_RULES

# ── FallbackRules import 生成区结束 ──

logger = logging.getLogger(__name__)

QUALITY_WARNING = "生成可能有误，请结合原文核对。"
QUALITY_DISCLAIMER = "（生成可能有误）"

# ── 空结构常量生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

_EMPTY_CATALOG = {
    "course": "",
    "version": "",
    "mode": "",
    "chapters": [],
    "unmatched_content": [],
    "uncertain_nodes": [],
    "added_chapters": [],
    "added_topics": [],
    "added_knowledge_points": [],
    "updated_knowledge_points": [],
    "merged_nodes": [],
}

_EMPTY_CHECKLIST = {
    "course": "",
    "catalog_version": "",
    "cards": [],
    "uncertain_quotes": [],
    "strategy": [],
    "phases": [],
}

_EMPTY_KNOWLEDGE_GRAPH = {
    "title": "",
    "nodes": [],
    "edges": [],
}

_EMPTY_LAST_CLASS = {
    "focus_points": [],
    "exam_hints": [],
    "classroom_notes": [],
    "strategy": "",
}

_EMPTY_LIBRARY = {
    "message": "",
    "increment": "",
    "files": [],
    "increment_by_file": [],
    "conflicts": [],
    "items": [],
}

_EMPTY_NOTES_UNDERSTANDING = {
    "note_purpose": "",
    "sections": [],
    "key_terms": [],
    "open_questions": [],
}

_EMPTY_QUIZ = {
    "concepts": [],
    "relations": [],
    "details": [],
    "questions": [],
}

_EMPTY_REVIEW = {
    "knowledge_points": [],
    "issues": [],
    "corrected_notes": "",
}

# ── 空结构常量生成区结束 ──

# ── 拒绝审核常量生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

_REJECT_KNOWLEDGE_GRAPH_REVIEW = {
    "decision": "reject",
    "graph_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_REVIEW_REVIEW = {
    "decision": "reject",
    "review_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_QUIZ_REVIEW = {
    "decision": "reject",
    "quiz_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_LIBRARY_REVIEW = {
    "decision": "reject",
    "library_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_CATALOG_REVIEW = {
    "decision": "reject",
    "catalog_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_CHECKLIST_REVIEW = {
    "decision": "reject",
    "checklist_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

_REJECT_LAST_CLASS_REVIEW = {
    "decision": "reject",
    "last_class_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

# ── 拒绝审核常量生成区结束 ──

# ── 任务线注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

TASK_LINES: dict[str, dict] = {
    "catalog": {
        "agent_attr": "catalog_agent",
        "supervisor_attr": "catalog_supervisor",
        "empty_draft": _EMPTY_CATALOG,
        "reject_review": _REJECT_CATALOG_REVIEW,
    },
    "checklist": {
        "agent_attr": "checklist_agent",
        "supervisor_attr": "checklist_supervisor",
        "empty_draft": _EMPTY_CHECKLIST,
        "reject_review": _REJECT_CHECKLIST_REVIEW,
    },
    "knowledge_graph": {
        "agent_attr": "knowledge_graph_agent",
        "supervisor_attr": "knowledge_graph_supervisor",
        "empty_draft": _EMPTY_KNOWLEDGE_GRAPH,
        "reject_review": _REJECT_KNOWLEDGE_GRAPH_REVIEW,
    },
    "last_class": {
        "agent_attr": "last_class_agent",
        "supervisor_attr": "last_class_supervisor",
        "empty_draft": _EMPTY_LAST_CLASS,
        "reject_review": _REJECT_LAST_CLASS_REVIEW,
    },
    "library": {
        "agent_attr": "library_agent",
        "supervisor_attr": "library_supervisor",
        "empty_draft": _EMPTY_LIBRARY,
        "reject_review": _REJECT_LIBRARY_REVIEW,
    },
    "quiz": {
        "agent_attr": "quiz_agent",
        "supervisor_attr": "quiz_supervisor",
        "empty_draft": _EMPTY_QUIZ,
        "reject_review": _REJECT_QUIZ_REVIEW,
    },
    "review": {
        "agent_attr": "review_agent",
        "supervisor_attr": "review_supervisor",
        "empty_draft": _EMPTY_REVIEW,
        "reject_review": _REJECT_REVIEW_REVIEW,
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

class _Nodes(DomainNodes):
    """notes 图节点实现：共享内核 + 领域专属钩子与笔记理解节点。"""

    _fallback_formatters = _LINES_FORMATTERS
    _quality_disclaimer = QUALITY_DISCLAIMER
    _understanding_key = "notes_understanding"
    _understanding_label = "已审核笔记理解"
    _transcript_label = "原文"
    _line_cn_names = LINE_CN_NAMES
    _line_policies = resolve_line_policies(LINE_KINDS)

    # ── 领域钩子：共享上下文（含笔记理解）──────────────────────

    def _shared_context(self, state) -> str:
        """agent 共享上下文（视角模式 + 画像 + 视角模型 + 原文 + 笔记理解）。"""
        mode = self._mode_label(state)
        extras = [
            str((state.get("line_extra") or {}).get(key) or "").strip()
            for key in ("quiz", "library")
        ]
        extra_block = "\n\n" + "\n\n".join(x for x in extras if x)
        extra_block = extra_block if extra_block.strip() else ""
        return (
            f"视角模式：{mode}\n"
            f"说明：perspective=objective 时为客观全员口径；"
            f"缺省或其它值为个人用户口径。\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"用户视角模型：\n{_json(state.get('perspective_profile'))}\n\n"
            f"notes理解：\n{_json(state.get('notes_understanding'))}\n\n"
            f"原文：\n{state['transcript']}"
            f"{extra_block}"
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
        extra = str((state.get("line_extra") or {}).get(line_name) or "").strip()
        extra_block = f"\n\n{extra}" if extra else ""
        return (
            f"视角模式：{mode}\n"
            f"{_line_cn(line_name)}返工次数：{revision_count}/{self.MAX_REVISIONS}\n"
            f"{allowed}\n\n"
            f"notes理解：\n{_json(state.get('notes_understanding'))}\n\n"
            f"原文（最高事实来源）：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"用户视角模型：\n{_json(state.get('perspective_profile'))}\n\n"
            f"{_line_draft_title(line_name)}：\n{_json(sub['draft'])}"
            f"{extra_block}"
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

    def _post_render_hook(self, state, line_name: str) -> None:
        super()._post_render_hook(state, line_name)
        if line_name == "review":
            from .tasks.review.display import attach_review_artifacts

            try:
                attach_review_artifacts(state)
            except Exception:
                logger.exception("笔记审查挂载知识库出处失败")
            else:
                render = getattr(self, "review_render", None)
                extractor = getattr(render, "extract_structure", None)
                if extractor:
                    _line(state, line_name)["structure"] = extractor(state)
        elif line_name == "quiz":
            from .tasks.quiz.display import attach_quiz_artifacts

            try:
                attach_quiz_artifacts(state)
            except Exception:
                logger.exception("自测题挂载知识库出处或题库检索失败")
        elif line_name == "library":
            from .tasks.library.report import attach_library_artifacts

            attach_library_artifacts(state)
        elif line_name == "last_class":
            from .tasks.last_class.display import attach_last_class_artifacts

            try:
                attach_last_class_artifacts(state)
            except Exception:
                logger.exception("期末划重点挂载知识库来源失败")
        elif line_name == "catalog":
            from .tasks.catalog.display import attach_catalog_artifacts

            try:
                attach_catalog_artifacts(state)
            except Exception:
                logger.exception("知识目录排版失败")
        elif line_name == "checklist":
            from .tasks.checklist.display import attach_checklist_artifacts

            try:
                attach_checklist_artifacts(state)
            except Exception:
                logger.exception("复习清单排版失败")

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

        self.catalog_agent: CatalogAgent = agents["catalog_agent"]
        self.catalog_supervisor: CatalogSupervisor = agents["catalog_supervisor"]
        self.catalog_render: CatalogRender = agents["catalog_render"]
        self.checklist_agent: ChecklistAgent = agents["checklist_agent"]
        self.checklist_supervisor: ChecklistSupervisor = agents["checklist_supervisor"]
        self.checklist_render: ChecklistRender = agents["checklist_render"]
        self.knowledge_graph_agent: KnowledgeGraphAgent = agents["knowledge_graph_agent"]
        self.knowledge_graph_supervisor: KnowledgeGraphSupervisor = agents["knowledge_graph_supervisor"]
        self.knowledge_graph_render: KnowledgeGraphRender = agents["knowledge_graph_render"]
        self.last_class_agent: LastClassAgent = agents["last_class_agent"]
        self.last_class_supervisor: LastClassSupervisor = agents["last_class_supervisor"]
        self.last_class_render: LastClassRender = agents["last_class_render"]
        self.library_agent: LibraryAgent = agents["library_agent"]
        self.library_supervisor: LibrarySupervisor = agents["library_supervisor"]
        self.library_render: LibraryRender = agents["library_render"]
        self.quiz_agent: QuizAgent = agents["quiz_agent"]
        self.quiz_supervisor: QuizSupervisor = agents["quiz_supervisor"]
        self.quiz_render: QuizRender = agents["quiz_render"]
        self.review_agent: ReviewAgent = agents["review_agent"]
        self.review_supervisor: ReviewSupervisor = agents["review_supervisor"]
        self.review_render: ReviewRender = agents["review_render"]

        # ── Agent 挂载生成区结束 ──

        # ── Report 组装器生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._report_assemblers = {
            "catalog": CatalogReport,
            "checklist": ChecklistReport,
            "knowledge_graph": KnowledgeGraphReport,
            "last_class": LastClassReport,
            "library": LibraryReport,
            "quiz": QuizReport,
            "review": ReviewReport,
        }

        # ── Report 组装器生成区结束 ──

        # ── FallbackRules 注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._fallback_rules = {
            "catalog": CATALOG_FALLBACK_RULES,
            "checklist": CHECKLIST_FALLBACK_RULES,
            "knowledge_graph": KNOWLEDGE_GRAPH_FALLBACK_RULES,
            "last_class": LAST_CLASS_FALLBACK_RULES,
            "library": LIBRARY_FALLBACK_RULES,
            "quiz": QUIZ_FALLBACK_RULES,
            "review": REVIEW_FALLBACK_RULES,
        }

        # ── FallbackRules 注册生成区结束 ──

        # 共享编排内核所需实例属性（引擎通过 self 读取；值来自领域注册表）
        self._task_lines = TASK_LINES
        self._line_cn_names = LINE_CN_NAMES
        self._state_class = NotesState
        self._quality_warning = QUALITY_WARNING
