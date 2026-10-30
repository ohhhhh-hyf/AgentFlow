"""Section 级原文检索。

只做轻量、确定性的相关片段选择，避免把整篇 transcript 塞给每个 section。
"""
from __future__ import annotations

import re
from typing import List

from ..config import TRANSCRIPT_CHAR_BUDGET


def _grams(text: str) -> set[str]:
    chars = re.sub(r"\s+", "", text or "")
    if len(chars) < 2:
        return {chars} if chars else set()
    return {chars[i : i + 2] for i in range(len(chars) - 1)}


def _blocks(transcript: str) -> List[str]:
    parts = re.split(r"\n\s*\n|(?<=[。！？!?])\s*(?=[^\s])", transcript or "")
    return [p.strip() for p in parts if p.strip()]


def retrieve_transcript(
    section_text: str,
    transcript: str,
    budget: int = TRANSCRIPT_CHAR_BUDGET,
) -> str:
    """按二元字重合度选相关段落；不足预算时按原顺序拼接。"""
    source = (transcript or "").strip()
    if not source:
        return ""
    if len(source) <= budget:
        return source

    blocks = _blocks(source)
    if not blocks:
        return source[:budget]

    target = _grams(section_text)
    scored: list[tuple[float, int, str]] = []
    for idx, block in enumerate(blocks):
        grams = _grams(block)
        overlap = len(target & grams) / max(1, len(grams))
        scored.append((overlap, idx, block))

    selected: list[tuple[int, str]] = []
    used = 0
    for score, idx, block in sorted(scored, key=lambda x: (-x[0], x[1])):
        if score <= 0:
            continue
        if used + len(block) > budget:
            continue
        selected.append((idx, block))
        used += len(block)
        if used >= budget:
            break

    if not selected:
        return source[:budget]
    selected.sort(key=lambda x: x[0])
    return "\n\n".join(block for _, block in selected)


__all__ = ["retrieve_transcript"]
