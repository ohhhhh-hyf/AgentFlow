"""笔记记忆：同一用户按学科分档，只记术语与场次，供图谱增量。"""
from __future__ import annotations

from typing import Any

_TERM_CAP = 80
_SESSION_CAP = 8


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def merge_notes(
    record: dict[str, Any],
    understanding: dict[str, Any] | None,
    stamp: str,
    subject: str = "",
) -> dict[str, Any]:
    """把本场笔记理解并进档案，不写入会议字段。"""
    rec = dict(record)
    label = _clean(subject) or _clean(rec.get("subject"))
    if label:
        rec["subject"] = label
        rec["project_key"] = label
        if not _clean(rec.get("display_name")):
            rec["display_name"] = label

    notes = dict(rec.get("notes") or {})
    notes["subject"] = label or _clean(notes.get("subject"))

    terms: list[str] = []
    for token in list(notes.get("key_terms") or []):
        text = _clean(token)
        if text and text not in terms:
            terms.append(text)
    incoming = understanding if isinstance(understanding, dict) else {}
    for token in incoming.get("key_terms") or []:
        text = _clean(token)
        if text and text not in terms:
            terms.append(text)
    notes["key_terms"] = terms[:_TERM_CAP]

    sessions = list(notes.get("sessions") or [])
    sessions.append(
        {
            "at": stamp,
            "purpose": _clean(incoming.get("note_purpose")),
            "key_terms": [
                _clean(t) for t in (incoming.get("key_terms") or []) if _clean(t)
            ][:20],
        }
    )
    notes["sessions"] = sessions[-_SESSION_CAP:]
    rec["notes"] = notes
    return rec


__all__ = ["merge_notes"]
