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
