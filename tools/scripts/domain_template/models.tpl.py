"""{{DOMAIN}} 领域数据模型（手写区 + 生成区）。

手写区：ModelMixin / UserIdentity / is_objective_perspective /
{{STATE_CLASS}}（LangGraph 共享状态）/ reducer；
生成区（由 tools/scripts/sync_domain.py 生成）：生成模型 / 审核模型 / Report 校验。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Annotated, Any, Literal, TypedDict

from tools.validation import (
    OutputValidationError,
    _action,
    _choice,
    _exact_fields,
    _review_check,
    _string,
    _string_list,
    validate_supervisor_semantics,
)


class ModelMixin:
    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UserIdentity(ModelMixin):
    """用户画像（与 perspective 公共组件对齐：perspective 字段决定视角模式）。"""

    name: str | None = None
    role: str | None = None
    department: str | None = None
    responsibilities: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    context: str | None = None
    # "objective" = 客观全员视角；缺省或其它值 = 具体用户视角
    perspective: str | None = None


def is_objective_perspective(user: UserIdentity | dict | None) -> bool:
    """画像 perspective 为 objective 时走客观全员口径。"""
    if user is None:
        return False
    data = user.model_dump() if hasattr(user, "model_dump") else dict(user)
    return str(data.get("perspective") or "").strip().lower() == "objective"


# ── 生成模型生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

# ── 生成模型生成区结束 ──

# ── 审核模型生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

# ── 审核模型生成区结束 ──

# ── Report 校验生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

# ── Report 校验生成区结束 ──


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
