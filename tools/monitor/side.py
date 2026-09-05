"""知识库 / 记忆的进程内计数，供 TaskMonitor 做基线差值。

不记录正文。任何异常都吞掉，避免监控拖垮主流程。
"""
from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_INT_KEYS = (
    "kb_ingest_calls",
    "kb_ingest_files",
    "kb_chunks_added",
    "kb_chunks_removed",
    "kb_chunks_unchanged",
    "kb_search_calls",
    "kb_search_hits",
    "kb_search_empty",
    "kb_cite_calls",
    "kb_cite_hits",
    "kb_scan_calls",
    "kb_scan_chunks",
    "embed_calls",
    "embed_tokens",
    "mem_prepare_calls",
    "mem_bound",
    "mem_unbound",
    "mem_created",
    "mem_inject_chars",
    "mem_strong",
    "mem_hits",
    "mem_persist_calls",
    "mem_persist_ok",
    "mem_persist_skip",
    "mem_embed_calls",
    "mem_embed_hits",
    "mem_embed_fail",
)
_FLOAT_KEYS = (
    "kb_ingest_seconds",
    "kb_search_seconds",
)
_STR_KEYS = (
    "kb_last_collection",
    "mem_last_project",
)
_LAST_INT_KEYS = (
    "mem_run_count",
)


def _empty() -> dict[str, Any]:
    data: dict[str, Any] = {key: 0 for key in _INT_KEYS}
    data.update({key: 0 for key in _LAST_INT_KEYS})
    data.update({key: 0.0 for key in _FLOAT_KEYS})
    data.update({key: "" for key in _STR_KEYS})
    return data


_stats = _empty()


def snapshot() -> dict[str, Any]:
    with _lock:
        return dict(_stats)


def _bump(**kwargs: Any) -> None:
    with _lock:
        for key, value in kwargs.items():
            if key in _INT_KEYS:
                _stats[key] = int(_stats.get(key) or 0) + int(value or 0)
            elif key in _LAST_INT_KEYS:
                _stats[key] = int(value or 0)
            elif key in _FLOAT_KEYS:
                _stats[key] = float(_stats.get(key) or 0.0) + float(value or 0.0)
            elif key in _STR_KEYS and value:
                _stats[key] = str(value)


def record_embed(*, calls: int = 1, tokens: int = 0) -> None:
    """记录 embedding 模型消耗（调用次数 / 输入 token 数）。

    供知识库/记忆等所有 embedding 调用方使用；与 LLM 的 usage 分开统计。
    任何异常都吞掉，避免监控拖垮主流程。
    """
    try:
        _bump(embed_calls=calls, embed_tokens=tokens)
    except Exception:  # noqa: BLE001
        pass


def record_knowledge_ingest(
    *,
    files: int = 1,
    added: int = 0,
    removed: int = 0,
    unchanged: int = 0,
    seconds: float = 0.0,
    collection: str = "",
) -> None:
    try:
        _bump(
            kb_ingest_calls=1,
            kb_ingest_files=files,
            kb_chunks_added=added,
            kb_chunks_removed=removed,
            kb_chunks_unchanged=unchanged,
            kb_ingest_seconds=seconds,
            kb_last_collection=collection,
        )
    except Exception:  # noqa: BLE001
        return


def record_knowledge_search(
    *,
    hits: int = 0,
    seconds: float = 0.0,
    collection: str = "",
    kind: str = "search",
) -> None:
    try:
        empty = 1 if hits <= 0 else 0
        if kind == "cite":
            _bump(
                kb_cite_calls=1,
                kb_cite_hits=hits,
                kb_search_calls=1,
                kb_search_hits=hits,
                kb_search_empty=empty,
                kb_search_seconds=seconds,
                kb_last_collection=collection,
            )
        elif kind == "scan":
            _bump(
                kb_scan_calls=1,
                kb_scan_chunks=hits,
                kb_last_collection=collection,
            )
        else:
            _bump(
                kb_search_calls=1,
                kb_search_hits=hits,
                kb_search_empty=empty,
                kb_search_seconds=seconds,
                kb_last_collection=collection,
            )
    except Exception:  # noqa: BLE001
        return


