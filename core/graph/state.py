"""core.graph.state —— LangGraph 共享状态与 Reducer 合并算法。"""
from __future__ import annotations

from typing import Any, TypedDict


def merge_degraded(a: bool | None, b: bool | None) -> bool:
    """quality_degraded 的 LangGraph reducer：任一为 True 则降级。"""
    return bool(a) or bool(b)


def merge_lines(a: dict | None, b: dict | None) -> dict:
    """任务线子空间（lines）的 LangGraph reducer：按线名浅合并。"""
    out = {name: dict(patch or {}) for name, patch in (a or {}).items()}
    for name, patch in (b or {}).items():
        cur = out.get(name)
        if isinstance(cur, dict) and isinstance(patch, dict):
            merged = dict(cur)
            merged.update(patch)
            out[name] = merged
        else:
            out[name] = patch
    return out


class BaseState(TypedDict, total=False):
    """跨领域 State 共有基础字段。"""

    transcript: str
    user: dict
    objective_perspective: bool
    quality_degraded: bool
    lines: dict[str, dict[str, Any]]


__all__ = ["BaseState", "merge_degraded", "merge_lines"]
