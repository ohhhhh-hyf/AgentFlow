"""把一段话对到知识库里的文件和原文。库空或检索失败则返回空，不准编出处。"""
from __future__ import annotations

import os
import re
from typing import Any


def open_knowledge():
    """能开库就开；缺 key / 依赖失败返回 None（调用方走旧逻辑）。"""
    try:
        from tools.knowledge.tool import get_knowledge
    except Exception:
        return None
    fake = os.getenv("KNOWLEDGE_FAKE", "").strip().lower() in {"1", "true", "yes"}
    try:
        return get_knowledge(fake=fake)
    except Exception:
        return None


def library_has_docs(kb: Any) -> bool:
    if kb is None:
        return False
    try:
        files = kb.list_files()
    except Exception:
        return False
    return bool(files)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _overlaps(query: str, excerpt: str) -> bool:
    """至少有一段连续 4 字同时出现在查询和摘录里，避免把无关块当出处。"""
    return _overlap_score(query, excerpt) > 0


def _overlap_score(query: str, excerpt: str) -> int:
    """重合越长分越高，用来在多份课件里挑更贴的那一块。"""
    q = _compact(query)
    e = _compact(excerpt)
    if not q or not e:
        return 0
    if q in e or e in q:
        return 1000 + min(len(q), len(e))
    limit = min(16, len(q), len(e))
    for size in range(limit, 3, -1):
        grams = {q[i : i + size] for i in range(0, len(q) - size + 1)}
        hit = sum(1 for gram in grams if gram in e)
        if hit:
            return size * 20 + hit
    return 0


def _pack(meta: dict, excerpt: str, score: object) -> dict[str, Any] | None:
    fname = str((meta or {}).get("source") or "").strip()
    if not fname:
        return None
    page = (meta or {}).get("page")
    text = " ".join(str(excerpt or "").split())
    if len(text) > 80:
        text = text[:79] + "…"
    return {
        "file": fname,
        "page": "" if page in (None, "") else str(page),
        "excerpt": text,
        "score": score,
    }


def cite_text(kb: Any, text: str, *, top_k: int = 3) -> list[dict[str, Any]]:
    """检索出处。只返回库里真有、且和查询对得上的命中。"""
    query = " ".join(str(text or "").split()).strip()
    if kb is None or len(query) < 4:
        return []
    packed: list[dict[str, Any]] = []
    try:
        scored: list[tuple[int, dict[str, Any]]] = []
        for chunk in kb.list_chunks():
            body = str(chunk.get("text") or "")
            score = _overlap_score(query, body)
            if score <= 0:
                continue
            item = _pack(chunk.get("metadata") or {}, body, score)
            if item:
                scored.append((score, item))
        scored.sort(key=lambda pair: -pair[0])
        packed = [item for _, item in scored[:top_k]]
    except Exception:
        packed = []
    if packed:
        return packed
    try:
        hits = kb.locate(query, top_k=top_k)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for hit in hits:
        excerpt = str(getattr(hit, "text", "") or "")
        if not _overlaps(query, excerpt):
            continue
        item = _pack(getattr(hit, "metadata", None) or {}, excerpt, getattr(hit, "score", None))
        if item:
            out.append(item)
    return out


def format_cite_line(hit: dict[str, Any]) -> str:
    fname = str(hit.get("file") or "未知文件")
    page = str(hit.get("page") or "").strip()
    if page:
        return f"{fname} 第{page}页"
    return fname
