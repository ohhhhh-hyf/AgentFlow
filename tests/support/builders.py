"""测试数据构造器。

Step 5/6 会把各测试文件里重复的状态与草稿构造逻辑逐步收敛到这里。
当前先提供最小可用的 Minutes 草稿构造器，避免继续复制同一份 7 字段字典。
"""
from __future__ import annotations

from typing import Any


def minutes_draft(**overrides: Any) -> dict[str, Any]:
    """返回满足 Minutes 契约的最小 7 字段草稿。"""
    draft: dict[str, Any] = {
        "headline": "测试会议",
        "executive_summary": ["测试概览"],
        "key_decisions": [],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
        "history_comparison": [],
    }
    draft.update(overrides)
    return draft
