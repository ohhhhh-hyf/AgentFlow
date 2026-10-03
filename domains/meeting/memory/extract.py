"""Extract the compact meeting fact used by meeting memory v2."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from infra.memory.entities import extract_entities, extract_quoted, is_generic_entity, speaker_names

from .bind import is_strong_anchor, project_core
from core.runner.text import clean_text as _clean


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
    # 议题树快照（module/title/decisions/actions/risks/open_issues）：
    # 记忆 v2 的作用域来源——条目自带 module/topic_title，不再靠正则从文本反猜主题。
    # 旧数据无此字段 → 默认 []，所有消费方按"无作用域"处理（行为与改造前一致）。
    topics: list[dict[str, Any]] = field(default_factory=list)

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
            "topics": self.topics,
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
            topics=_normalize_topics(raw.get("topics")),
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


def _normalize_topics(raw_topics: object) -> list[dict[str, Any]]:
    """议题树归一化：理解层输出与存储行共用同一形状。

    形状（memory 自己的词汇，与 MeetingFact.action_items 对齐）::

        {topic_id, module, title, decisions[], actions[{text,owner,timing,deliverable}],
         risks[], open_issues[]}

    理解层 actions 的键是 task/deadline，存储行是 text/timing——两种来源都收，
    幂等（归一化结果再归一化不变），as_dict → from_dict 往返无损。
    """
    out: list[dict[str, Any]] = []
    for topic in raw_topics or []:
        if not isinstance(topic, dict):
            continue
        actions: list[dict[str, str]] = []
        for item in topic.get("actions") or []:
            if not isinstance(item, dict):
                continue
            text = _clean(item.get("text") or item.get("task"))
            if not text:
                continue
            actions.append({
                "text": text,
                "owner": _clean(item.get("owner")),
                "timing": _clean(item.get("timing") or item.get("deadline")),
                "deliverable": _clean(item.get("deliverable")),
            })
        risks: list[str] = []
        for item in topic.get("risks") or []:
            text = _clean(item.get("risk")) if isinstance(item, dict) else _clean(item)
            if text and text not in risks:
                risks.append(text)
        out.append({
            "topic_id": _clean(topic.get("topic_id")),
            "module": _clean(topic.get("module")),
            "title": _clean(topic.get("title")),
            "decisions": _str_list(topic.get("decisions")),
            "actions": actions,
            "risks": risks,
            "open_issues": _str_list(topic.get("open_issues")),
        })
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
# open_issues 专用的强完成标记：去掉裸词「关闭/解决」——open_issues 是"没谈拢的
# 敞口事项"聚集地，「关闭策略待定」「解决方案未确认」这类未完成表述在裸词口径下
# 会被误判成闭环。2026-10 修：完成宣告只出现在 open_issues 时闭环池扫不到，
# 条目永远挂在【延续事项】里（实测 last_seen 更新、status 仍是 open）。
_DONE_STRONG_RE = re.compile(r"(已完成|已解决|已闭环|已整改|完成整改|已关闭|已落实)")


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
        for dec in topic.get("decisions") or []:
            d = _clean(dec)
            if d:
                rows.append(d)
    return rows


def _topic_closed_issues(understanding: dict[str, Any]) -> list[str]:
    """议题 open_issues 里的完成宣告（强完成标记口径，``_DONE_STRONG_RE``）。

    闭环池原本只扫 decisions/open_questions/actions/conclusion/key_points，
    模型把「X 已完成」记进 open_issues 时进不了池子，闭环整条不发生；
    这里单独收编，且用强完成标记避免把「关闭策略待定」这类敞口表述误判成闭环。
    """
    rows: list[str] = []
    for topic in understanding.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        for issue in topic.get("open_issues") or []:
            text = _clean(issue)
            if text and _DONE_STRONG_RE.search(text) and text not in rows:
                rows.append(text)
    return rows


def _action_items(understanding: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    source: list[dict[str, Any]] = []
    for t in (understanding.get("topics") or []):
        if isinstance(t, dict):
            for a in (t.get("actions") or []):
                if isinstance(a, dict):
                    source.append({
                        "action": a.get("task") or a.get("action") or "",
                        "owner": a.get("owner") or "",
                        "timing": a.get("deadline") or a.get("timing") or "",
                    })
    if not source:
        source = list(understanding.get("action_hints") or [])
    for item in source:
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
    # open_issues 的完成宣告：强完成标记口径单独收编（与上面的宽松口径分开，
    # 避免把敞口表述误判成闭环；详见 _topic_closed_issues）。
    for text in _topic_closed_issues(understanding):
        if text not in rows:
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
    topics = data.get("topics") or []
    decisions = _str_list(data.get("decisions"))
    if not decisions and isinstance(topics, list):
        for t in topics:
            if isinstance(t, dict):
                for d in (t.get("decisions") or []):
                    if d and str(d).strip() and str(d).strip() not in decisions:
                        decisions.append(str(d).strip())

    opens = _str_list(data.get("open_questions"))
    if not opens and isinstance(topics, list):
        for t in topics:
            if isinstance(t, dict):
                for o in (t.get("open_issues") or []):
                    if o and str(o).strip() and str(o).strip() not in opens:
                        opens.append(str(o).strip())

    risks = _str_list(data.get("risks"))
    if not risks and isinstance(topics, list):
        for t in topics:
            if isinstance(t, dict):
                for r in (t.get("risks") or []):
                    if isinstance(r, dict) and r.get("risk"):
                        r_text = str(r["risk"]).strip()
                        if r_text and r_text not in risks:
                            risks.append(r_text)

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
        # 结构化议题与 flat 列表并行产出：flat 逻辑（含 fields 回退）一字不动，
        # topics 只作记忆作用域/对照标签的原生来源。
        topics=_normalize_topics(topics),
    )


__all__ = ["MeetingFact", "extract_meeting_fact"]
