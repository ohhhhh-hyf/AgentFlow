"""个人单线 minutes 的本人证据包。

证据包只用于 PersonalPerspective 建模，不进入草稿。
短/中文本直接全文；超长时优先复用现有按人切片，切片失败再走关键词窗口/全局采样。
"""
from __future__ import annotations

import re
from typing import Any

from .hits import slice_transcript_for_person

PERSONAL_EVIDENCE_FULL_LIMIT = 12000
_DEFAULT_RADIUS = 600
_OMIT_MIDDLE = "\n……（此处省略中间无关内容）\n"
_OMIT_WINDOW = "\n……（此处省略无关内容）\n"
_BULLET_RE = re.compile(r"^\s*[•·*+\-]\s+(.*)$")
_TIME_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?")
_COLON_RE = re.compile(r"^[^\s:：]{1,24}[：:]")

_HEADER_FULL = "【个人证据包】\n（本场原文较短，提供全文；仅用于本人视角建模）"
_HEADER_SLICE = "【个人证据包】\n（已按本人姓名/别称、重点人物、重点标的裁剪；省略处为无关内容）"
_HEADER_KEYWORD = "【个人证据包】\n（已按本人姓名/别称、重点人物、重点标的定位；省略处为无关内容）"
_HEADER_SAMPLE = "【个人证据包】\n（本人相关段落不足，使用全局采样；省略处为无关内容）"


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _looks_like_speaker_header(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped or len(stripped) > 80:
        return False
    if _TIME_RE.search(stripped):
        return True
    return bool(_COLON_RE.match(stripped))


def _strip_speaker_bullets(text: str) -> str:
    """兼容 ``• 发言者 1 00:21`` / ``- 张三 00:21`` 等带前导符号的发言行。"""
    lines: list[str] = []
    for line in (text or "").splitlines():
        match = _BULLET_RE.match(line)
        if match and _looks_like_speaker_header(match.group(1)):
            lines.append(match.group(1))
        else:
            lines.append(line)
    return "\n".join(lines)


def _sample_text(text: str, max_chars: int) -> tuple[str, bool]:
    """超长文本取头部 + 中段 + 尾部；返回 (文本, 是否截断)。"""
    if len(text) <= max_chars:
        return text, False
    marker_len = len(_OMIT_MIDDLE)
    available = max_chars - marker_len
    if available <= 0:
        return text[:max_chars], True
    head_len = available * 45 // 100
    mid_len = available * 20 // 100
    tail_len = available - head_len - mid_len
    middle_at = max(head_len, len(text) // 2 - mid_len // 2)
    middle = text[middle_at:middle_at + mid_len]
    sampled = (
        text[:head_len]
        + _OMIT_MIDDLE
        + middle
        + _OMIT_MIDDLE
        + text[-tail_len:]
    )
    return sampled, True


def _keyword_windows(text: str, keywords: list[str], max_chars: int) -> tuple[str, bool]:
    """无稳定发言人结构时，按姓名/关注点取关键词窗口。"""
    spans: list[tuple[int, int]] = []
    for keyword in _dedupe(keywords):
        for match in re.finditer(re.escape(keyword), text):
            spans.append(
                (max(0, match.start() - _DEFAULT_RADIUS), min(len(text), match.end() + _DEFAULT_RADIUS))
            )
    if not spans:
        return "", False

    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1] + 100:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    body = _OMIT_WINDOW.join(text[start:end] for start, end in merged)
    return _sample_text(body, max_chars)


def build_personal_evidence_pack(
    transcript: str,
    user: dict[str, Any] | None,
    *,
    max_chars: int = PERSONAL_EVIDENCE_FULL_LIMIT,
) -> tuple[str, dict[str, Any]]:
    """构建个人视角建模证据包。

    返回 ``(evidence_text, stats)``。stats 只含统计值，不记录原文。
    """
    text = transcript or ""
    stats: dict[str, Any] = {
        "mode": "empty",
        "track": "",
        "kept": 0,
        "dropped": 0,
        "chars_in": len(text),
        "chars_out": 0,
        "fallback": False,
        "capped": False,
        "empty": not bool(text.strip()),
    }
    if not text.strip():
        return "", stats

    if max_chars <= 0:
        max_chars = PERSONAL_EVIDENCE_FULL_LIMIT

    if len(text) <= max_chars:
        body = text.strip()
        output = f"{_HEADER_FULL}\n\n{body}"
        stats.update(mode="full", chars_out=len(output))
        return output, stats

    profile = user if isinstance(user, dict) else {}
    name = str(profile.get("name") or "").strip()
    aliases = _dedupe([str(a) for a in (profile.get("name_aliases") or [])])
    addresses = _dedupe([name, *aliases])
    focus_persons = _dedupe([str(p) for p in (profile.get("focus_person") or [])])
    focus_things = _dedupe([str(t) for t in (profile.get("focus_thing") or [])])

    normalized = _strip_speaker_bullets(text)
    sliced, slice_stats = slice_transcript_for_person(
        normalized,
        addresses,
        full_name=name,
        min_keep_chars=200,
        self_label=name,
        focus_persons=focus_persons,
        focus_things=focus_things,
        user_profile=profile,
    )
    track = "" if slice_stats.get("fallback") else str(slice_stats.get("track") or "")
    if sliced.strip() and not slice_stats.get("fallback"):
        body, capped = _sample_text(sliced.strip(), max_chars)
        output = f"{_HEADER_SLICE}\n\n{body}"
        stats.update(
            mode="slice",
            track=track or "NAMED",
            kept=int(slice_stats.get("kept") or 0),
            dropped=int(slice_stats.get("dropped") or 0),
            chars_out=len(output),
            capped=capped,
        )
        return output, stats

    keywords = _dedupe([*addresses, *focus_persons, *focus_things])
    keyword_text, keyword_capped = _keyword_windows(text, keywords, max_chars)
    if keyword_text:
        output = f"{_HEADER_KEYWORD}\n\n{keyword_text}"
        stats.update(
            mode="keyword",
            track="KEYWORD",
            chars_out=len(output),
            capped=keyword_capped,
        )
        return output, stats

    body, capped = _sample_text(text.strip(), max_chars)
    output = f"{_HEADER_SAMPLE}\n\n{body}"
    stats.update(
        mode="sample",
        track=track or "SAMPLE",
        chars_out=len(output),
        fallback=True,
        capped=capped,
    )
    return output, stats


__all__ = [
    "PERSONAL_EVIDENCE_FULL_LIMIT",
    "build_personal_evidence_pack",
]
