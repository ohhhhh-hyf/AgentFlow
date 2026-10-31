"""Visual Minutes 通用视觉 IR。

只保留少量通用原语，业务语义由 Planner 决定，渲染器只负责确定性呈现。
"""
from __future__ import annotations

from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


# ── 通用视觉原语 ──────────────────────────────────────────────

class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    time_label: str
    title: str
    detail: str = ""
    evidence: str = ""


class TimelineData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    events: List[TimelineEvent] = Field(default_factory=list)


class TimelineVisual(BaseModel):
    kind: Literal["timeline"] = "timeline"
    title: str
    data: TimelineData


class TableRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cells: List[str] = Field(default_factory=list)
    evidence: str = ""


class TableData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    columns: List[str] = Field(default_factory=list)
    rows: List[TableRow] = Field(default_factory=list)


class TableVisual(BaseModel):
    kind: Literal["table"] = "table"
    title: str
    data: TableData


class FlowNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    node_id: str
    title: str
    detail: str = ""
    evidence: str = ""


class FlowEdge(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    source: str = Field(alias="from")
    target: str = Field(alias="to")
    label: str = ""


class FlowData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nodes: List[FlowNode] = Field(default_factory=list)
    edges: List[FlowEdge] = Field(default_factory=list)


class FlowVisual(BaseModel):
    kind: Literal["flow"] = "flow"
    title: str
    data: FlowData


class TreeNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    node_id: str
    parent_id: Optional[str] = None
    title: str
    detail: str = ""
    evidence: str = ""


class TreeData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nodes: List[TreeNode] = Field(default_factory=list)


class TreeVisual(BaseModel):
    kind: Literal["tree"] = "tree"
    title: str
    data: TreeData


class StatMetric(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str
    value: str
    evidence: str = ""  # 已废弃字段：不再渲染且模型不再输出，保留默认值以完全兼容已有缓存


class StatsData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    metrics: List[StatMetric] = Field(default_factory=list)


class StatsVisual(BaseModel):
    kind: Literal["stats"] = "stats"
    title: str
    data: StatsData


VisualUnion = Annotated[
    Union[
        TimelineVisual,
        TableVisual,
        FlowVisual,
        TreeVisual,
        StatsVisual,
    ],
    Field(discriminator="kind"),
]


class SectionVisual(BaseModel):
    """一个 section 的最终视觉结果；visual=None 表示该段不出图。"""

    model_config = ConfigDict(extra="ignore")

    section_id: str
    visual: Optional[VisualUnion] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)


# ── Planner 输出 ──────────────────────────────────────────────

VisualKind = Literal["none", "timeline", "table", "flow", "tree", "stats"]


class SectionDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    section_id: str
    visual: VisualKind = "none"
    necessity: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    required_data: List[str] = Field(default_factory=list)


class PlannerResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sections: List[SectionDecision] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ── 开篇通览图 ────────────────────────────────────────────────

class BlockHighlight(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tag: str = ""
    value: str = ""


class CardItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tag: str = ""
    title: str = ""
    summary: str = ""
    key_points: List[str] = Field(default_factory=list)
    highlight: Optional[BlockHighlight] = None


class CardsData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: List[CardItem] = Field(default_factory=list)


class CardsVisual(BaseModel):
    kind: Literal["cards"] = "cards"
    title: str = ""
    data: CardsData = Field(default_factory=CardsData)


MasterWidget = Annotated[
    Union[
        TimelineVisual,
        TableVisual,
        FlowVisual,
        TreeVisual,
        StatsVisual,
        CardsVisual,
    ],
    Field(discriminator="kind"),
]


class MasterBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    section_ids: List[str] = Field(default_factory=list)
    title: str
    summary: str = ""
    key_points: List[str] = Field(default_factory=list)
    highlight: Optional[BlockHighlight] = None


class MasterMetric(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str
    value: str
    evidence: str = ""


class MasterVisual(BaseModel):
    model_config = ConfigDict(extra="ignore")

    headline: str
    thesis: str = ""  # 已彻底废弃：大模型不提取，前端不渲染
    widgets: List[MasterWidget] = Field(default_factory=list)
    layout: Literal["grid", "timeline", "flow", "matrix"] = "grid"
    blocks: List[MasterBlock] = Field(default_factory=list)
    metrics: List[MasterMetric] = Field(default_factory=list)


class VisualDocumentIR(BaseModel):
    model_config = ConfigDict(extra="ignore")

    master: MasterVisual
    sections: List[SectionVisual] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


__all__ = [
    "BlockHighlight",
    "CardItem",
    "CardsData",
    "CardsVisual",
    "FlowData",
    "FlowEdge",
    "FlowNode",
    "FlowVisual",
    "MasterBlock",
    "MasterMetric",
    "MasterVisual",
    "MasterWidget",
    "PlannerResponse",
    "SectionDecision",
    "SectionVisual",
    "StatMetric",
    "StatsData",
    "StatsVisual",
    "TableData",
    "TableRow",
    "TableVisual",
    "TimelineData",
    "TimelineEvent",
    "TimelineVisual",
    "TreeData",
    "TreeNode",
    "TreeVisual",
    "VisualDocumentIR",
    "VisualKind",
    "VisualUnion",
]
