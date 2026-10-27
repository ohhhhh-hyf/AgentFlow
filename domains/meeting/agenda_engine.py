from __future__ import annotations

import copy
from dataclasses import dataclass, field
import logging
from typing import Any

from domains.meeting.tasks.agenda_minutes.agenda_parser import (
    normalize_lang,
    parse_agenda_text,
)
from domains.meeting.tasks.agenda_minutes.alignment_engine import (
    align_agenda_with_transcript,
    group_transcript_blocks,
    is_trivial_ceremonial_item,
    DiscussionBlock,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidAgendaItem:
    """经审核确认现场实际深入讨论的有效业务/技术议题。"""

    seq: str
    title: str
    presenters: list[str] = field(default_factory=list)
    start_index: int = -1
    end_index: int = -1
    matched_blocks: list[DiscussionBlock] = field(default_factory=list)


@dataclass
class AgendaProcessResult:
    """议题提纯与全文打标综合处理结果。"""

    has_valid_agenda: bool
    valid_agendas: list[ValidAgendaItem]
    tagged_transcript: str


def _format_block(b: DiscussionBlock) -> str:
    sp = (b.speaker or "").strip()
    ts = (b.timestamp or "").strip()
    content = (b.content or "").strip()
    if sp and ts:
        return f"{sp} {ts}：{content}"
    if sp:
        return f"{sp}：{content}"
    return content


def build_tagged_transcript_with_head_tail(
    all_blocks: list[DiscussionBlock],
    valid_agendas: list[ValidAgendaItem],
) -> str:
    """按议题打标，同时物理保护首个议题前的开场白与末个议题后的会末定调。"""
    if not all_blocks:
        return ""
    if not valid_agendas:
        return "\n\n".join(_format_block(b) for b in all_blocks)

    # 找出所有实质议题发言块中的最小起始索引与最大结束索引
    all_valid_block_indices: list[int] = []
    for a in valid_agendas:
        for b in a.matched_blocks:
            all_valid_block_indices.append(b.index)

    if not all_valid_block_indices:
        return "\n\n".join(_format_block(b) for b in all_blocks)

    min_start_idx = min(all_valid_block_indices)
    max_end_idx = max(all_valid_block_indices)

    parts: list[str] = []

    # 0. 现场审定的有效议题清单（纯业务输入数据，供全链路节点作为客观事实基准读取）
    checklist_lines = [
        f"{i+1}. 议题：{a.title}（汇报人：{'、'.join(a.presenters) or '未指定'}）"
        for i, a in enumerate(valid_agendas)
    ]
    if checklist_lines:
        parts.append("【现场审定的有效议题清单】：\n" + "\n".join(checklist_lines))

    # 1. 头部保护：首个实质议题前的发言（开场白、背景动线）
    head_blocks = [b for b in all_blocks if b.index < min_start_idx]
    if head_blocks:
        head_text = "\n\n".join(_format_block(b) for b in head_blocks).strip()
        if head_text:
            parts.append(f"【会议开场背景与主线脉络】：\n{head_text}")

    # 2. 各实质有效议题切片（按现场实际先后时序排列）
    for a in valid_agendas:
        item_text = "\n\n".join(_format_block(b) for b in a.matched_blocks).strip()
        pres_str = "、".join(a.presenters) if a.presenters else "未指定"
        parts.append(
            f"════════════════════════════════════════\n"
            f"【议题 {a.seq}：{a.title}】（汇报人：{pres_str}）\n"
            f"{item_text}"
        )

    # 3. 尾部保护：末个实质议题后的发言（散会决议、领导最终拍板）
    tail_blocks = [b for b in all_blocks if b.index > max_end_idx]
    if tail_blocks:
        tail_text = "\n\n".join(_format_block(b) for b in tail_blocks).strip()
        if tail_text:
            parts.append(f"════════════════════════════════════════\n【会末收尾与全场定调】：\n{tail_text}")

    return "\n\n".join(parts)


def _extract_valid_agendas_from_alignment(
    alignment_res: Any, *, lang: str = "zh"
) -> list[ValidAgendaItem]:
    """从对齐结果中过滤出已讨论、非仪式的有效议题，并按现场时序排列。"""
    lang_key = normalize_lang(lang)
    valid_items: list[ValidAgendaItem] = []
    # 使用 chronological_alignments 确保时序遵循现场真实讨论先后
    for align in alignment_res.chronological_alignments:
        if align.status != "discussed":
            continue
        if is_trivial_ceremonial_item(align, lang=lang_key):
            continue
        if not align.matched_blocks:
            continue

        valid_items.append(
            ValidAgendaItem(
                seq=align.item.seq,
                title=align.item.title,
                presenters=list(align.item.presenters or []),
                start_index=align.start_index,
                end_index=align.end_index,
                matched_blocks=align.matched_blocks,
            )
        )
    return valid_items


_PROCESS_AGENDA_CACHE: dict[
    tuple[int, int, int, int, str, str, str], AgendaProcessResult
] = {}


def clear_agenda_engine_cache() -> None:
    """清空议程综合处理结果缓存（供单测使用）。"""
    _PROCESS_AGENDA_CACHE.clear()


def process_agenda_for_minutes(
    transcript: str, agenda_text: str, *, lang: str = "zh"
) -> AgendaProcessResult:
    """提取有效讨论议题，并生成带头尾保护的打标实录（单次解析与对齐）。"""
    t = (transcript or "").strip()
    a = (agenda_text or "").strip()
    if not t or not a:
        return AgendaProcessResult(
            has_valid_agenda=False,
            valid_agendas=[],
            tagged_transcript=transcript or "",
        )

    lang_key = normalize_lang(lang)
    cache_key = (
        hash(t),
        hash(a),
        len(t),
        len(a),
        t[:128],
        a[:128],
        lang_key,
    )
    if cache_key in _PROCESS_AGENDA_CACHE:
        logger.debug(
            "[AGENDA_ENGINE] 命中议程处理综合结果缓存 (有效议题: %d)",
            len(_PROCESS_AGENDA_CACHE[cache_key].valid_agendas),
        )
        return copy.deepcopy(_PROCESS_AGENDA_CACHE[cache_key])

    try:
        plan = parse_agenda_text(a, transcript=t)
        if not plan or not plan.items:
            empty_res = AgendaProcessResult(
                has_valid_agenda=False,
                valid_agendas=[],
                tagged_transcript=transcript or "",
            )
            if len(_PROCESS_AGENDA_CACHE) >= 64:
                _PROCESS_AGENDA_CACHE.pop(next(iter(_PROCESS_AGENDA_CACHE)))
            _PROCESS_AGENDA_CACHE[cache_key] = copy.deepcopy(empty_res)
            return empty_res

        alignment_res = align_agenda_with_transcript(plan, t, lang=lang_key)
        if not alignment_res or not alignment_res.alignments:
            empty_res = AgendaProcessResult(
                has_valid_agenda=False,
                valid_agendas=[],
                tagged_transcript=transcript or "",
            )
            if len(_PROCESS_AGENDA_CACHE) >= 64:
                _PROCESS_AGENDA_CACHE.pop(next(iter(_PROCESS_AGENDA_CACHE)))
            _PROCESS_AGENDA_CACHE[cache_key] = copy.deepcopy(empty_res)
            return empty_res

        valid_agendas = _extract_valid_agendas_from_alignment(
            alignment_res, lang=lang_key
        )
        if not valid_agendas:
            empty_res = AgendaProcessResult(
                has_valid_agenda=False,
                valid_agendas=[],
                tagged_transcript=transcript or "",
            )
            if len(_PROCESS_AGENDA_CACHE) >= 64:
                _PROCESS_AGENDA_CACHE.pop(next(iter(_PROCESS_AGENDA_CACHE)))
            _PROCESS_AGENDA_CACHE[cache_key] = copy.deepcopy(empty_res)
            return empty_res

        all_blocks = group_transcript_blocks(t, plan=plan)
        tagged = build_tagged_transcript_with_head_tail(all_blocks, valid_agendas)
        result = AgendaProcessResult(
            has_valid_agenda=True,
            valid_agendas=valid_agendas,
            tagged_transcript=tagged,
        )
        if len(_PROCESS_AGENDA_CACHE) >= 64:
            _PROCESS_AGENDA_CACHE.pop(next(iter(_PROCESS_AGENDA_CACHE)))
        _PROCESS_AGENDA_CACHE[cache_key] = copy.deepcopy(result)
        return result
    except Exception as err:
        logger.warning("process_agenda_for_minutes failed unexpectedly: %s", err, exc_info=True)
        return AgendaProcessResult(
            has_valid_agenda=False,
            valid_agendas=[],
            tagged_transcript=transcript or "",
        )


def probe_valid_agendas(
    transcript: str, agenda_text: str, *, lang: str = "zh"
) -> list[ValidAgendaItem]:
    """快速探测 docs 是否包含与会议转写实质对齐的有效讨论议题（纯 Python，零 LLM 调用）。"""
    res = process_agenda_for_minutes(transcript, agenda_text, lang=lang)
    return res.valid_agendas if res.has_valid_agenda else []
