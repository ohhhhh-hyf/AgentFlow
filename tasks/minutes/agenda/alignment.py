"""agenda alignment -- 议题有效性判定与原文切片对齐引擎 (零旧代码依赖).

核心能力:
1. group_transcript_blocks: 按真实发言人与时间戳聚合为天然发言块 (DiscussionBlock);
2. 过滤会务动线与仪式性环节 (开场致辞、签到、茶歇、合影等非实质性研讨项);
3. 基于主讲人匹配与议题专名关联，将逐字稿切片精准映射到有效议程项;
4. build_tagged_transcript_with_head_tail: 物理保护开场背景与会末定调，生成结构化切片实录;
5. process_agenda_for_minutes: 统一对外纯算法接口，无大模型调用，毫秒级完成对齐。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .parser import (
    AgendaItemParsed,
    AgendaPlan,
    ensure_agenda_plan,
    match_presenter_name,
    normalize_lang,
)

logger = logging.getLogger("tasks.minutes.agenda.alignment")

_CEREMONIAL_KEYWORDS = {
    "开场致辞", "领导致辞", "致辞", "开场", "签到", "入场", "茶歇", "茶歇休息",
    "合影", "合照", "拍照", "拍照合影", "合影留念", "午餐", "就餐", "闭门研讨",
    "自由交流", "散会", "收尾", "休息", "乘车", "漫步",
}


@dataclass
class DiscussionBlock:
    """连续单人发言块."""

    speaker: str
    timestamp: str
    content: str
    index: int = 0


@dataclass
class ValidAgendaItem:
    """经审核确认现场实际深入讨论的有效业务/技术议题."""

    seq: str
    title: str
    presenters: list[str] = field(default_factory=list)
    start_index: int = -1
    end_index: int = -1
    matched_blocks: list[DiscussionBlock] = field(default_factory=list)


@dataclass
class AgendaProcessResult:
    """议题提纯与全文打标综合处理结果."""

    has_valid_agenda: bool
    valid_agendas: list[ValidAgendaItem]
    tagged_transcript: str


def group_transcript_blocks(transcript: str) -> list[DiscussionBlock]:
    """将会议转写文本聚合为发言块列表."""
    text = (transcript or "").strip()
    if not text:
        return []

    lines = text.splitlines()
    blocks: list[DiscussionBlock] = []

    # 匹配 "发言人 10:00:00: 内容" 或 "发言人: 内容"
    header_pattern = re.compile(
        r"^(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s+([^\n:：]{1,16})|([^\n:：]{1,16})\s*[:：]|\s*【([^\n】]{1,16})】\s*[:：]?)(.*)$"
    )

    curr_speaker = ""
    curr_ts = ""
    curr_lines: list[str] = []

    for line in lines:
        sline = line.strip()
        if not sline:
            continue

        m = header_pattern.match(sline)
        if m:
            # 结转上一个 block
            if curr_lines:
                blocks.append(
                    DiscussionBlock(
                        speaker=curr_speaker,
                        timestamp=curr_ts,
                        content="\n".join(curr_lines).strip(),
                        index=len(blocks),
                    )
                )
                curr_lines = []

            curr_ts = m.group(1) or ""
            curr_speaker = (m.group(2) or m.group(3) or m.group(4) or "").strip()
            rest = (m.group(5) or "").strip(" :：")
            if rest:
                curr_lines.append(rest)
        else:
            curr_lines.append(sline)

    if curr_lines:
        blocks.append(
            DiscussionBlock(
                speaker=curr_speaker,
                timestamp=curr_ts,
                content="\n".join(curr_lines).strip(),
                index=len(blocks),
            )
        )

    # 若未识别到任何发言人行，按自然段保底切分
    if not blocks and text:
        for p in text.split("\n\n"):
            p_str = p.strip()
            if p_str:
                blocks.append(
                    DiscussionBlock(
                        speaker="",
                        timestamp="",
                        content=p_str,
                        index=len(blocks),
                    )
                )

    return blocks


def is_trivial_ceremonial_item(
    item: AgendaItemParsed,
    matched_blocks: list[DiscussionBlock],
) -> bool:
    """判定一个议程项是否为纯会务过场或仪式性环节 (非实质性研讨项)."""
    title = (item.title or "").strip()
    has_ceremonial_word = any(w in title for w in _CEREMONIAL_KEYWORDS)

    if not has_ceremonial_word:
        return False

    # 若含有仪式关键词且没有明确技术主讲人，直接剔除
    if not item.presenters:
        return True

    # 现场发言极短 (< 100字) 且发言块很少，判定为过场吆喝
    total_chars = sum(len(b.content) for b in matched_blocks)
    if len(matched_blocks) <= 2 and total_chars < 100:
        return True

    return False


def _extract_keywords(title: str) -> list[str]:
    """从议题标题中提取有效关键词用于文本匹配."""
    cleaned = re.sub(r"^[0-9一二三四五六七八九十\.\、\s【】\[\]议题]+", "", title)
    segments = re.split(r"[与及和的在向从对关于、，,·\-_/\\|\s:：\(\)（）【】]+", cleaned)
    tokens = [s.strip() for s in segments if len(s.strip()) >= 2]
    return tokens


def align_agenda_with_transcript(
    plan: AgendaPlan,
    transcript: str,
) -> list[ValidAgendaItem]:
    """将既定议程与会议实录发言块进行双向打标对齐."""
    if not plan or not plan.items or not transcript.strip():
        return []

    blocks = group_transcript_blocks(transcript)
    if not blocks:
        return []

    # 准备每个议程项的特征
    item_features: list[dict[str, Any]] = []
    for it in plan.items:
        tokens = _extract_keywords(it.title)
        item_features.append({
            "item": it,
            "presenters": it.presenters or [],
            "tokens": tokens,
            "blocks": [],
        })

    # 为每个发言块计算与各议题的亲和度得分
    for block in blocks:
        best_idx = -1
        best_score = 0.0

        for idx, feat in enumerate(item_features):
            score = 0.0
            # 1. 发言人匹配 (权重极高)
            if block.speaker and feat["presenters"]:
                for p in feat["presenters"]:
                    if match_presenter_name(p, block.speaker) >= 0.8:
                        score += 5.0
                        break

            # 2. 议题专名/关键词命中
            for tok in feat["tokens"]:
                if tok in block.content:
                    score += 2.0

            if score > best_score:
                best_score = score
                best_idx = idx

        # 阈值判定：达到基本亲和度才挂入对应议题
        if best_idx != -1 and best_score >= 2.0:
            item_features[best_idx]["blocks"].append(block)

    valid_agendas: list[ValidAgendaItem] = []

    for feat in item_features:
        it: AgendaItemParsed = feat["item"]
        matched_blocks: list[DiscussionBlock] = feat["blocks"]

        # 检查是否包含实质讨论
        total_len = sum(len(b.content) for b in matched_blocks)
        if not matched_blocks or total_len < 40:
            continue

        # 检查是否为仪式性过场项
        if is_trivial_ceremonial_item(it, matched_blocks):
            logger.info("[AGENDA_ALIGN] 过滤仪式性过场议题: 《%s》", it.title)
            continue

        start_idx = min(b.index for b in matched_blocks)
        end_idx = max(b.index for b in matched_blocks)

        valid_agendas.append(
            ValidAgendaItem(
                seq=it.seq,
                title=it.title,
                presenters=list(it.presenters or []),
                start_index=start_idx,
                end_index=end_idx,
                matched_blocks=matched_blocks,
            )
        )

    # 按照现场实际开讲时序 (start_index) 排序
    valid_agendas.sort(key=lambda a: a.start_index)
    return valid_agendas


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
    """按议题切片打标，同时物理保护首个议题前的开场白与末个议题后的会末定调."""
    if not all_blocks:
        return ""
    if not valid_agendas:
        return "\n\n".join(_format_block(b) for b in all_blocks)

    all_valid_indices: list[int] = []
    for a in valid_agendas:
        for b in a.matched_blocks:
            all_valid_indices.append(b.index)

    if not all_valid_indices:
        return "\n\n".join(_format_block(b) for b in all_blocks)

    min_start_idx = min(all_valid_indices)
    max_end_idx = max(all_valid_indices)

    parts: list[str] = []

    # 0. 现场审定的有效议题清单
    checklist_lines = [
        f"{i+1}. 议题：{a.title}（汇报人：{'、'.join(a.presenters) or '未指定'}）"
        for i, a in enumerate(valid_agendas)
    ]
    if checklist_lines:
        parts.append("【现场审定的有效议题清单】：\n" + "\n".join(checklist_lines))

    # 1. 头部保护：开场白与背景
    head_blocks = [b for b in all_blocks if b.index < min_start_idx]
    if head_blocks:
        head_text = "\n\n".join(_format_block(b) for b in head_blocks).strip()
        if head_text:
            parts.append(f"【会议开场背景与主线脉络】：\n{head_text}")

    # 2. 各有效议题切片
    for i, a in enumerate(valid_agendas, 1):
        item_text = "\n\n".join(_format_block(b) for b in a.matched_blocks).strip()
        pres_str = "、".join(a.presenters) if a.presenters else "未指定"
        parts.append(
            f"════════════════════════════════════════\n"
            f"【议题 {i}：{a.title}】（汇报人：{pres_str}）\n"
            f"{item_text}"
        )

    # 3. 尾部保护：会末定调
    tail_blocks = [b for b in all_blocks if b.index > max_end_idx]
    if tail_blocks:
        tail_text = "\n\n".join(_format_block(b) for b in tail_blocks).strip()
        if tail_text:
            parts.append(f"════════════════════════════════════════\n【会末收尾与全场定调】：\n{tail_text}")

    return "\n\n".join(parts)


def process_agenda_for_minutes(
    transcript: str,
    agenda: AgendaPlan | dict[str, Any] | str = "",
) -> AgendaProcessResult:
    """提取有效讨论议题，并生成带头尾保护的打标实录 (纯 Python, 零 LLM 调用)."""
    t = (transcript or "").strip()
    if not t or (not agenda and agenda != 0):
        return AgendaProcessResult(
            has_valid_agenda=False,
            valid_agendas=[],
            tagged_transcript=transcript or "",
        )

    plan = ensure_agenda_plan(agenda, transcript=t)
    if not plan or not plan.items:
        return AgendaProcessResult(
            has_valid_agenda=False,
            valid_agendas=[],
            tagged_transcript=transcript or "",
        )

    valid_agendas = align_agenda_with_transcript(plan, t)
    if not valid_agendas:
        logger.info("[AGENDA] 实录中未对齐到任何实质讨论的有效议题，降级为普通纪要")
        return AgendaProcessResult(
            has_valid_agenda=False,
            valid_agendas=[],
            tagged_transcript=transcript or "",
        )

    all_blocks = group_transcript_blocks(t)
    tagged = build_tagged_transcript_with_head_tail(all_blocks, valid_agendas)
    return AgendaProcessResult(
        has_valid_agenda=True,
        valid_agendas=valid_agendas,
        tagged_transcript=tagged,
    )


def probe_valid_agendas(
    transcript: str,
    agenda: AgendaPlan | dict[str, Any] | str = "",
) -> list[ValidAgendaItem]:
    """快速探测是否包含与会议转写实质对齐的有效讨论议题."""
    res = process_agenda_for_minutes(transcript, agenda)
    return res.valid_agendas if res.has_valid_agenda else []
