"""PersonalPerspective 数据模型：个人单线 minutes 专用视角模型。

字段严格冻结为 9 个：
confidence + 8 个内容字段。旧 PerspectiveModeling 的 11 字段不在这里复用，
避免个人路径和 role_template / notes / 多线继续耦合。
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Literal

from core.schema.validation import (
    _choice,
    _exact_fields,
    _string,
    _string_list,
)

from .models import ModelMixin

PERSONAL_PERSPECTIVE_FIELDS = (
    "confidence",
    "personal_summary",
    "focus_points",
    "possible_actions",
    "collaborations",
    "concerns",
    "data_gaps",
    "focus_risks",
    "open_questions",
)


@dataclass
class PersonalPerspective(ModelMixin):
    """个人视角建模输出（浅校验：第一层键与类型）。"""

    confidence: Literal["high", "medium", "low"]
    personal_summary: str
    focus_points: list[str] = field(default_factory=list)
    possible_actions: list[str] = field(default_factory=list)
    collaborations: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)
    focus_risks: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "PersonalPerspective":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _choice(data["confidence"], {"high", "medium", "low"}, "confidence")
        _string(data["personal_summary"], "personal_summary")
        for name in PERSONAL_PERSPECTIVE_FIELDS[2:]:
            _string_list(data[name], name)
        return cls(**data)


EMPTY_PERSONAL_PERSPECTIVE = {
    "confidence": "low",
    "personal_summary": "",
    "focus_points": [],
    "possible_actions": [],
    "collaborations": [],
    "concerns": [],
    "data_gaps": [],
    "focus_risks": [],
    "open_questions": [],
}


__all__ = [
    "PERSONAL_PERSPECTIVE_FIELDS",
    "PersonalPerspective",
    "EMPTY_PERSONAL_PERSPECTIVE",
]
