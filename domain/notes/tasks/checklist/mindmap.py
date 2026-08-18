"""checklist 思维导图：用 meeting/mindmap 同一套大纲规则生成 markmap。"""
from __future__ import annotations

from typing import Any

from tools.mindmap import sanitize_mindmap_outline

from .select import _as_list, _clean

_GRADE = {"S": "核心", "A": "重点", "B": "简要", "C": "结构"}


def _short(text: object, limit: int = 22) -> str:
    raw = _clean(text)
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)].rstrip("，。；;、, ") + "…"


def build_checklist_mindmap_outline(
    draft: dict[str, Any],
    cards: list[dict[str, Any]] | None = None,
) -> str:
    items = [c for c in (cards or draft.get("cards") or []) if isinstance(c, dict) and _clean(c.get("name"))]
    course = _clean(draft.get("course")) or "复习清单"
    lines = [f"# {course} · 复习清单", ""]
    tree: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for card in items:
        chapter = _clean(card.get("chapter")) or "本章"
        topic = _clean(card.get("topic")) or "主题"
        tree.setdefault(chapter, {}).setdefault(topic, []).append(card)
    for chapter, topics in tree.items():
        lines.append(f"## {chapter}")
        for topic, rows in topics.items():
            lines.append(f"### {topic}")
            for card in rows:
                grade = _GRADE.get(str(card.get("session_priority") or ""), "")
                name = _clean(card.get("name"))
                title = f"{name}（{grade}）" if grade else name
                lines.append(f"#### {title}")
                for item in _as_list(card.get("session_focus_items"))[:4]:
                    lines.append(f"- {_short(item)}")
                if not _as_list(card.get("session_focus_items")):
                    for item in _as_list(card.get("knowledge_items"))[:3]:
                        lines.append(f"- {_short(item)}")
            lines.append("")
    return sanitize_mindmap_outline("\n".join(lines).strip())


__all__ = ["build_checklist_mindmap_outline"]
