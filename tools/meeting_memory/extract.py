"""Extract the compact meeting fact used by meeting memory v2."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from tools.memory.entities import extract_entities, extract_quoted, is_generic_entity, speaker_names


@dataclass
class MeetingFact:
    meeting_id: str
    time: str
    project_id: str = ""
    bind: dict[str, Any] = field(default_factory=dict)
    title: str = ""
    summary: str = ""
    anchors: list[str] = field(default_factory=list)
    project_candidates: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_items: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    closed_items: list[str] = field(default_factory=list)
    quotes: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "meeting_id": self.meeting_id,
            "time": self.time,
            "project_id": self.project_id,
            "bind": self.bind,
            "title": self.title,
            "summary": self.summary,
            "anchors": self.anchors,
            "project_candidates": self.project_candidates,
            "decisions": self.decisions,
            "open_items": self.open_items,
            "risks": self.risks,
            "closed_items": self.closed_items,
            "quotes": self.quotes,
        }


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


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
# 概括句句首常见的动词性引导词（仅在项目名候选里剥离，避免"复盘小艺…"式杂质）
_LEAD_VERBS = (
    "复盘", "跟进", "确认", "围绕", "讨论", "召开", "汇报", "总结", "明确",
    "识别", "优化", "推进", "完成", "加快", "梳理", "协调", "沟通",
)


def _latin_anchored_entities(*texts: str) -> list[str]:
    """低门槛提取中文-拉丁混合段（项目名常以「中文+拉丁」形态出现在概括句/标题）。

    例：「跟进小艺慧记Agent开发进展」→「小艺慧记Agent开发进展」。
    """
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
        if 4 <= len(piece) <= 24 and piece not in out:
            out.append(piece)
    return out[:10]


def _project_candidates(transcript: str, understanding: dict[str, Any], title: str) -> list[str]:
    """项目名候选：标题（第一信号）→ 原文引号实体 → 中文-拉丁混合段。"""
    quoted = [q for q in extract_quoted(transcript or "") if 2 <= len(q) <= 24]
    purpose = _clean(understanding.get("meeting_purpose"))
    brief = _clean(understanding.get("meeting_brief"))
    mixed = _latin_anchored_entities(title, purpose, brief)
    cands: list[str] = []
    if title and 2 <= len(title) <= 40:
        cands.append(title)
    for c in quoted + mixed:
        if c and c not in cands:
            cands.append(c)
    return cands[:8]


def _anchor_candidates(understanding: dict[str, Any], transcript: str) -> list[str]:
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
        + list(extract_quoted(transcript))
        + list(extract_quoted(blob))
        + list(extract_entities(blob, limit=30))
        + _latin_anchored_entities(title, blob)
    )
    out: list[str] = []
    for item in candidates:
        text = _clean(item)
        if not text or text in out or text in speakers or is_generic_entity(text):
            continue
        if len(text) < 2 or len(text) > 24:
            continue
        if any(len(s) >= 2 and (text.startswith(s) or s.startswith(text)) for s in speakers):
            continue
        out.append(text)
        if len(out) >= 16:
            break
    return out


_DONE_RE = re.compile(r"(已完成|已解决|已闭环|已整改|完成整改|关闭|解决)")


def _closed_items(understanding: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for text in _str_list(understanding.get("decisions")) + _str_list(understanding.get("open_questions")):
        if _DONE_RE.search(text):
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


def _quotes(transcript: str, decisions: list[str], opens: list[str], risks: list[str], closed: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for kind, values in (
        ("decision", decisions),
        ("open", opens),
        ("risk", risks),
        ("closed", closed),
    ):
        for text in values[:6]:
            quote = _quote_for(transcript, text)
            if quote:
                # state._quote 需要 text 做相似匹配，才能把原文摘录写回
                # decisions/open_items/risks 对应条目。
                rows.append({"kind": kind, "text": text, "quote": quote})
    return rows[:24]


def _meeting_id(request_id: str, transcript: str) -> str:
    if request_id:
        return "m_" + re.sub(r"[^A-Za-z0-9_-]+", "_", request_id)[:80]
    day = datetime.now().strftime("%Y%m%d")
    digest = hashlib.md5((transcript or "").encode("utf-8")).hexdigest()[:8]
    return f"m_{day}_{digest}"


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
    closed = _closed_items(data)
    title = _meeting_title(data, transcript)
    return MeetingFact(
        meeting_id=_meeting_id(request_id, transcript),
        time=(time or "").strip() or datetime.now().strftime("%Y-%m-%d %H:%M"),
        bind={"mode": "auto", "confidence": "low", "evidence": []},
        title=title,
        summary=_summary(data),
        anchors=_anchor_candidates(data, transcript),
        project_candidates=_project_candidates(transcript, data, title),
        decisions=decisions,
        open_items=opens,
        risks=risks,
        closed_items=closed,
        quotes=_quotes(transcript, decisions, opens, risks, closed),
    )


__all__ = ["MeetingFact", "extract_meeting_fact"]
