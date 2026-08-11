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
    KnowledgeGraphReportValidation,
    PointsReportValidation,
)

# ── Report 基类 import 生成区结束 ──

@dataclass
class PointsReport(ModelMixin, PointsReportValidation):
    """知识点总结输出。"""

    points: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "structure"},
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
