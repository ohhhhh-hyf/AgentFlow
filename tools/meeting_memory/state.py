"""Project state update for meeting memory v2."""
from __future__ import annotations

import re
from typing import Any


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _similar(left: str, right: str) -> bool:
    a, b = _compact(left), _compact(right)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    limit = min(12, len(a), len(b))
    for size in range(limit, 4, -1):
        grams = {a[i:i + size] for i in range(len(a) - size + 1)}
        if any(gram in b for gram in grams):
            return True
    return False


def _quote(fact: Any, kind: str, text: str) -> str:
    for item in getattr(fact, "quotes", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == kind and _similar(str(item.get("text") or ""), text):
            return _clean(item.get("quote"))
    return ""


def _merge_unique(old: list[str], new: list[str], cap: int = 24) -> list[str]:
    out: list[str] = []
    for item in list(old or []) + list(new or []):
        text = _clean(item)
        if text and text not in out:
            out.append(text)
    return out[:cap]


def _upsert_items(rows: list[dict[str, Any]], values: list[str], fact: Any, kind: str) -> list[dict[str, Any]]:
    out = [dict(r) for r in rows if isinstance(r, dict) and _clean(r.get("text"))]
    for value in values:
        text = _clean(value)
        if not text:
            continue
        hit = next((r for r in out if _similar(str(r.get("text") or ""), text)), None)
        if hit is None:
            out.append({
                "text": text,
                "since": fact.meeting_id,
                "last_seen": fact.meeting_id,
                "meeting_title": _clean(fact.title),
                "time": _clean(getattr(fact, "time", "")),
                "quote": _quote(fact, kind, text),
            })
        else:
            hit["last_seen"] = fact.meeting_id
            hit["meeting_title"] = _clean(fact.title)
            hit["time"] = _clean(getattr(fact, "time", "")) or hit.get("time") or ""
            hit["quote"] = _quote(fact, kind, text) or hit.get("quote") or ""
    return out[:40]


def _close_items(rows: list[dict[str, Any]], closed: list[str]) -> list[dict[str, Any]]:
    if not closed:
        return rows
    kept: list[dict[str, Any]] = []
    for row in rows:
        text = _clean(row.get("text"))
        if text and any(_similar(text, c) for c in closed):
            continue
        kept.append(row)
    return kept


_MITIGATED_RE = re.compile(r"(已解决|已缓解|已消除|风险解除|不再存在|完成整改)")


def _upsert_risks(rows: list[dict[str, Any]], risks: list[str], fact: Any) -> list[dict[str, Any]]:
    out = [dict(r) for r in rows if isinstance(r, dict) and _clean(r.get("text"))]
    for value in risks:
        text = _clean(value)
        if not text:
            continue
        status = "mitigated" if _MITIGATED_RE.search(text) else "active"
        hit = next((r for r in out if _similar(str(r.get("text") or ""), text)), None)
        if hit is None:
            out.append({
                "text": text,
                "status": status,
                "since": fact.meeting_id,
                "last_seen": fact.meeting_id,
                "meeting_title": _clean(fact.title),
                "time": _clean(getattr(fact, "time", "")),
                "quote": _quote(fact, "risk", text),
            })
        else:
            hit["last_seen"] = fact.meeting_id
            hit["meeting_title"] = _clean(fact.title)
            hit["time"] = _clean(getattr(fact, "time", "")) or hit.get("time") or ""
            hit["status"] = status if status == "mitigated" else hit.get("status") or "active"
            hit["quote"] = _quote(fact, "risk", text) or hit.get("quote") or ""
    return out[:40]


def _upsert_decisions(rows: list[dict[str, Any]], decisions: list[str], fact: Any) -> list[dict[str, Any]]:
    out = [dict(r) for r in rows if isinstance(r, dict) and _clean(r.get("text"))]
    for value in decisions:
        text = _clean(value)
        if not text or any(_similar(str(r.get("text") or ""), text) for r in out):
            continue
        out.append({
            "text": text,
            "meeting_id": fact.meeting_id,
            "meeting_title": _clean(fact.title),
            "time": _clean(getattr(fact, "time", "")),
            "quote": _quote(fact, "decision", text),
        })
    return out[-60:]


def backfill_meeting_titles(state: dict[str, Any], meetings: list[dict[str, Any]]) -> dict[str, Any]:
    """从 meetings.jsonl 补全 items 缺失的 meeting_title（旧数据迁移兼容）。

    早期 state 未存会议标题；meetings.jsonl 的 {meeting_id: title} 是权威来源。
    open/risk 用 last_seen（最近场次），decision 用 meeting_id（首次决策场次）。
    """
    titles: dict[str, str] = {}
    for meeting in meetings:
        mid = _clean(meeting.get("meeting_id"))
        title = _clean(meeting.get("title"))
        if mid and title:
            titles[mid] = title
    if not titles:
        return state
    out = dict(state or {})
    for key in ("open_items", "risks", "decisions"):
        rows: list[dict[str, Any]] = []
        for item in out.get(key) or []:
            if not isinstance(item, dict):
                rows.append(item)
                continue
            row = dict(item)
            if not _clean(row.get("meeting_title")):
                mid = _clean(row.get("last_seen") or row.get("meeting_id") or row.get("since"))
                if mid in titles:
                    row["meeting_title"] = titles[mid]
            rows.append(row)
        out[key] = rows
    return out


def update_state(state: dict[str, Any], fact: Any, project_id: str, project_name: str = "") -> dict[str, Any]:
    out = dict(state or {})
    out["project_id"] = project_id
    out["name"] = project_name or out.get("name") or project_id
    out["anchors"] = _merge_unique(out.get("anchors") or [], getattr(fact, "anchors", []) or [])
    out["decisions"] = _upsert_decisions(out.get("decisions") or [], getattr(fact, "decisions", []) or [], fact)
    opens = _upsert_items(out.get("open_items") or [], getattr(fact, "open_items", []) or [], fact, "open")
    out["open_items"] = _close_items(opens, getattr(fact, "closed_items", []) or [])
    out["risks"] = _upsert_risks(out.get("risks") or [], getattr(fact, "risks", []) or [], fact)
    recent = [str(x) for x in (out.get("recent_meetings") or []) if str(x).strip()]
    if fact.meeting_id in recent:
        recent.remove(fact.meeting_id)
    recent.append(fact.meeting_id)
    out["recent_meetings"] = recent[-8:]
    bits = [getattr(fact, "summary", "") or ""]
    active_open = [_clean(i.get("text")) for i in out.get("open_items") or [] if isinstance(i, dict)]
    active_risks = [
        _clean(i.get("text")) for i in out.get("risks") or []
        if isinstance(i, dict) and i.get("status") != "mitigated"
    ]
    if active_open:
        bits.append("未决：" + "；".join(active_open[:5]))
    if active_risks:
        bits.append("风险：" + "；".join(active_risks[:4]))
    out["summary"] = " ".join(bit for bit in bits if bit)[:800]
    return out


__all__ = ["backfill_meeting_titles", "update_state"]
