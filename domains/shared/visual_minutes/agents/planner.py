"""Agent 1：Section Planner。"""
from __future__ import annotations

import logging
from typing import List

from ..llm import VisualLLM
from ..models.ir import PlannerResponse, SectionDecision
from ..parsing.parser import SectionNode
from .prompts import PLANNER_SYSTEM_PROMPT, build_planner_user_prompt

logger = logging.getLogger(__name__)


def _payload(section: SectionNode) -> dict:
    return {
        "section_id": section.section_id,
        "heading": section.heading,
        "level": section.level,
        "path": section.path,
        "text": section.plain_text[:1200],
    }


class SectionPlanner:
    def __init__(self, llm: VisualLLM) -> None:
        self.llm = llm

    async def plan(self, sections: List[SectionNode]) -> PlannerResponse:
        if not sections:
            return PlannerResponse(sections=[])

        try:
            raw = await self.llm.json_call(
                PLANNER_SYSTEM_PROMPT,
                build_planner_user_prompt([_payload(s) for s in sections]),
                label="visual_minutes/planner",
            )
        except Exception:  # noqa: BLE001 - 规划失败默认全部不出图
            logger.warning("section planner failed; fallback to none", exc_info=True)
            return PlannerResponse(
                sections=[
                    SectionDecision(
                        section_id=s.section_id,
                        visual="none",
                        necessity=0.0,
                        rationale="planner fallback",
                    )
                    for s in sections
                ],
                warnings=["section planner failed; all sections set to none"],
            )

        by_id: dict[str, SectionDecision] = {}
        warnings: list[str] = []
        raw_sections = raw.get("sections") if isinstance(raw, dict) else None
        if not isinstance(raw_sections, list):
            warnings.append("planner response missing sections")
            raw_sections = []
        for item in raw_sections:
            try:
                decision = SectionDecision.model_validate(item)
            except Exception:  # noqa: BLE001 - 单条非法只影响该条
                logger.warning("invalid planner decision ignored: %r", item)
                sid = item.get("section_id") if isinstance(item, dict) else None
                warnings.append(f"invalid planner decision ignored: {sid}")
                continue
            if decision.section_id in by_id:
                warnings.append(
                    f"duplicate planner decision ignored: {decision.section_id}"
                )
                continue
            by_id[decision.section_id] = decision

        known = {s.section_id for s in sections}
        for sid in by_id:
            if sid not in known:
                warnings.append(f"unknown planner section ignored: {sid}")

        normalized: list[SectionDecision] = []
        for section in sections:
            decision = by_id.get(section.section_id)
            if decision is None:
                warnings.append(f"missing planner decision: {section.section_id}")
                decision = SectionDecision(
                    section_id=section.section_id,
                    visual="none",
                    necessity=0.0,
                    rationale="missing planner decision",
                )
            normalized.append(decision)

        return PlannerResponse(sections=normalized, warnings=warnings)


__all__ = ["SectionPlanner"]
