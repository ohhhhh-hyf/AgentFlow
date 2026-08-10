"""perspective 公共包的模型定义（生成区由 perspective/gen_models.py 管理）。

模型类从 meeting 域 codegen 生成区抽取：作为跨 domain 公共底座，
不应由某个 domain 的 codegen 管理，故由本包自带迷你生成器
（gen_models.py，复用 tools/scripts/codegen.py 的生成函数）维护。

改字段流程：只改 contracts.py 的 fields → 运行
    python perspective/gen_models.py
→ 模型类 / validate / EMPTY_PERSPECTIVE_MODELING 自动同步。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal

from tools.validation import (
    _choice,
    _exact_fields,
    _string,
    _string_list,
)


class ModelMixin:
    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


# ── 模型生成区：由 perspective/gen_models.py 生成，勿手改 ──

@dataclass
class PerspectiveModeling(ModelMixin):
    """PerspectiveModeling输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    confidence: Literal["high", "medium", "low"]
    name: str
    inferred_role: str
    responsibilities: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    relevant_topics: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "PerspectiveModeling":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _choice(data["confidence"], {"high", "medium", "low"}, "confidence")
        _string(data["name"], "name")
        _string(data["inferred_role"], "inferred_role")
        _string_list(data["responsibilities"], "responsibilities")
        _string_list(data["goals"], "goals")
        _string_list(data["concerns"], "concerns")
        _string_list(data["relevant_topics"], "relevant_topics")
        _string_list(data["evidence"], "evidence")
        return cls(**data)


EMPTY_PERSPECTIVE_MODELING = {
    "confidence": "high",
    "name": "",
    "inferred_role": "",
    "responsibilities": [],
    "goals": [],
    "concerns": [],
    "relevant_topics": [],
    "evidence": [],
}


# ── 模型生成区结束 ──
