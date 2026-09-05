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
    import re

    s = " ".join(str(value or "").split()).strip()
    if not s:
        return ""
    # 多轮清洗：序号、口语前缀与外层引号互为嵌套时一并剥离
    for _ in range(3):
        s = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩\d]+[\.、\s\-_]*", "", s).strip()
        s = re.sub(r"^(口诀|错题记录|常见限制|老师敲黑板|课尾预告)[:：\s]*", "", s).strip()
        s = re.sub(r"^[\"“”'《]+|[\"“”'》]+$", "", s).strip()
    return s


def _resolve_canonical_node(raw_name: str, valid_names: set[str]) -> str | None:
    import re

    if raw_name in valid_names:
        return raw_name
    stripped = re.sub(r"[^\w\u4e00-\u9fa5]", "", raw_name)
    for vn in valid_names:
        if stripped == re.sub(r"[^\w\u4e00-\u9fa5]", "", vn):
            return vn
    # 唯一包含匹配（长度 >= 3）
    candidates = [
        vn
        for vn in valid_names
        if (len(vn) >= 3 and vn in raw_name) or (len(raw_name) >= 3 and raw_name in vn)
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


_VALID_NODE_TYPES = {"concept", "formula", "method", "problem", "pitfall"}
_RELATION_ALIASES = {
    "依赖": "前提",
    "前置": "前提",
    "基础": "前提",
    "应用": "用于",
    "使用": "用于",
    "包括": "包含",
    "涵盖": "包含",
    "归属于": "属于",
    "归入": "属于",
    "等价": "等价于",
    "区别": "区别于",
    "不同于": "区别于",
    "引起": "导致",
}


def sanitize_graph(draft: dict[str, Any]) -> dict[str, Any]:
    """清洗图谱草稿（生成侧拦截，不修改入参）。

    - 节点：name 清除序号/修饰前缀/空白；同名节点合并；剔除伪概念章节标题；type 归一化
    - 边：source/relation/target 去空白与规范化对齐；过滤自环；别名归一；过滤“相关”；
      同三元组去重；悬空边与无效边剥离并计数告警
    """
    out = dict(draft or {})
    nodes_in = out.get("nodes") if isinstance(out.get("nodes"), list) else []
    edges_in = out.get("edges") if isinstance(out.get("edges"), list) else []

    # 统计各 section 出现频次，用于过滤误作节点的章节全名
    section_counts: dict[str, int] = {}
    for node in nodes_in:
        if isinstance(node, dict):
            sec = str(node.get("section") or "").strip()
            if sec:
                section_counts[sec] = section_counts.get(sec, 0) + 1

    node_map: dict[str, dict[str, Any]] = {}
    for node in nodes_in:
        if not isinstance(node, dict):
            continue
        name = _clean(node.get("name"))
        if not name:
            continue
        sec = str(node.get("section") or "").strip()
        # 若节点名字完全等于某个章节名且该章节已有多个节点，跳过该伪节点
        if name in section_counts and section_counts[name] > 1 and sec in ("", "未分组", name):
            continue

        prev = node_map.get(name, {})
        merged = dict(prev)
        for key, value in node.items():
            if value not in (None, ""):
                merged[key] = value
        merged["name"] = name

        # 归一化 type
        ntype = str(merged.get("type") or "").strip().lower()
        if ntype not in _VALID_NODE_TYPES:
            full_text = f"{name} {merged.get('definition', '')}"
            if any(k in full_text for k in ("注意", "误区", "陷阱", "易错", "限制", "条件", "前提", "大于", "小于", "不等于", "≠", "对称", "特殊值")):
                ntype = "pitfall"
            elif any(k in full_text for k in ("公式", "定理", "恒等式", "法则")):
                ntype = "formula"
            elif any(k in full_text for k in ("法", "技巧", "步骤", "求法")):
                ntype = "method"
            elif any(k in full_text for k in ("题", "考法", "求值", "值域", "定义域", "最值", "比较大小", "解方程", "解不等式", "范围")):
                ntype = "problem"
            else:
                ntype = "concept"
        merged["type"] = ntype

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
        raw_src = _clean(edge.get("source"))
        rel = _clean(edge.get("relation"))
        raw_tgt = _clean(edge.get("target"))
        if not raw_src or not rel or not raw_tgt:
            dropped += 1
            continue

        # 规范名对齐纠偏（模糊对齐）
        src = _resolve_canonical_node(raw_src, node_names)
        tgt = _resolve_canonical_node(raw_tgt, node_names)
        if not src or not tgt:
            dropped += 1
            continue

        # 过滤自环
        if src == tgt:
            dropped += 1
            continue

        # 归一化关系动词
        if rel in _RELATION_ALIASES:
            rel = _RELATION_ALIASES[rel]
        # 淘汰模糊的“相关”
        if rel == "相关":
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
            "知识图谱生成侧校验：剥离 %d 条无效/悬空/自环/重复/弱相关边（source/target 不在 nodes 或字段缺失）",
            dropped,
        )
    return out


def _node_key(node: dict[str, Any]) -> str:
    return _clean(node.get("name"))


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _clean(edge.get("source")),
        str(edge.get("relation") or "").strip(),
        _clean(edge.get("target")),
    )


def merge_graph(record: dict[str, Any], report: object) -> dict[str, Any]:
    """把本次图谱报告并入 record['graph']（规范化去重与防冗余雪球）。"""
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
        name = _clean(node.get("name"))
        if not name:
            continue
        # 若能匹配到已收录的标准名称，则合入既有条目，防止同义短语膨胀
        canon = _resolve_canonical_node(name, set(nodes.keys()))
        key = canon if canon else name

        prev = nodes.get(key, {})
        merged = dict(prev)
        merged.update({k: v for k, v in node.items() if v not in (None, "")})
        merged["name"] = key
        # 定义取更长的那条（通常信息更多）
        old_def = str(prev.get("definition") or "")
        new_def = str(node.get("definition") or "")
        if len(old_def) > len(new_def):
            merged["definition"] = old_def
        merged.pop("origin", None)
        nodes[key] = merged

    node_names = set(nodes)
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in list(old.get("edges") or []) + list(incoming.get("edges") or []):
        if not isinstance(edge, dict):
            continue
        raw_src = _clean(edge.get("source"))
        rel = str(edge.get("relation") or "").strip()
        raw_tgt = _clean(edge.get("target"))
        src = _resolve_canonical_node(raw_src, node_names)
        tgt = _resolve_canonical_node(raw_tgt, node_names)
        if not src or not tgt or src == tgt:
            continue
        key = (src, rel, tgt)
        prev = edges.get(key, {})
        merged = dict(prev)
        merged.update({k: v for k, v in edge.items() if v not in (None, "")})
        merged["source"] = src
        merged["relation"] = rel
        merged["target"] = tgt
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
