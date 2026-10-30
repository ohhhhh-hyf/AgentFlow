"""Agent 3：Master Visual Planner + 程序 fallback。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from ..llm import VisualLLM
from ..models.ir import MasterBlock, MasterVisual, SectionDecision
from ..parsing.parser import ParsedMinutes, SectionNode
from .prompts import MASTER_SYSTEM_PROMPT, build_master_user_prompt

logger = logging.getLogger(__name__)


def _section_payload(section: SectionNode) -> dict:
    return {
        "section_id": section.section_id,
        "heading": section.heading,
        "level": section.level,
        "path": section.path,
        "text": section.plain_text[:800],
    }


def fallback_master(parsed: ParsedMinutes) -> MasterVisual:
    """保证 master 永远存在，且覆盖所有一级 section。"""
    blocks = [
        MasterBlock(
            section_ids=[s.section_id],
            title=s.heading or f"章节 {s.order + 1}",
            summary=s.plain_text[:160],
            key_points=[],
        )
        for s in parsed.sections
    ]
    return MasterVisual(
        headline=parsed.document_title or "图文纪要",
        thesis=f"本纪要共 {len(parsed.sections)} 个主要章节。",
        layout="grid",
        blocks=blocks,
        metrics=[],
    )


def _coverage_ok(master: MasterVisual, sections: List[SectionNode]) -> bool:
    expected = {s.section_id for s in sections}
    seen: set[str] = set()
    for block in master.blocks:
        for sid in block.section_ids:
            if sid in seen:
                return False
            seen.add(sid)
    return seen == expected


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
    ) -> MasterPlanResult:
        if not parsed.sections:
            return MasterPlanResult(master=fallback_master(parsed))

        try:
            raw = await self.llm.json_call(
                MASTER_SYSTEM_PROMPT,
                build_master_user_prompt(
                    [_section_payload(s) for s in parsed.sections],
                    [d.model_dump() for d in decisions],
                ),
                label="visual_minutes/master",
            )
            master = MasterVisual.model_validate(raw)
            if not master.headline.strip():
                raise ValueError("master headline is empty")
            if not _coverage_ok(master, parsed.sections):
                raise ValueError("master does not cover all primary sections")
            return MasterPlanResult(master=master)
        except Exception:  # noqa: BLE001 - master 失败必须降级
            logger.warning("master planner failed; fallback to section map", exc_info=True)
            return MasterPlanResult(
                master=fallback_master(parsed),
                warnings=["master planner failed; fallback applied"],
            )


__all__ = ["MasterPlanResult", "MasterPlanner", "fallback_master"]
