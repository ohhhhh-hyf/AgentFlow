"""IR 校验：保真、覆盖、密度、数据完整性（工业级自愈与容错版）。"""
from __future__ import annotations

from typing import Iterable, List

from ..config import (
    MAX_FLOW_EDGES,
    MAX_FLOW_NODES,
    MAX_MASTER_BLOCK_KEY_POINTS,
    MAX_MASTER_BLOCK_SUMMARY_CHARS,
    MAX_MASTER_KEY_POINT_CHARS,
    MAX_SECTION_VISUALS,
    MAX_STATS_METRICS,
    MAX_TABLE_COLUMNS,
    MAX_TABLE_ROWS,
    MAX_TIMELINE_EVENTS,
    MAX_TREE_NODES,
    MIN_FLOW_EDGES,
    MIN_FLOW_NODES,
    MIN_STATS_METRICS,
    MIN_TABLE_COLUMNS,
    MIN_TABLE_ROWS,
    MIN_TIMELINE_EVENTS,
    MIN_TREE_NODES,
)
from ..agents.master import _is_master_valid, fallback_master
from ..models.ir import MasterVisual, SectionVisual, VisualDocumentIR
from ..parsing.parser import ParsedMinutes, SectionNode


def _evidence_of(visual: SectionVisual) -> list[str]:
    out = [e.strip() for e in visual.evidence if e.strip()]
    data = visual.visual
    if data is None:
        return out
    if data.kind == "timeline":
        out.extend(e.evidence.strip() for e in data.data.events if e.evidence.strip())
    elif data.kind == "table":
        out.extend(r.evidence.strip() for r in data.data.rows if r.evidence.strip())
    elif data.kind == "flow":
        out.extend(n.evidence.strip() for n in data.data.nodes if n.evidence.strip())
    elif data.kind == "tree":
        out.extend(n.evidence.strip() for n in data.data.nodes if n.evidence.strip())
    elif data.kind == "stats":
        out.extend(m.evidence.strip() for m in data.data.metrics if m.evidence.strip())
    return [e for e in out if e]


def _valid_visual(visual: SectionVisual) -> bool:
    data = visual.visual
    if data is None:
        return False
    if data.kind == "timeline":
        return len(data.data.events) >= MIN_TIMELINE_EVENTS
    if data.kind == "table":
        columns = data.data.columns
        rows = data.data.rows
        if len(columns) < MIN_TABLE_COLUMNS or len(rows) < MIN_TABLE_ROWS:
            return False
        # 自愈修复：若某行单元格长度不匹配列数，自适应对齐填充空字符串
        for r in rows:
            if len(r.cells) < len(columns):
                r.cells.extend([""] * (len(columns) - len(r.cells)))
            elif len(r.cells) > len(columns):
                r.cells = r.cells[:len(columns)]
        return True
    if data.kind == "flow":
        nodes = data.data.nodes
        edges = data.data.edges
        if len(nodes) < MIN_FLOW_NODES or len(edges) < MIN_FLOW_EDGES:
            return False
        ids = {n.node_id for n in nodes}
        # 过滤掉引用未知节点的非法边
        valid_edges = [e for e in edges if e.source in ids and e.target in ids]
        data.data.edges = valid_edges
        return len(valid_edges) >= 1
    if data.kind == "tree":
        nodes = data.data.nodes
        if len(nodes) < MIN_TREE_NODES:
            return False
        ids = {n.node_id for n in nodes}
        for n in nodes:
            if n.parent_id is not None and n.parent_id not in ids:
                n.parent_id = None
        return True
    if data.kind == "stats":
        return len(data.data.metrics) >= MIN_STATS_METRICS
    return False


def _truncate(text: str, limit: int) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip("，,。.;；、 ") + "…"


