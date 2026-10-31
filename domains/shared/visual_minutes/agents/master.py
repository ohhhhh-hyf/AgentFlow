"""Agent 3：Master Visual Planner + 健壮 fallback。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from ..llm import VisualLLM
from ..models.ir import (
    BlockHighlight,
    CardItem,
    CardsData,
    CardsVisual,
    MasterBlock,
    MasterVisual,
    SectionDecision,
)
from ..parsing.parser import ParsedMinutes, SectionNode
from .prompts import MASTER_SYSTEM_PROMPT, build_master_user_prompt

logger = logging.getLogger(__name__)

# 结构性过滤词：用于过滤非业务议题的结构/通用栏目，确保通览立柱聚焦实质研讨
META_STRUCTURAL_HEADINGS = {
    # 概括与总结类
    "全文摘要",
    "摘要",
    "要点梳理",
    "主要议题",
    "会议记录",
    "结论定调",
    "结论",
    "会议结论",
    "后续安排",
    "待办事项",
    "待办清单",
    "行动项",
    # 智能章节 / 段落速览类（全文速览附录，正文原生呈现）
    "智能章节",
    "段落速览",
    "分段速览",
    "章节速览",
    # 金句引语类（正文原生引用块呈现）
    "金句总结",
    "金句时刻",
    "金句",
    "经典语录",
    "名言金句",
    "人物金句",
    "定调金句",
    # 问答对话类（正文原生问答列表呈现）
    "问答",
    "现场问答",
    "问答环节",
    "关键问答",
    "互动答疑",
    "答疑",
    "qa",
    "q&a",
    # 英文通用词
    "summary",
    "overview",
    "conclusion",
    "action items",
}


def _section_payload(section: SectionNode) -> dict:
    return {
        "section_id": section.section_id,
        "heading": section.heading,
        "level": section.level,
        "path": section.path,
        "text": section.plain_text[:1000],
    }


def fallback_master(parsed: ParsedMinutes) -> MasterVisual:
    """保证 master 稳定可用，优先遴选实质性研讨议题作为立柱标题。"""
    substantive = [
        s
        for s in parsed.sections
        if s.heading.strip().lower() not in META_STRUCTURAL_HEADINGS
    ]
    targets = substantive if substantive else parsed.sections
    targets = targets[:5]  # 最多 5 个 blocks

    blocks = []
    for s in targets:
        first_sentence = s.plain_text.split("。")[0].strip()
        summary = first_sentence[:60] if first_sentence else s.heading
        blocks.append(
            MasterBlock(
                section_ids=[s.section_id],
                title=s.heading,
                summary=summary,
                key_points=[],
                highlight=BlockHighlight(tag="核心议程", value=s.heading[:20]),
            )
        )

    if not blocks:
        blocks = [
            MasterBlock(
                section_ids=[s.section_id for s in parsed.sections[:1]],
                title=parsed.document_title or "会议核心议题",
                summary="会议核心内容已完成系统化梳理与提炼。",
                key_points=[],
                highlight=BlockHighlight(tag="核心结论", value="达成会议共识"),
            )
        ]

    card_items = [
        CardItem(
            tag=f"议题 {idx:02d}",
            title=b.title,
            summary=b.summary,
            key_points=b.key_points,
            highlight=b.highlight,
        )
        for idx, b in enumerate(blocks, start=1)
    ]
    cards_widget = CardsVisual(
        kind="cards",
        title="核心议题架构",
        data=CardsData(items=card_items),
    )

    return MasterVisual(
        headline=parsed.document_title or "会议核心议题通览",
        thesis="",
        widgets=[cards_widget],
        layout="grid",
        blocks=blocks,
        metrics=[],
    )


def _is_master_valid(master: MasterVisual, sections: List[SectionNode]) -> bool:
    """校验 Master 规划是否合法。"""
    if not master.headline or not master.headline.strip():
        return False

    # 1. 优先校验自主多组件流（widgets）
    if master.widgets and len(master.widgets) >= 1:
        return True

    # 2. 兼容校验经典单立柱块（blocks）
    if not master.blocks or len(master.blocks) < 1:
        return False

    meta_count = sum(
        1
        for b in master.blocks
        if b.title.strip().lower() in META_STRUCTURAL_HEADINGS
    )
    if meta_count >= len(master.blocks):
        return False

    known = {s.section_id for s in sections}
    for block in master.blocks:
        block.section_ids = [sid for sid in block.section_ids if sid in known]

    return True


@dataclass
class MasterPlanResult:
    master: MasterVisual
    warnings: List[str] = field(default_factory=list)


class MasterPlanner:
    def __init__(self, llm: VisualLLM) -> None:
        self.llm = llm

    async def plan(
        self,
        parsed: ParsedMinutes,
        decisions: List[SectionDecision],
        transcript: str = "",
    ) -> MasterPlanResult:
        if not parsed.sections:
            return MasterPlanResult(master=fallback_master(parsed))

        try:
            raw = await self.llm.json_call(
                MASTER_SYSTEM_PROMPT,
                build_master_user_prompt(
                    [_section_payload(s) for s in parsed.sections],
                    [d.model_dump() for d in decisions],
                    transcript=transcript,
                ),
                label="visual_minutes/master",
            )
            master = MasterVisual.model_validate(raw)
            if not _is_master_valid(master, parsed.sections):
                raise ValueError("master validation failed")
            return MasterPlanResult(master=master)
        except Exception:  # noqa: BLE001 - master 失败必须优雅降级
            logger.warning(
                "master planner failed; fallback to substantive section map",
                exc_info=True,
            )
            return MasterPlanResult(
                master=fallback_master(parsed),
                warnings=["master planner failed; substantive fallback applied"],
            )


__all__ = ["MasterPlanResult", "MasterPlanner", "fallback_master"]
