# -*- coding: utf-8 -*-
"""通用文本/列表工具 —— 多模块复用的最小公共函数。

从 checklist/catalog/quiz/review 等模块收敛而来，语义与原实现完全一致
（旧模块以别名 import 保持调用点不变）。
"""
from __future__ import annotations

from typing import Any


def clean_text(text: object) -> str:
    """归一空白并去首尾空格；None/空 → ""。"""
    return " ".join(str(text or "").split()).strip()


def as_text_list(value: object) -> list[str]:
    """list[str] 清洗（去空项）；单 str → [str]；其他 → []。"""
    if isinstance(value, list):
        return [clean_text(x) for x in value if clean_text(x)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def as_dict_list(value: object) -> list[dict[str, Any]]:
    """只保留 list 中的 dict 项；其他 → []。"""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