def _compact_master(master: MasterVisual) -> MasterVisual:
    """通览图只保留概览信息，精简冗余字数。"""
    for block in master.blocks:
        block.summary = _truncate(block.summary, MAX_MASTER_BLOCK_SUMMARY_CHARS)
        block.key_points = [
            _truncate(point, MAX_MASTER_KEY_POINT_CHARS)
            for point in block.key_points[:MAX_MASTER_BLOCK_KEY_POINTS]
            if point.strip()
        ]
        if block.highlight:
            block.highlight.tag = _truncate(block.highlight.tag, 10)
            block.highlight.value = _truncate(block.highlight.value, 30)

    for w in master.widgets:
        if w.kind == "cards":
            for item in w.data.items:
                item.summary = _truncate(item.summary, MAX_MASTER_BLOCK_SUMMARY_CHARS)
                item.key_points = [
                    _truncate(p, MAX_MASTER_KEY_POINT_CHARS)
                    for p in item.key_points[:MAX_MASTER_BLOCK_KEY_POINTS]
                    if p.strip()
                ]
                if item.highlight:
                    item.highlight.tag = _truncate(item.highlight.tag, 10)
                    item.highlight.value = _truncate(item.highlight.value, 30)
        elif w.kind == "timeline":
            w.data.events = w.data.events[:MAX_TIMELINE_EVENTS]
        elif w.kind == "table":
            w.data.columns = w.data.columns[:MAX_TABLE_COLUMNS]
            w.data.rows = w.data.rows[:MAX_TABLE_ROWS]
        elif w.kind == "stats":
            w.data.metrics = w.data.metrics[:MAX_STATS_METRICS]
    return master


def _trim_tree_nodes(nodes, limit: int):
    """按层级保留前 N 个节点，保证被保留节点的父节点仍然存在。"""
    selected = []
    selected_ids: set[str] = set()
    remaining = list(nodes)
    while remaining and len(selected) < limit:
        added = False
        for node in list(remaining):
            if node.parent_id is None or node.parent_id in selected_ids:
                selected.append(node)
                selected_ids.add(node.node_id)
                remaining.remove(node)
                added = True
                if len(selected) >= limit:
                    break
        if not added:
            break
    return selected


def _compact_visual(visual: SectionVisual) -> SectionVisual:
    """限制单个视觉的数据量，避免把整篇正文塞进一张图。"""
    data = visual.visual
    if data is None:
        return visual
    if data.kind == "timeline":
        data.data.events = data.data.events[:MAX_TIMELINE_EVENTS]
    elif data.kind == "table":
        columns = data.data.columns[:MAX_TABLE_COLUMNS]
        data.data.columns = columns
        data.data.rows = data.data.rows[:MAX_TABLE_ROWS]
        for row in data.data.rows:
            row.cells = row.cells[: len(columns)]
    elif data.kind == "flow":
        nodes = data.data.nodes[:MAX_FLOW_NODES]
        data.data.nodes = nodes
        ids = {node.node_id for node in nodes}
        edges = [
            edge
            for edge in data.data.edges
            if edge.source in ids and edge.target in ids
        ]
        data.data.edges = edges[:MAX_FLOW_EDGES]
    elif data.kind == "tree":
        data.data.nodes = _trim_tree_nodes(data.data.nodes, MAX_TREE_NODES)
    elif data.kind == "stats":
        data.data.metrics = data.data.metrics[:MAX_STATS_METRICS]
    return visual


def _limit_visuals(
    visuals: List[SectionVisual],
    warnings: List[str],
) -> List[SectionVisual]:
    if len(visuals) <= MAX_SECTION_VISUALS:
        return visuals
    keep = sorted(
        visuals,
        key=lambda v: (-v.confidence, v.section_id),
    )[:MAX_SECTION_VISUALS]
    keep_ids = {v.section_id for v in keep}
    dropped = [v.section_id for v in visuals if v.section_id not in keep_ids]
    warnings.append("visual density limit dropped: " + ",".join(dropped))
    order = {v.section_id: i for i, v in enumerate(visuals)}
    return sorted(keep, key=lambda v: order[v.section_id])


def validate_document(
    ir: VisualDocumentIR,
    parsed: ParsedMinutes,
) -> VisualDocumentIR:
    warnings = list(ir.warnings)
    known = {s.section_id for s in parsed.sections}

    master = ir.master
    if not _is_master_valid(master, parsed.sections):
        warnings.append("master validation failed; fallback applied")
        master = fallback_master(parsed)

    master = _compact_master(master)

    valid_visuals: List[SectionVisual] = []
    seen: set[str] = set()
    for item in ir.sections:
        if item.visual is None:
            continue
        if item.section_id not in known or item.section_id in seen:
            warnings.append(f"invalid section_id dropped: {item.section_id}")
            continue
        if not _valid_visual(item):
            warnings.append(f"invalid visual dropped: {item.section_id}")
            continue
        seen.add(item.section_id)
        valid_visuals.append(_compact_visual(item))

    valid_visuals = _limit_visuals(valid_visuals, warnings)
    return VisualDocumentIR(
        master=master,
        sections=valid_visuals,
        warnings=list(dict.fromkeys(warnings)),
    )


__all__ = ["validate_document"]
