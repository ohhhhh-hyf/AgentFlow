"""规则兜底：LLM 失败时仍输出可读的分段速览。

兜底不做语义总结，只按时间间隔 / 时间窗切分，标题取正文首句，
纪要取正文前 200 字，并在结果里带 warning。
"""
from __future__ import annotations

from typing import List

from .config import FALLBACK_GAP_SECONDS, FALLBACK_WINDOW_SECONDS
from .models import SectionSummary, TranscriptLine
from .validation import clean_summary, fallback_title


def fallback_sections(
    lines: List[TranscriptLine],
    *,
    gap_seconds: int = FALLBACK_GAP_SECONDS,
    window_seconds: int = FALLBACK_WINDOW_SECONDS,
) -> List[SectionSummary]:
    if not lines:
        return []

    groups: List[List[TranscriptLine]] = []
    current: List[TranscriptLine] = [lines[0]]
    for line in lines[1:]:
        gap = line.seconds - current[-1].seconds
        span = line.seconds - current[0].seconds
        if gap > gap_seconds or span >= window_seconds:
            groups.append(current)
            current = [line]
        else:
            current.append(line)
    groups.append(current)

    sections: List[SectionSummary] = []
    for group in groups:
        text = " ".join(line.text for line in group if line.text).strip()
        if not text:
            continue
        summary = clean_summary(text)
        if not summary:
            continue
        sections.append(
            SectionSummary(
                time_start=group[0].timestamp,
                title=fallback_title(text),
                key_words=[],
                section_summary=summary,
            )
        )

    if sections and sections[0].time_start != lines[0].timestamp:
        sections[0] = sections[0].model_copy(
            update={"time_start": lines[0].timestamp}
        )
    return sections


__all__ = ["fallback_sections"]
