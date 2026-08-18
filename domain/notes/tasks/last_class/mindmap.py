"""last_class 思维导图：用 meeting/mindmap 同一套大纲规则生成 markmap。

输入是已抽取的 focus_points，输出是 sanitize 后的 Markdown 大纲
（# / ## / ### / -），再交给 tools.mindmap 渲染可编辑 HTML。
"""
from __future__ import annotations

from typing import Any

from tools.mindmap import sanitize_mindmap_outline

from .kb import _as_list, _clean


def _short(text: object, limit: int = 20) -> str:
    raw = _clean(text)
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)].rstrip("，。；;、, ") + "…"


def build_last_class_mindmap_outline(
    draft: dict[str, Any],
    subject: str = "",
    points: list[dict[str, Any]] | None = None,
) -> str:
    """按 meeting/mindmap 约定把考点编成树状大纲。"""
    items = list(points or [])
    if not items:
        raw = draft.get("focus_points") or []
        items = [p for p in raw if isinstance(p, dict) and _clean(p.get("name"))]
    title = f"期末复习清单 · {subject}" if (subject or "").strip() else "期末复习清单"
    lines: list[str] = [f"# {title}", ""]

    for degree in ("必考", "重点", "了解"):
        group = [p for p in items if _clean(p.get("degree")) == degree]
        if not group:
            continue
        lines.append(f"## {degree}")
        for point in group:
            name = _clean(point.get("name"))
            lines.append(f"### {name}")
            mastery = _clean(point.get("mastery"))
            if mastery:
                lines.append(f"- {_short(mastery)}")
            for fact in _as_list(point.get("key_facts"))[:3]:
                lines.append(f"- {_short(fact, 22)}")
            for step in _as_list(point.get("methods"))[:2]:
                lines.append(f"- {_short(step, 22)}")
            trap = _clean(point.get("explain_trap"))
            if trap:
                lines.append(f"- 易错：{_short(trap, 18)}")
            examples = _as_list(point.get("examples")) or (
                [_clean(point.get("example"))] if _clean(point.get("example")) else []
            )
            if examples and degree != "了解":
                lines.append(f"- 例：{_short(examples[0], 18)}")
            for action in _as_list(point.get("practice"))[:2]:
                lines.append(f"- {_short(action)}")
        lines.append("")

    strategy = _clean(draft.get("strategy"))
    if strategy:
        lines.append("## 复习策略")
        parts = [p for p in strategy.replace("。", "。\n").splitlines() if _clean(p)]
        if not parts:
            parts = [strategy]
        for part in parts[:5]:
            leaf = _clean(part).strip("。；;")
            if leaf:
                lines.append(f"- {_short(leaf, 28)}")
        lines.append("")

    return sanitize_mindmap_outline("\n".join(lines).strip())


__all__ = ["build_last_class_mindmap_outline"]
