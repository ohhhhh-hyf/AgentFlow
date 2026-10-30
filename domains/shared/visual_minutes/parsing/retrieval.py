"""Section 级现场原文智能检索（高保真段落检索版）。

以自然发言段落为基本单位，基于关键词与字二元组加权匹配，
挑选与当前 Section 最相关的连贯现场原文，避免句子碎片化。
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


def _paragraphs(transcript: str) -> List[str]:
    # 优先按两个以上换行符（发言人切换段落）切分
    parts = [p.strip() for p in re.split(r"\n{2,}", transcript or "") if p.strip()]
    if len(parts) >= 3:
        return parts

    # 兜底：若无双换行，按发言人时间戳行（如 "张三 00:12:30"）切分
    parts = [
        p.strip()
        for p in re.split(r"(?=\n[^\n]{1,15}\s+\d{1,2}:\d{2})", transcript or "")
        if p.strip()
    ]
    if len(parts) >= 3:
        return parts

    # 再次兜底：按单换行切分
    return [line.strip() for line in (transcript or "").splitlines() if line.strip()]


def retrieve_transcript(
    section_text: str,
    transcript: str,
    budget: int = TRANSCRIPT_CHAR_BUDGET,
) -> str:
    """挑选与当前 section 相关性最高的连贯原文段落。"""
    source = (transcript or "").strip()
    if not source:
        return ""
    if len(source) <= budget:
        return source

    blocks = _paragraphs(source)
    if not blocks:
        return source[:budget]

    target_grams = _grams(section_text)
    if not target_grams:
        return source[:budget]

    # 计算匹配分数：重合二元组数量 / sqrt(段落长度)，平衡相关度与段落饱满度
    scored: list[tuple[float, int, str]] = []
    for idx, block in enumerate(blocks):
        bg = _grams(block)
        if not bg:
            continue
        common = len(target_grams & bg)
        score = common / (len(bg) ** 0.5)
        scored.append((score, idx, block))

    selected: list[tuple[int, str]] = []
    used = 0
    for score, idx, block in sorted(scored, key=lambda x: (-x[0], x[1])):
        if score <= 0.05:
            continue
        if used + len(block) > budget:
            continue
        selected.append((idx, block))
        used += len(block)
        if used >= budget:
            break

    if not selected:
        return source[:budget]

    # 按原文时序还原拼接
    selected.sort(key=lambda x: x[0])
    return "\n\n".join(block for _, block in selected)


__all__ = ["retrieve_transcript"]
