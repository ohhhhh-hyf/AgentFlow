"""Extract the compact meeting fact used by meeting memory v2."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from tools.memory.entities import extract_entities, extract_quoted, is_generic_entity, speaker_names

from .bind import is_strong_anchor, project_core
from tools.core.text import clean_text as _clean


@dataclass
class MeetingFact:
    meeting_id: str
    time: str
    time_source: str = "unknown"  # user | unknown
    project_id: str = ""
    bind: dict[str, Any] = field(default_factory=dict)
    title: str = ""
    summary: str = ""
    anchors: list[str] = field(default_factory=list)
    project_candidates: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_items: list[str] = field(default_factory=list)
    action_items: list[dict[str, str]] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    closed_items: list[str] = field(default_factory=list)
    quotes: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "meeting_id": self.meeting_id,
            "time": self.time,
            "time_source": self.time_source,
            "project_id": self.project_id,
            "bind": self.bind,
            "title": self.title,
            "summary": self.summary,
            "anchors": self.anchors,
            "project_candidates": self.project_candidates,
            "decisions": self.decisions,
            "open_items": self.open_items,
            "action_items": self.action_items,
            "risks": self.risks,
            "closed_items": self.closed_items,
            "quotes": self.quotes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MeetingFact":
        raw = data if isinstance(data, dict) else {}
        actions = raw.get("action_items") or []
        action_items: list[dict[str, str]] = []
        for item in actions:
            if isinstance(item, dict):
                text = _clean(item.get("text") or item.get("action"))
                if text:
                    action_items.append({
                        "text": text,
                        "owner": _clean(item.get("owner")),
                        "timing": _clean(item.get("timing")),
                    })
            else:
                text = _clean(item)
                if text:
                    action_items.append({"text": text, "owner": "", "timing": ""})
        time_val = _clean(raw.get("time"))
        source = _clean(raw.get("time_source")) or ("user" if time_val else "unknown")
        return cls(
            meeting_id=_clean(raw.get("meeting_id")) or "m_unknown",
            time=time_val,
            time_source=source if source in {"user", "unknown"} else "unknown",
            project_id=_clean(raw.get("project_id")),
            bind=dict(raw.get("bind") or {}) if isinstance(raw.get("bind"), dict) else {},
            title=_clean(raw.get("title")),
            summary=_clean(raw.get("summary")),
            anchors=_str_list(raw.get("anchors")),
            project_candidates=_str_list(raw.get("project_candidates")),
            decisions=_str_list(raw.get("decisions")),
            open_items=_str_list(raw.get("open_items")),
            action_items=action_items,
            risks=_str_list(raw.get("risks")),
            closed_items=_str_list(raw.get("closed_items")),
            quotes=[
                item for item in (raw.get("quotes") or [])
                if isinstance(item, dict)
            ],
        )


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _clean(item)
        if text and text not in out:
            out.append(text)
    return out


def _topic_title(topic: object) -> str:
    return _clean(topic.get("title")) if isinstance(topic, dict) else ""


def _meeting_title(understanding: dict[str, Any], transcript: str) -> str:
    for pattern in (r"会议主题[:：]\s*([^\n]+)", r"主题[:：]\s*([^\n]+)"):
        match = re.search(pattern, transcript or "")
        if match:
            title = _clean(match.group(1))
            if 2 <= len(title) <= 40:
                return title[:30]
    topics = [_topic_title(t) for t in understanding.get("topics") or []]
    topics = [t for t in topics if t]
    if topics:
        return topics[0][:30]
    purpose = _clean(understanding.get("meeting_purpose"))
    return purpose[:30] if purpose else "会议纪要"


def _summary(understanding: dict[str, Any]) -> str:
    parts: list[str] = []
    purpose = _clean(understanding.get("meeting_purpose"))
    if purpose:
        parts.append(purpose)
    topics = [_topic_title(t) for t in understanding.get("topics") or []]
    topics = [t for t in topics if t]
    if topics:
        parts.append("议题：" + "；".join(topics[:5]))
    decisions = _str_list(understanding.get("decisions"))
    if decisions:
        parts.append("决策：" + "；".join(decisions[:3]))
    return " ".join(parts)[:500]


_LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}")
_LEAD_VERBS = (
    "复盘", "跟进", "确认", "围绕", "讨论", "召开", "汇报", "总结", "明确",
    "识别", "优化", "推进", "完成", "加快", "梳理", "协调", "沟通",
)


def _latin_anchored_entities(*texts: str) -> list[str]:
    blob = " ".join(_clean(t) for t in texts if _clean(t))
    out: list[str] = []
    for m in _LATIN_TOKEN.finditer(blob):
        start, end = m.start(), m.end()
        while start > 0 and "\u4e00" <= blob[start - 1] <= "\u9fff":
            start -= 1
        while end < len(blob) and "\u4e00" <= blob[end] <= "\u9fff":
            end += 1
        piece = _clean(blob[start:end])
        for verb in _LEAD_VERBS:
            if piece.startswith(verb) and len(piece) > len(verb):
                piece = piece[len(verb):].strip()
                break
        piece = project_core(piece)
        if 4 <= len(piece) <= 24 and piece not in out:
            out.append(piece)
    return out[:10]


def _project_candidates(transcript: str, understanding: dict[str, Any], title: str) -> list[str]:
    quoted = [q for q in extract_quoted(transcript or "") if 2 <= len(q) <= 24]
    purpose = _clean(understanding.get("meeting_purpose"))
    brief = _clean(understanding.get("meeting_brief"))
    mixed = _latin_anchored_entities(title, purpose, brief)
    cands: list[str] = []
    core = project_core(title)
    if core and 2 <= len(core) <= 40:
        cands.append(core)
    if title and title not in cands and 2 <= len(title) <= 40:
        cands.append(title)
    for c in quoted + mixed:
        if c and c not in cands:
            cands.append(c)
    return cands[:8]


def _anchor_candidates(understanding: dict[str, Any], transcript: str) -> list[str]:
    """Only identity-grade tokens (strong anchors). N-grams stay out of registry."""
    speakers = speaker_names(transcript)
    title = _meeting_title(understanding, transcript)
    text_bits = [
        title,
        _clean(understanding.get("meeting_purpose")),
        _clean(understanding.get("meeting_brief")),
        *[_topic_title(t) for t in understanding.get("topics") or []],
        *_str_list(understanding.get("decisions")),
        *_str_list(understanding.get("open_questions")),
        *_str_list(understanding.get("risks")),
    ]
    blob = " ".join(bit for bit in text_bits if bit) or transcript
    candidates = (
        ([title] if title else [])
        + [project_core(title)]
        + list(extract_quoted(transcript))
        + list(extract_quoted(blob))
        + _latin_anchored_entities(title, blob)
        + list(extract_entities(blob, limit=30))
    )
    out: list[str] = []
    for item in candidates:
        text = _clean(item)
        core = project_core(text) or text
        if not core or core in out or core in speakers or is_generic_entity(core):
            continue
        if any(len(s) >= 2 and (core.startswith(s) or s.startswith(core)) for s in speakers):
            continue
        if not is_strong_anchor(core):
            continue
        out.append(core)
        if len(out) >= 12:
            break
    return out


_DONE_RE = re.compile(r"(已完成|已解决|已闭环|已整改|完成整改|已关闭|关闭|解决|已落实)")


def _topic_conclusions(understanding: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for topic in understanding.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        text = _clean(topic.get("conclusion"))
        if text:
            rows.append(text)
        for point in topic.get("key_points") or []:
            p = _clean(point)
            if p:
                rows.append(p)
    return rows


def _action_items(understanding: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in understanding.get("action_hints") or []:
        if isinstance(item, dict):
            text = _clean(item.get("action") or item.get("text"))
            owner = _clean(item.get("owner"))
            timing = _clean(item.get("timing"))
        else:
            text = _clean(item)
            owner = ""
            timing = ""
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append({"text": text, "owner": owner, "timing": timing})
    return rows[:16]


def _closed_items(understanding: dict[str, Any], actions: list[dict[str, str]]) -> list[str]:
    pool = (
        _str_list(understanding.get("decisions"))
        + _str_list(understanding.get("open_questions"))
        + [a["text"] for a in actions]
        + _topic_conclusions(understanding)
    )
    rows: list[str] = []
    for text in pool:
        if _DONE_RE.search(text) and text not in rows:
            rows.append(text)
    return rows[:12]


def _quote_for(transcript: str, text: str) -> str:
    query = _clean(text)
    raw = transcript or ""
    if not query:
        return ""
    compact_query = re.sub(r"\s+", "", query)
    sentences = [s.strip() for s in re.split(r"(?<=[。！？；!?\n])", raw) if s.strip()]
    best = ""
    best_score = 0
    for sent in sentences:
        compact_sent = re.sub(r"\s+", "", sent)
        score = 0
        if compact_query and compact_query in compact_sent:
            score = 1000 + len(compact_query)
        else:
            for size in range(min(12, len(compact_query)), 3, -1):
                grams = {compact_query[i:i + size] for i in range(len(compact_query) - size + 1)}
                hit = sum(1 for gram in grams if gram in compact_sent)
                if hit:
                    score = size * 20 + hit
                    break
        if score > best_score:
            best = sent
            best_score = score
    return best[:180]


def _quotes(
    transcript: str,
    decisions: list[str],
    opens: list[str],
    risks: list[str],
    closed: list[str],
    actions: list[dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    action_texts = [a["text"] for a in actions]
    for kind, values in (
        ("decision", decisions),
        ("open", opens),
        ("action", action_texts),
        ("risk", risks),
        ("closed", closed),
    ):
        for text in values[:6]:
            quote = _quote_for(transcript, text)
            if quote:
                rows.append({"kind": kind, "text": text, "quote": quote})
    return rows[:24]


def _meeting_id(request_id: str, transcript: str) -> str:
    if request_id:
        return "m_" + re.sub(r"[^A-Za-z0-9_-]+", "_", request_id)[:80]
    digest = hashlib.md5((transcript or "").encode("utf-8")).hexdigest()[:8]
    return f"m_{digest}"


def extract_meeting_fact(
    understanding: dict[str, Any] | None,
    transcript: str,
    *,
    request_id: str = "",
    time: str = "",
) -> MeetingFact:
    data = understanding if isinstance(understanding, dict) else {}
    decisions = _str_list(data.get("decisions"))
    opens = _str_list(data.get("open_questions"))
    risks = _str_list(data.get("risks"))
    actions = _action_items(data)
    closed = _closed_items(data, actions)
    title = _meeting_title(data, transcript)
    time_val = (time or "").strip()
    return MeetingFact(
        meeting_id=_meeting_id(request_id, transcript),
        time=time_val,
        time_source="user" if time_val else "unknown",
        bind={"mode": "auto", "confidence": "low", "evidence": []},
        title=title,
        summary=_summary(data),
        anchors=_anchor_candidates(data, transcript),
        project_candidates=_project_candidates(transcript, data, title),
        decisions=decisions,
        open_items=opens,
        action_items=actions,
        risks=risks,
        closed_items=closed,
        quotes=_quotes(transcript, decisions, opens, risks, closed, actions),
    )


__all__ = ["MeetingFact", "extract_meeting_fact"]
