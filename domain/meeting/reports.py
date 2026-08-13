"""会议域全部任务线的最终输出 Report 类 —— 手写区（无生成区标记）。

新增任务线时在此追加 Report 类：
- 字段声明 + ``metadata["source"]`` 标签（供通用组装器取值）
- 继承 ``models`` 里脚本生成的 ``XxxReportValidation``（validate 自动生成）
- 顶部基类 import 生成区由脚本自动补（勿手改）
"""
from __future__ import annotations

from dataclasses import dataclass, field

from typing import Any

# ── Report 基类 import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .models import (
    ModelMixin,
    ActionItemsReportValidation,
    MindmapReportValidation,
    MinutesReportValidation,
    MultiStylesReportValidation,
    RiskReportValidation,
)

# ── Report 基类 import 生成区结束 ──

@dataclass
class MinutesReport(ModelMixin, MinutesReportValidation):
    """纪要输出（与待办输出分离，各自独立）。

    字段的 ``metadata["source"]`` 供通用组装器从 state 抽屉取值：
    ``title`` → 视角标题（通用计算）；``rendered`` → 渲染正文。
    """

    title: str = field(metadata={"source": "title"})
    personalized_minutes: str = field(metadata={"source": "rendered"})
    # 仅由系统在兜底路径写入；LLM 输出不需要也不应包含该字段
    quality_warning: str | None = None

@dataclass
class ActionItemsReport(ModelMixin, ActionItemsReportValidation):
    """待办输出（与纪要输出分离，各自独立）。

    字段的 ``metadata["source"]`` 供通用组装器从 state 抽屉取值：
    ``structure`` → 结构化待办列表（extract_actions 合并结果）；
    ``rendered`` → LLM 渲染文本（无模板普通渲染 / 有模板按模板）。
    """

    # 结构化待办列表（客观视角 = 全员已分配 + 未分配；个人视角 = 本人）
    action_items: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={
            "source": "structure",
            "item_validator": "action",  # 逐条待办结构校验器（生成 validate 用）
        },
    )
    # 仅由系统在兜底路径写入；LLM 输出不需要也不应包含该字段
    quality_warning: str | None = None
    # 待办渲染文本（无模板 / 有模板均为 LLM 输出）
    personalized_text: str | None = field(
        default=None, metadata={"source": "rendered"}
    )

@dataclass
class RiskReport(ModelMixin, RiskReportValidation):
    """风险分析输出。"""

    risks: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "structure"},
    )
    quality_warning: str | None = None
    personalized_text: str | None = field(
        default=None,
        metadata={"source": "rendered"},
    )

@dataclass
class MindmapReport(ModelMixin, MindmapReportValidation):
    """思维导图输出：outline（Markdown 大纲，markmap 的直接输入）。

    字段的 ``metadata["source"]`` 供通用组装器从 state 抽屉取值：
    ``rendered`` → 渲染后的规范大纲（LLM 渲染结果）。
    """

    outline: str = field(default="", metadata={"source": "rendered"})
    quality_warning: str | None = None

@dataclass
class MultiStylesReport(ModelMixin, MultiStylesReportValidation):
    """多样式纪要输出（时间线 / 逻辑总分 / 因果推导 / 主体责权 / 决策时效）。

    mode / title / summary / sections 取自草稿（draft.* 与 structure）；
    personalized_text 为渲染正文。
    """

    mode: str = field(default="", metadata={"source": "draft.mode"})
    title: str = field(default="", metadata={"source": "draft.title"})
    summary: str = field(default="", metadata={"source": "draft.summary"})
    sections: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "structure"},
    )
    quality_warning: str | None = None
    personalized_text: str | None = field(
        default=None,
        metadata={"source": "rendered"},
    )
