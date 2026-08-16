"""手写基础模型：Mixin 与用户画像。生成模型见 models_generated.py。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


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
    # 画像类型：null/缺省 = 真人画像（name 为真实姓名）；"role_template" = 大众职业模板（name 为职业名）
    persona_type: str | None = None
    # 真人画像引用的职业模板名（如 "developer" → {profile_dir}/developer_profile.json）；合并时加载
    role_template: str | None = None
    # ── 视角画像扩展字段（客观/个人视角通用承载）────────────────
    scope: str | None = None          # 覆盖面：全员 / 跨组 / 组织级
    principles: list[str] = field(default_factory=list)   # 立场与记录原则
    focus_areas: list[str] = field(default_factory=list)  # 重点关注领域
    constraints: list[str] = field(default_factory=list)  # 边界与约束
    values: list[str] = field(default_factory=list)       # 价值优先级
    output_style: str | None = None   # 输出风格与语言要求


def is_objective_perspective(user: UserIdentity | dict | None) -> bool:
    """画像 perspective 为 objective 时走客观全员口径。"""
    if user is None:
        return False
    data = user.model_dump() if hasattr(user, "model_dump") else dict(user)
    return str(data.get("perspective") or "").strip().lower() == "objective"

