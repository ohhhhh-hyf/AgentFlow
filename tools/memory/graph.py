"""笔记知识图谱增量：同名节点合并，边按三元组去重；生成侧校验拦截无效数据。"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

GRAPH_DATA_HEADER = "已积累图谱数据："


def inject_graph(record: dict[str, Any]) -> str:
    """已积累图谱的注入文本。空图返回空串。"""
    graph = (record or {}).get("graph") or {}
    nodes = [n for n in (graph.get("nodes") or []) if isinstance(n, dict) and n.get("name")]
    if not nodes:
        return ""
    edges = [e for e in (graph.get("edges") or []) if isinstance(e, dict)]
    subject = str(record.get("subject") or record.get("project_key") or "").strip()
    lines = [
        "【已积累知识图谱（在此基础上增量补充；同名节点合并，不要丢掉已有节点）】",
        f"学科：{subject or graph.get('title') or ''}",
        f"已记录场次：{record.get('run_count') or 0}",
        f"title：{graph.get('title') or ''}",
        f"已有节点 {len(nodes)} 个、边 {len(edges)} 条。",
    ]
    for node in nodes[:40]:
        name = str(node.get("name") or "").strip()
        definition = str(node.get("definition") or "").strip()
        section = str(node.get("section") or "").strip()
        bit = f"- {name}"
        if section:
            bit += f"（{section}）"
        if definition:
            bit += f"：{definition[:40]}"
        lines.append(bit)
    if edges:
        lines.append("已有关系：")
        for edge in edges[:50]:
            src = str(edge.get("source") or "").strip()
            rel = str(edge.get("relation") or "").strip()
            tgt = str(edge.get("target") or "").strip()
            if src and rel and tgt:
                lines.append(f"- {src} {rel} {tgt}")
    payload = {
        "title": graph.get("title") or "",
        "nodes": nodes,
        "edges": [
            e
            for e in edges
            if isinstance(e, dict) and e.get("source") and e.get("target")
        ],
    }
    lines.append(GRAPH_DATA_HEADER)
    lines.append(json.dumps(payload, ensure_ascii=False))
    return "\n".join(lines)


def parse_graph_from_text(text: str) -> dict[str, Any]:
    """从注入块解析已积累图谱 JSON。"""
    raw = text or ""
    idx = raw.find(GRAPH_DATA_HEADER)
    if idx < 0:
        return {}
    rest = raw[idx + len(GRAPH_DATA_HEADER) :]
    start = rest.find("{")
    if start < 0:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(rest[start:])
    except json.JSONDecodeError:
        return {}
    if not isinstance(obj, dict):
        return {}
    nodes = obj.get("nodes") if isinstance(obj.get("nodes"), list) else []
    edges = obj.get("edges") if isinstance(obj.get("edges"), list) else []
    return {
        "title": str(obj.get("title") or "").strip(),
        "nodes": nodes,
        "edges": edges,
    }


def apply_graph_memory(draft: dict[str, Any], context: str) -> dict[str, Any]:
    """本场草稿与已积累图硬合并，保证旧节点不会在增量时丢失。"""
    old = parse_graph_from_text(context)
    if not old.get("nodes"):
        return dict(draft or {})
    merged = merge_graph({"graph": old}, draft or {})
    graph = dict(merged.get("graph") or draft or {})
    return mark_graph_origin(graph, old)


def mark_graph_origin(
    graph: dict[str, Any],
    old: dict[str, Any],
) -> dict[str, Any]:
    """给本场合并结果打 origin：history=旧图已有，new=本场新增。"""
    out = dict(graph or {})
    old_names = {
        _clean(node.get("name"))
        for node in (old.get("nodes") or [])
        if isinstance(node, dict) and _clean(node.get("name"))
    }
    old_edges = {
        _edge_key(edge)
        for edge in (old.get("edges") or [])
        if isinstance(edge, dict) and all(_edge_key(edge))
    }
    nodes: list[dict[str, Any]] = []
    for node in out.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        item = dict(node)
        name = _clean(item.get("name"))
        item["origin"] = "history" if name in old_names else "new"
        nodes.append(item)
    edges: list[dict[str, Any]] = []
    for edge in out.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        item = dict(edge)
        item["origin"] = "history" if _edge_key(item) in old_edges else "new"
        edges.append(item)
    out["nodes"] = nodes
    out["edges"] = edges
    return out


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def sanitize_graph(draft: dict[str, Any]) -> dict[str, Any]:
    """清洗图谱草稿（生成侧拦截，不修改入参）。

    - 节点：name 去空白；同名节点合并（后到字段覆盖空值，definition 取更长）
    - 边：source/relation/target 去空白；同三元组去重；悬空边（两端不在
      nodes）与无效边剥离并计数告警
    - 与导出侧（tools/knowledge_graph.py 的悬空边过滤）形成
      「生成侧拦截 + 导出侧兜底」双层，避免脏数据进入 memory / 产物
    """
    out = dict(draft or {})
    nodes_in = out.get("nodes") if isinstance(out.get("nodes"), list) else []
    edges_in = out.get("edges") if isinstance(out.get("edges"), list) else []

    node_map: dict[str, dict[str, Any]] = {}
    for node in nodes_in:
        if not isinstance(node, dict):
            continue
        name = _clean(node.get("name"))
        if not name:
            continue
        prev = node_map.get(name, {})
        merged = dict(prev)
        for key, value in node.items():
            if value not in (None, ""):
                merged[key] = value
        merged["name"] = name  # 规范化后的 name 强制写回
        old_def = str(prev.get("definition") or "").strip()
        new_def = str(merged.get("definition") or "").strip()
        if old_def and len(old_def) > len(new_def):
            merged["definition"] = old_def
        node_map[name] = merged

    nodes = list(node_map.values())
    node_names = set(node_map)

    edge_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    dropped = 0
    for edge in edges_in:
        if not isinstance(edge, dict):
            dropped += 1
            continue
        src = _clean(edge.get("source"))
        rel = _clean(edge.get("relation"))
        tgt = _clean(edge.get("target"))
        if not src or not rel or not tgt:
            dropped += 1
            continue
        if src not in node_names or tgt not in node_names:
            dropped += 1
            continue
        key = (src, rel, tgt)
        prev = edge_map.get(key, {})
        merged = dict(prev)
        for k, v in edge.items():
            if v not in (None, ""):
                merged[k] = v
        merged["source"] = src
        merged["relation"] = rel
        merged["target"] = tgt
        edge_map[key] = merged

    out["nodes"] = nodes
    out["edges"] = list(edge_map.values())
    if dropped:
        logger.warning(
            "知识图谱生成侧校验：剥离 %d 条无效/悬空/重复边（source/target 不在 nodes 或字段缺失）",
            dropped,
        )
    return out


def _node_key(node: dict[str, Any]) -> str:
    return str(node.get("name") or "").strip()


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(edge.get("source") or "").strip(),
        str(edge.get("relation") or "").strip(),
        str(edge.get("target") or "").strip(),
    )


def merge_graph(record: dict[str, Any], report: object) -> dict[str, Any]:
    """把本次图谱报告并入 record['graph']。"""
    rec = dict(record)
    incoming: dict[str, Any] = {}
    if hasattr(report, "model_dump"):
        dumped = report.model_dump()
        if isinstance(dumped, dict):
            incoming = dumped
    elif isinstance(report, dict):
        incoming = report
    if not incoming:
        return rec

    old = dict(rec.get("graph") or {})
    nodes: dict[str, dict[str, Any]] = {}
    for node in list(old.get("nodes") or []) + list(incoming.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        key = _node_key(node)
        if not key:
            continue
        prev = nodes.get(key, {})
        merged = dict(prev)
        merged.update({k: v for k, v in node.items() if v not in (None, "")})
        # 定义取更长的那条（通常信息更多）
        old_def = str(prev.get("definition") or "")
        new_def = str(node.get("definition") or "")
        if len(old_def) > len(new_def):
            merged["definition"] = old_def
        merged.pop("origin", None)
        nodes[key] = merged

    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in list(old.get("edges") or []) + list(incoming.get("edges") or []):
        if not isinstance(edge, dict):
            continue
        key = _edge_key(edge)
        if not all(key):
            continue
        if key[0] not in nodes or key[2] not in nodes:
            continue
        prev = edges.get(key, {})
        merged = dict(prev)
        merged.update({k: v for k, v in edge.items() if v not in (None, "")})
        merged.pop("origin", None)
        edges[key] = merged

    subject = str(rec.get("subject") or rec.get("project_key") or "").strip()
    title = subject or str(incoming.get("title") or old.get("title") or "").strip()
    rec["graph"] = {
        "title": title,
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
    }
    return rec


__all__ = [
    "GRAPH_DATA_HEADER",
    "apply_graph_memory",
    "inject_graph",
    "mark_graph_origin",
    "merge_graph",
    "parse_graph_from_text",
    "sanitize_graph",
]
