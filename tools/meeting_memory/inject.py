"""Build high-confidence meeting memory context for generation and citations."""
from __future__ import annotations

import re
from typing import Any

from .state import session_index, session_label, similar


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _relevance(item: dict[str, Any], fact: Any | None) -> int:
    if fact is None:
        return 1
    blob = _compact(
        " ".join([
            _clean(getattr(fact, "title", "")),
            _clean(getattr(fact, "summary", "")),
            " ".join(getattr(fact, "anchors", []) or []),
            " ".join(getattr(fact, "decisions", []) or []),
            " ".join(getattr(fact, "open_items", []) or []),
            " ".join(getattr(fact, "risks", []) or []),
        ])
    )
    text = _compact(_clean(item.get("text")))
    if not text:
        return 0
    if text in blob or blob in text:
        return 100
    score = 0
    for size in range(min(8, len(text)), 3, -1):
        grams = {text[i:i + size] for i in range(0, len(text) - size + 1, size)}
        hits = sum(1 for g in grams if g in blob)
        if hits:
            score = size * hits
            break
    return score


def _rank(items: list[dict[str, Any]], fact: Any | None, cap: int) -> list[dict[str, Any]]:
    scored = [( _relevance(i, fact), i) for i in items]
    scored.sort(key=lambda x: -x[0])
    if fact is None:
        return [i for _, i in scored[:cap]]
    kept = [i for s, i in scored if s > 0][:cap]
    if kept:
        return kept
    return [i for _, i in scored[:cap]]


def _append_item(
    parts: list[str],
    item: dict[str, Any],
    *,
    seq_map: dict[str, dict[str, Any]],
    meta: str,
) -> None:
    text = _clean(item.get("text"))
    if not text:
        return
    parts.append(f"- {text}（{meta}）")
    quote = _clean(item.get("quote"))
    if quote:
        parts.append(f"  原文摘录：{quote}")
    title = _clean(item.get("meeting_title"))
    if title:
        parts.append(f"  来源会议：{title}")
    mid = _clean(item.get("last_seen") or item.get("meeting_id") or item.get("closed_at") or item.get("since"))
    info = seq_map.get(mid) or {}
    time_val = _clean(item.get("time")) or _clean(info.get("time"))
    if time_val:
        parts.append(f"  会议时间：{time_val}")


def _open_meta(item: dict[str, Any], seq_map: dict[str, dict[str, Any]]) -> str:
    since = session_label(seq_map, _clean(item.get("since")))
    last = session_label(seq_map, _clean(item.get("last_seen") or item.get("since")))
    status = _clean(item.get("status")) or "open"
    bits = [f"{since}起", f"最近{last}", f"状态 {status}"]
    owner = _clean(item.get("owner"))
    if owner:
        bits.append(f"负责人 {owner}")
    return "，".join(bits)


def _closed_meta(item: dict[str, Any], seq_map: dict[str, dict[str, Any]]) -> str:
    closed = session_label(seq_map, _clean(item.get("closed_at") or item.get("last_seen")))
    return f"{closed}关闭"


def _risk_meta(item: dict[str, Any], seq_map: dict[str, dict[str, Any]]) -> str:
    status = _clean(item.get("status")) or "active"
    last = session_label(seq_map, _clean(item.get("last_seen")))
    return f"{status}，最近{last}"


def _decision_meta(item: dict[str, Any], seq_map: dict[str, dict[str, Any]]) -> str:
    first = session_label(seq_map, _clean(item.get("meeting_id") or item.get("since")))
    status = _clean(item.get("status")) or "active"
    return f"{first}已决策，状态 {status}"


