"""notes 域全部任务线的最终输出 Report 类 —— 手写区。

每个任务线在文件末尾追加一个 Report dataclass，字段按
``metadata["source"]`` 标签由通用组装器 _assemble_report 取值：

- ``title`` → 视角标题；``rendered`` → LLM 渲染文本
- ``structure`` → 结构化列表；``draft.xxx`` → 草稿字段
- quality_warning 由系统在兜底路径写入（LLM 不输出）

模板：
    @dataclass
    class XxxReport(ModelMixin, XxxReportValidation):
        title: str = field(metadata={"source": "title"})
        ...
"""
from __future__ import annotations

from dataclasses import dataclass, field

from typing import Any

# ── Report 基类 import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .models import (
    ModelMixin,
    CatalogReportValidation,
    ChecklistReportValidation,
    KnowledgeGraphReportValidation,
    LibraryReportValidation,
    QuizReportValidation,
    ReviewReportValidation,
)

# ── Report 基类 import 生成区结束 ──

@dataclass
class CatalogReport(ModelMixin, CatalogReportValidation):
    """知识目录：保存 JSON，页面只给简要说明。"""

    course: str = field(default="", metadata={"source": "draft.course"})
    version: str = field(default="1", metadata={"source": "draft.version"})
    mode: str = field(default="build", metadata={"source": "draft.mode"})
    chapters: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "structure"},
    )
    unmatched_content: list[str] = field(
        default_factory=list,
        metadata={"source": "draft.unmatched_content"},
    )
    uncertain_nodes: list[str] = field(
        default_factory=list,
        metadata={"source": "draft.uncertain_nodes"},
    )
    added_chapters: list[str] = field(
        default_factory=list,
        metadata={"source": "draft.added_chapters"},
    )
    added_topics: list[str] = field(
        default_factory=list,
        metadata={"source": "draft.added_topics"},
    )
    added_knowledge_points: list[str] = field(
        default_factory=list,
        metadata={"source": "draft.added_knowledge_points"},
    )
    updated_knowledge_points: list[str] = field(
        default_factory=list,
        metadata={"source": "draft.updated_knowledge_points"},
    )
    merged_nodes: list[str] = field(
        default_factory=list,
        metadata={"source": "draft.merged_nodes"},
    )
    catalog_html: str = field(
        default="",
        metadata={"source": "draft.catalog_html"},
    )
    quality_warning: str | None = None
    personalized_text: str | None = field(
        default=None,
        metadata={"source": "rendered"},
    )

@dataclass
class ChecklistReport(ModelMixin, ChecklistReportValidation):
    """复习清单：Catalog 激活 KP + 卡片 + HTML。不回写长期目录。"""

    course: str = field(default="", metadata={"source": "draft.course"})
    catalog_version: str = field(default="", metadata={"source": "draft.catalog_version"})
    cards: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "structure"},
    )
    phases: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "draft.phases"},
    )
    strategy: list[str] = field(
        default_factory=list,
        metadata={"source": "draft.strategy"},
    )
    uncertain_quotes: list[str] = field(
        default_factory=list,
        metadata={"source": "draft.uncertain_quotes"},
    )
    checklist_html: str = field(
        default="",
        metadata={"source": "draft.checklist_html"},
    )
    quality_warning: str | None = None
    personalized_text: str | None = field(
        default=None,
        metadata={"source": "rendered"},
    )

@dataclass
class KnowledgeGraphReport(ModelMixin, KnowledgeGraphReportValidation):
    """知识图谱输出。

    字段的 ``metadata["source"]`` 供通用组装器从 state 抽屉取值：
    - ``rendered`` → 树形大纲文本（markmap 可可视化）
    - ``draft.nodes`` / ``draft.edges`` → 已批准图数据（graphviz 渲染图谱用）
    """

    # 树形大纲（LLM 渲染，人可读 / markmap 树形视图）
    outline: str = field(default="", metadata={"source": "rendered"})
    title: str = field(default="", metadata={"source": "draft.title"})
    # 图数据：节点与关系边（bootstrap 据此渲染 graphviz 知识图谱）
    nodes: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "draft.nodes"},
    )
    edges: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "draft.edges"},
    )
    quality_warning: str | None = None

@dataclass
class ReviewReport(ModelMixin, ReviewReportValidation):
    """笔记审查输出：总结 + 对照 HTML + 订正笔记。"""

    knowledge_points: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "draft.knowledge_points"},
    )
    issues: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "structure"},
    )
    corrected_notes: str = field(
        default="",
        metadata={"source": "draft.corrected_notes"},
    )
    review_html: str = field(
        default="",
        metadata={"source": "draft.review_html"},
    )
    original_notes: str = field(
        default="",
        metadata={"source": "draft.original_notes"},
    )
    quality_warning: str | None = None
    personalized_text: str | None = field(
        default=None,
        metadata={"source": "rendered"},
    )

@dataclass
class QuizReport(ModelMixin, QuizReportValidation):
    """自测题输出：题干展开，参考得分点折叠。"""

    questions: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "structure"},
    )
    bank_questions: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "draft.bank_questions"},
    )
    bank_query: str = field(default="", metadata={"source": "draft.bank_query"})
    bank_status: str = field(default="", metadata={"source": "draft.bank_status"})
    quiz_html: str = field(
        default="",
        metadata={"source": "draft.quiz_html"},
    )
    quality_warning: str | None = None
    personalized_text: str | None = field(
        default=None,
        metadata={"source": "rendered"},
    )

@dataclass
class LibraryReport(ModelMixin, LibraryReportValidation):
    """资料入库：知识增量与冲突点，不是解析进度条。"""

    increment: str = field(default="0", metadata={"source": "draft.increment"})
    message: str = field(default="", metadata={"source": "draft.message"})
    files: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "draft.files"},
    )
    increment_by_file: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "draft.increment_by_file"},
    )
    conflicts: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "draft.conflicts"},
    )
    items: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "draft.items"},
    )
    library_html: str = field(
        default="",
        metadata={"source": "draft.library_html"},
    )
    quality_warning: str | None = None
    personalized_text: str | None = field(
        default=None,
        metadata={"source": "rendered"},
    )
