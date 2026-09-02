"""Build high-confidence meeting memory context for generation and citations."""
from __future__ import annotations

from typing import Any


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def _item_line(item: dict[str, Any], *, kind: str) -> str:
    text = _clean(item.get("text"))
    if not text:
        return ""
    if kind == "open":
        since = _clean(item.get("since")) or "未知"
        last = _clean(item.get("last_seen")) or since
        return f"- {text}（自 {since}，最近 {last}）"
    if kind == "risk":
        status = _clean(item.get("status")) or "active"
        last = _clean(item.get("last_seen")) or "未知"
        return f"- {text}（{status}，最近 {last}）"
    meeting_id = _clean(item.get("meeting_id")) or "未知会议"
    return f"- {meeting_id}：{text}"


def build_memory_context(
    *,
    project_id: str,
    project: dict[str, Any],
    state: dict[str, Any],
    bind: Any,
) -> str:
    if not project_id or not state:
        return ""
    evidence = getattr(bind, "evidence", []) or []
    parts = [
        "【会议记忆】",
        f"项目：{project_id} / {_clean(project.get('name')) or _clean(state.get('name')) or project_id}",
    ]
    if evidence:
        parts.append("命中依据：" + "、".join(str(x) for x in evidence[:8]))

    opens = [i for i in (state.get("open_items") or []) if isinstance(i, dict)]
    risks = [i for i in (state.get("risks") or []) if isinstance(i, dict) and i.get("status") != "mitigated"]
    decisions = [i for i in (state.get("decisions") or []) if isinstance(i, dict)]

    if opens:
        parts.append("\n【延续事项】")
        for item in opens[:6]:
            line = _item_line(item, kind="open")
            if line:
                parts.append(line)
                quote = _clean(item.get("quote"))
                if quote:
                    parts.append(f"  原文摘录：{quote}")
                title = _clean(item.get("meeting_title"))
                if title:
                    parts.append(f"  来源会议：{title}")
                mtime = _clean(item.get("time"))
                if mtime:
                    parts.append(f"  会议时间：{mtime}")
    if risks:
        parts.append("\n【风险演变】")
        for item in risks[:5]:
            line = _item_line(item, kind="risk")
            if line:
                parts.append(line)
                quote = _clean(item.get("quote"))
                if quote:
                    parts.append(f"  原文摘录：{quote}")
                title = _clean(item.get("meeting_title"))
                if title:
                    parts.append(f"  来源会议：{title}")
                mtime = _clean(item.get("time"))
                if mtime:
                    parts.append(f"  会议时间：{mtime}")
    if decisions:
        parts.append("\n【历史决策】")
        for item in decisions[-6:]:
            line = _item_line(item, kind="decision")
            if line:
                parts.append(line)
                quote = _clean(item.get("quote"))
                if quote:
                    parts.append(f"  原文摘录：{quote}")
                title = _clean(item.get("meeting_title"))
                if title:
                    parts.append(f"  来源会议：{title}")
                mtime = _clean(item.get("time"))
                if mtime:
                    parts.append(f"  会议时间：{mtime}")
    return "\n".join(parts).strip()


__all__ = ["build_memory_context"]
