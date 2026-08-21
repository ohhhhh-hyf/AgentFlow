"""{{DOMAIN}} 领域数据模型（手写）。生成模型在 models_generated.py。"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from .models_base import ModelMixin, UserIdentity, is_objective_perspective
from .models_generated import *  # noqa: F403


# ── LangGraph 共享状态 ────────────────────────────────────────


def _merge_degraded(a: bool | None, b: bool | None) -> bool:
    """reducer：quality_degraded 跨节点累积（任一节点降级即整体降级）。"""
    return bool(a) or bool(b)


def _merge_lines(a: dict | None, b: dict | None) -> dict:
    """reducer：lines[线名] 跨节点按子键合并（不同线、不同子键互不覆盖）。"""
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


class {{STATE_CLASS}}(TypedDict, total=False):
    """LangGraph 共享状态（跨节点传递）。

    通用字段：transcript / user / objective_perspective / perspective_profile
    （perspective 公共组件输出）/ lines / quality_degraded / templates。
    领域专属字段（如核心理解结果）在此追加。
    """

    transcript: str
    user: dict
    objective_perspective: bool
    perspective_profile: dict
    lines: Annotated[dict[str, dict], _merge_lines]
    quality_degraded: Annotated[bool, _merge_degraded]
    templates: dict[str, str]
    line_modes: dict[str, str]
    line_extra: dict[str, str]
