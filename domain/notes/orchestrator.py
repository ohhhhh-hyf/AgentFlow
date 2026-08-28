"""notes 编排层：LangGraph 图 + 节点 + 流式输出（笔记 域）。

手写区 = 领域钩子覆写（共享上下文 / core 节点 / render 前特判）；
生成区（由 tools/scripts/sync_domain.py 生成）：任务线注册 / Agent 挂载 /
各类 import / Report 组装器 / FallbackRules。render / fallback 由运行时一份函数生成。

共享编排内核位于 ``tools/domain_engine.py``，渲染在 ``tools.runtime.render``。
本文件只保留领域差异：笔记理解 core 节点、含 notes 理解的上下文、
graph 线 render 前特判、降级格式化器。

新增任务线流程：register_task.py --domain notes --task xxx --name "中文名"
→ 手写 tasks/xxx/prompts.py + reports.py 追加 Report 类
→ sync_domain.py --domain notes 全量生成 → --check 校验。
"""
from __future__ import annotations

import logging

from langgraph.graph import START

from client import LLMClient
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

from .tasks.graph import (
    KnowledgeGraphAgent,
    KnowledgeGraphRender,
    KnowledgeGraphSupervisor,
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
from .tasks.graph.contracts import KNOWLEDGE_GRAPH_FALLBACK_RULES
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
    "graph": {
        "agent_attr": "graph_agent",
        "supervisor_attr": "graph_supervisor",
        "empty_draft": _EMPTY_KNOWLEDGE_GRAPH,
        "reject_review": _REJECT_KNOWLEDGE_GRAPH_REVIEW,
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
    "graph": format_graph_node,
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

    # ── 领域钩子：共享上下文（按线裁剪，notes 域不注入画像/视角）────────

    def _understanding_pack(self, state, line_name: str) -> dict:
        """按线裁剪笔记理解包：只给该线消费的字段（理解输出仍是全量）。

        - graph / catalog：note_purpose + sections + key_terms（open_questions 不消费）
        - review / quiz：全量（CLI 线，保持现状）
        - 其余：全量兜底
        """
        u = state.get("notes_understanding") or {}
        if not isinstance(u, dict):
            return {}
        if line_name in {"graph", "catalog"}:
            return {
                key: u.get(key)
                for key in ("note_purpose", "sections", "key_terms")
                if u.get(key) not in (None, "")
            }
        return u

    def _line_shared_context(self, state, line_name: str) -> str:
        """按线拼 agent 上下文（只给该线消费的块）。

        - 原文块对全部线保留：graph/review/quiz 是笔记正文，catalog/checklist 是
          老师划重点文本（_teacher_text / teacher_from_context 从「原文:」块提取）
        - 理解包按线裁剪（graph/catalog 跳过 open_questions）；checklist 跳过理解
        """
        mode = self._mode_label(state)
        head = (
            f"视角模式：{mode}\n"
            f"说明：perspective=objective 时为客观全员口径；"
            f"缺省或其它值为个人用户口径。"
        )
        parts = [head]
        if line_name != "checklist":
            parts.append(
                f"notes理解：\n{_json(self._understanding_pack(state, line_name))}"
            )
        parts.append(f"原文：\n{state['transcript']}")
        return "\n\n".join(parts)

    def _make_agent_node(self, line_name: str):
        """笔记域生成节点：使用按线裁剪的上下文（同构共享内核，替换一刀切上下文）。"""
        cfg = self._task_lines[line_name]
        cn = _line_cn(line_name)

        async def node(state: dict) -> dict:
            agent = getattr(self, cfg["agent_attr"])
            context = self._line_shared_context(state, line_name)
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

    def _understanding_needle_fields(self, line_name: str) -> set[str] | None:
        """审核摘录时笔记理解参与 needle 的字段白名单（未列出的线走全字段）。"""
        keep = {
            "graph": {"note_purpose", "sections", "key_terms"},
            "catalog": {"note_purpose", "sections", "key_terms"},
            "review": {"note_purpose", "sections", "key_terms", "open_questions"},
            "quiz": {"note_purpose", "sections", "key_terms", "open_questions"},
        }.get(line_name)
        return set(keep) if keep else None

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
        extra = str((state.get("line_extra") or {}).get(line_name) or "").strip()
        extra_block = f"\n\n{extra}" if extra else ""
        return (
            f"视角模式：{mode}\n"
            f"{_line_cn(line_name)}返工次数：{revision_count}/{self.MAX_REVISIONS}\n"
            f"{allowed}\n\n"
            f"{self._supervisor_source_pack(state, line_name)}\n\n"
            f"{_line_draft_title(line_name)}：\n{_json(sub['draft'])}"
            f"{extra_block}"
        )

    # ── 领域钩子：core 节点 ───────────────────────────────────

    def _build_core(self, builder, line_names=None) -> list[str]:
        """核心层：笔记理解按线按需构建（notes 域不跑视角建模）。

        - 视角建模：notes 域全部跳过（graph/catalog 的 prompt 不消费视角模型/画像，
          省一次读全文的大调用）
        - 笔记理解：library / checklist 跳过；graph / catalog 需要
          （catalog 需要理解锚点做稳定目录）
        """
        skip_understanding = frozenset({"library", "checklist"})
        selected = [name for name in (line_names or []) if name]
        need_understanding = (not selected) or any(
            name not in skip_understanding for name in selected
        )
        cores: list[str] = []
        if need_understanding:
            builder.add_node("notes_understanding", self._notes_understanding_node)
            builder.add_edge(START, "notes_understanding")
            cores.append("notes_understanding")
        if not cores:
            # 全部 core 节点都被按线跳过：用占位入口保证图有 START 起点
            builder.add_node("noop_core", self._noop_core_node)
            builder.add_edge(START, "noop_core")
            cores = ["noop_core"]
        return cores

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
        self.graph_agent: KnowledgeGraphAgent = agents["graph_agent"]
        self.graph_supervisor: KnowledgeGraphSupervisor = agents["graph_supervisor"]
        self.graph_render: KnowledgeGraphRender = agents["graph_render"]
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
            "graph": KnowledgeGraphReport,
            "library": LibraryReport,
            "quiz": QuizReport,
            "review": ReviewReport,
        }

        # ── Report 组装器生成区结束 ──

        # ── FallbackRules 注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._fallback_rules = {
            "catalog": CATALOG_FALLBACK_RULES,
            "checklist": CHECKLIST_FALLBACK_RULES,
            "graph": KNOWLEDGE_GRAPH_FALLBACK_RULES,
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

