"""IR 校验：保真、覆盖、密度、数据完整性。"""
from __future__ import annotations

from typing import Iterable, List

from ..config import (
    MAX_SECTION_VISUALS,
    MIN_FLOW_EDGES,
    MIN_FLOW_NODES,
    MIN_STATS_METRICS,
    MIN_TABLE_COLUMNS,
    MIN_TABLE_ROWS,
    MIN_TIMELINE_EVENTS,
    MIN_TREE_NODES,
)
from ..agents.master import _coverage_ok, fallback_master
from ..models.ir import SectionVisual, VisualDocumentIR
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
    if not _evidence_of(visual):
        return False
    if data.kind == "timeline":
        return len(data.data.events) >= MIN_TIMELINE_EVENTS
    if data.kind == "table":
        columns = data.data.columns
        rows = data.data.rows
        if len(columns) < MIN_TABLE_COLUMNS or len(rows) < MIN_TABLE_ROWS:
            return False
        return all(len(row.cells) == len(columns) for row in rows)
    if data.kind == "flow":
        nodes = data.data.nodes
        edges = data.data.edges
        if len(nodes) < MIN_FLOW_NODES or len(edges) < MIN_FLOW_EDGES:
            return False
        ids = {n.node_id for n in nodes}
        return all(e.source in ids and e.target in ids for e in edges)
    if data.kind == "tree":
        nodes = data.data.nodes
        if len(nodes) < MIN_TREE_NODES:
            return False
        ids = {n.node_id for n in nodes}
        if any(n.parent_id is not None and n.parent_id not in ids for n in nodes):
            return False
        # 检测环
        by_id = {n.node_id: n for n in nodes}
        for node in nodes:
            seen = set()
            cur = node
            while cur.parent_id is not None:
                if cur.node_id in seen:
                    return False
                seen.add(cur.node_id)
                cur = by_id.get(cur.parent_id)
                if cur is None:
                    return False
        return True
    if data.kind == "stats":
        return len(data.data.metrics) >= MIN_STATS_METRICS
    return False


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
    if (
        not master.headline.strip()
        or not master.blocks
        or not _coverage_ok(master, parsed.sections)
    ):
        warnings.append("master coverage invalid; fallback applied")
        master = fallback_master(parsed)
    master.metrics = [m for m in master.metrics if m.evidence.strip()]

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
        valid_visuals.append(item)

    valid_visuals = _limit_visuals(valid_visuals, warnings)
    return VisualDocumentIR(
        master=master,
        sections=valid_visuals,
        warnings=list(dict.fromkeys(warnings)),
    )


__all__ = ["validate_document"]