def record_memory_prepare(
    *,
    bound: bool,
    created: bool = False,
    strong: int = 0,
    hits: int = 0,
    inject_chars: int = 0,
    project_id: str = "",
) -> None:
    try:
        _bump(
            mem_prepare_calls=1,
            mem_bound=1 if bound else 0,
            mem_unbound=0 if bound else 1,
            mem_created=1 if created else 0,
            mem_strong=strong,
            mem_hits=hits,
            mem_inject_chars=inject_chars,
            mem_last_project=project_id,
        )
    except Exception:  # noqa: BLE001
        return


def record_memory_persist(
    *,
    ok: bool,
    run_count: int = 0,
    project_id: str = "",
) -> None:
    try:
        _bump(
            mem_persist_calls=1,
            mem_persist_ok=1 if ok else 0,
            mem_persist_skip=0 if ok else 1,
            mem_run_count=run_count,
            mem_last_project=project_id,
        )
    except Exception:  # noqa: BLE001
        return


def record_memory_embed(
    *,
    ok: bool = True,
    hits: int = 0,
    calls: int = 0,
) -> None:
    """记忆向量索引调用计数（归属/摘录检索 + 同步）。"""
    try:
        _bump(
            mem_embed_calls=calls,
            mem_embed_hits=hits,
            mem_embed_fail=0 if ok else 1,
        )
    except Exception:  # noqa: BLE001
        return


def diff_side(base: dict[str, Any] | None, now: dict[str, Any] | None) -> dict[str, Any]:
    before = base or {}
    after = now or {}
    out: dict[str, Any] = {}
    for key in _INT_KEYS:
        out[key] = int(after.get(key) or 0) - int(before.get(key) or 0)
    for key in _FLOAT_KEYS:
        out[key] = round(float(after.get(key) or 0.0) - float(before.get(key) or 0.0), 3)
    for key in _LAST_INT_KEYS:
        out[key] = int(after.get(key) or 0)
    for key in _STR_KEYS:
        out[key] = str(after.get(key) or "")
    return out


def split_side(diff: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    knowledge = {
        "ingest_calls": diff.get("kb_ingest_calls") or 0,
        "ingest_files": diff.get("kb_ingest_files") or 0,
        "chunks_added": diff.get("kb_chunks_added") or 0,
        "chunks_removed": diff.get("kb_chunks_removed") or 0,
        "chunks_unchanged": diff.get("kb_chunks_unchanged") or 0,
        "ingest_seconds": diff.get("kb_ingest_seconds") or 0.0,
        "search_calls": diff.get("kb_search_calls") or 0,
        "search_hits": diff.get("kb_search_hits") or 0,
        "search_empty": diff.get("kb_search_empty") or 0,
        "search_seconds": diff.get("kb_search_seconds") or 0.0,
        "cite_calls": diff.get("kb_cite_calls") or 0,
        "cite_hits": diff.get("kb_cite_hits") or 0,
        "scan_calls": diff.get("kb_scan_calls") or 0,
        "scan_chunks": diff.get("kb_scan_chunks") or 0,
        "collection": diff.get("kb_last_collection") or "",
        "embed_calls": diff.get("embed_calls") or 0,
        "embed_tokens": diff.get("embed_tokens") or 0,
    }
    memory = {
        "prepare_calls": diff.get("mem_prepare_calls") or 0,
        "bound": diff.get("mem_bound") or 0,
        "unbound": diff.get("mem_unbound") or 0,
        "created": diff.get("mem_created") or 0,
        "inject_chars": diff.get("mem_inject_chars") or 0,
        "strong": diff.get("mem_strong") or 0,
        "hits": diff.get("mem_hits") or 0,
        "persist_calls": diff.get("mem_persist_calls") or 0,
        "persist_ok": diff.get("mem_persist_ok") or 0,
        "persist_skip": diff.get("mem_persist_skip") or 0,
        "run_count": diff.get("mem_run_count") or 0,
        "project_id": diff.get("mem_last_project") or "",
        "embed_calls": diff.get("mem_embed_calls") or 0,
        "embed_hits": diff.get("mem_embed_hits") or 0,
        "embed_fail": diff.get("mem_embed_fail") or 0,
    }
    return knowledge, memory


__all__ = [
    "diff_side",
    "record_embed",
    "record_knowledge_ingest",
    "record_knowledge_search",
    "record_memory_embed",
    "record_memory_persist",
    "record_memory_prepare",
    "snapshot",
    "split_side",
]