def preview_comparison(
    state: dict[str, Any],
    fact: Any,
    seq_map: dict[str, dict[str, Any]],
) -> list[str]:
    """Programmatic history_comparison lines (at most one per class)."""
    lines: list[str] = []
    hist_decisions = [
        i for i in (state.get("decisions") or [])
        if isinstance(i, dict) and _clean(i.get("text")) and i.get("status") != "superseded"
    ]
    new_decisions = [
        d for d in (getattr(fact, "decisions", None) or [])
        if _clean(d) and not any(similar(d, _clean(h.get("text"))) for h in hist_decisions)
    ]
    if new_decisions:
        lines.append(f"新增决策：{_clean(new_decisions[0])}")

    opens = [
        i for i in list(state.get("actions") or []) + list(state.get("open_items") or [])
        if isinstance(i, dict) and i.get("status") == "open" and _clean(i.get("text"))
    ]
    ranked_open = _rank(opens, fact, 1)
    if ranked_open:
        item = ranked_open[0]
        since = session_label(seq_map, _clean(item.get("since")))
        lines.append(f"延续事项（自{since}）：{_clean(item.get('text'))}")

    closed_now = list(getattr(fact, "closed_items", None) or [])
    closed_hist = [
        i for i in list(state.get("actions") or []) + list(state.get("open_items") or [])
        if isinstance(i, dict) and _clean(i.get("text"))
        and (
            i.get("status") == "done"
            or any(similar(_clean(i.get("text")), c) for c in closed_now)
        )
    ]
    if closed_hist:
        item = closed_hist[0]
        closed_mid = _clean(item.get("closed_at"))
        when = session_label(seq_map, closed_mid) if item.get("status") == "done" and closed_mid in seq_map else "本场"
        lines.append(f"已闭环（{when}）：{_clean(item.get('text'))}")
    elif closed_now:
        lines.append(f"已闭环：{_clean(closed_now[0])}")

    hist_risks = [i for i in (state.get("risks") or []) if isinstance(i, dict) and _clean(i.get("text"))]
    fact_risks = [_clean(r) for r in (getattr(fact, "risks", None) or []) if _clean(r)]
    evolved = ""
    for hist in hist_risks:
        for cur in fact_risks:
            if not similar(_clean(hist.get("text")), cur):
                continue
            if re.search(r"(已解决|已缓解|已消除|风险解除|不再存在|完成整改)", cur):
                last = session_label(seq_map, _clean(hist.get("last_seen")))
                evolved = f"风险演变（缓解，{last}）：{cur}"
            elif hist.get("status") == "mitigated":
                evolved = f"风险演变（再发，本场）：{cur}"
            else:
                last = session_label(seq_map, _clean(hist.get("last_seen")))
                evolved = f"风险演变（持续，{last}）：{_clean(hist.get('text'))}"
            break
        if evolved:
            break
    if not evolved:
        active = [i for i in hist_risks if i.get("status") == "active"]
        if active:
            item = _rank(active, fact, 1)[0]
            last = session_label(seq_map, _clean(item.get("last_seen")))
            evolved = f"风险演变（持续，{last}）：{_clean(item.get('text'))}"
    if evolved:
        lines.append(evolved)
    return lines[:4]


def build_memory_context(
    *,
    project_id: str,
    project: dict[str, Any],
    state: dict[str, Any],
    bind: Any,
    meetings: list[dict[str, Any]] | None = None,
    current_fact: Any | None = None,
) -> tuple[str, list[str]]:
    if not project_id or not state:
        return "", []
    seq_map = session_index(meetings or [], project_id)
    evidence = getattr(bind, "evidence", []) or []
    parts = [
        "【会议记忆】",
        f"项目：{_clean(project.get('name')) or _clean(state.get('name')) or project_id}",
    ]
    if evidence:
        parts.append("命中依据：" + "、".join(str(x) for x in evidence[:8]))

    opens = [
        i for i in list(state.get("actions") or []) + list(state.get("open_items") or [])
        if isinstance(i, dict) and (i.get("status") or "open") == "open"
    ]
    closed = [
        i for i in list(state.get("actions") or []) + list(state.get("open_items") or [])
        if isinstance(i, dict) and i.get("status") == "done"
    ]
    risks = [
        i for i in (state.get("risks") or [])
        if isinstance(i, dict) and i.get("status") in {"active", "mitigated"}
    ]
    active_risks = [i for i in risks if i.get("status") == "active"]
    mitigated = [i for i in risks if i.get("status") == "mitigated"]
    decisions = [
        i for i in (state.get("decisions") or [])
        if isinstance(i, dict) and i.get("status") != "superseded"
    ]

    ranked_open = _rank(opens, current_fact, 6)
    ranked_closed = _rank(closed, current_fact, 4)
    ranked_risks = _rank(active_risks, current_fact, 5) + _rank(mitigated, current_fact, 2)
    ranked_decisions = _rank(decisions[-8:], current_fact, 6)

    if ranked_open:
        parts.append("\n【延续事项】")
        for item in ranked_open:
            _append_item(parts, item, seq_map=seq_map, meta=_open_meta(item, seq_map))
    if ranked_closed:
        parts.append("\n【已闭环】")
        for item in ranked_closed:
            _append_item(parts, item, seq_map=seq_map, meta=_closed_meta(item, seq_map))
    if ranked_risks:
        parts.append("\n【风险演变】")
        for item in ranked_risks[:5]:
            _append_item(parts, item, seq_map=seq_map, meta=_risk_meta(item, seq_map))
    if ranked_decisions:
        parts.append("\n【历史决策】")
        for item in ranked_decisions:
            _append_item(parts, item, seq_map=seq_map, meta=_decision_meta(item, seq_map))

    comparison: list[str] = []
    if current_fact is not None:
        comparison = preview_comparison(state, current_fact, seq_map)
        if comparison:
            parts.append("\n【历史对照素材】")
            for line in comparison:
                parts.append(f"- {line}")

    return "\n".join(parts).strip(), comparison


__all__ = ["build_memory_context", "preview_comparison"]
