"""Agent 2：Visual Extractor。"""
from __future__ import annotations

import logging
from typing import Optional

from ..llm import VisualLLM
from ..models.ir import SectionDecision, SectionVisual
from ..parsing.parser import SectionNode
from .prompts import EXTRACTOR_SYSTEM_PROMPT, build_extractor_user_prompt

logger = logging.getLogger(__name__)


class VisualExtractor:
    def __init__(self, llm: VisualLLM) -> None:
        self.llm = llm

    async def extract(
        self,
        section: SectionNode,
        decision: SectionDecision,
        transcript: str,
    ) -> Optional[SectionVisual]:
        if decision.visual == "none":
            return None

        try:
            raw = await self.llm.json_call(
                EXTRACTOR_SYSTEM_PROMPT,
                build_extractor_user_prompt(
                    {
                        "section_id": section.section_id,
                        "heading": section.heading,
                        "markdown": section.markdown,
                        "plain_text": section.plain_text,
                    },
                    decision.model_dump(),
                    transcript,
                ),
                label="visual_minutes/extractor",
            )
            kind = str(raw.get("kind") or "").strip()
            if kind == "none":
                return None
            if kind != decision.visual:
                raise ValueError(f"kind mismatch: {kind!r} != {decision.visual!r}")
            visual_payload = {
                "kind": kind,
                "title": str(raw.get("title") or section.heading),
                "data": raw.get("data") or {},
            }
            return SectionVisual(
                section_id=section.section_id,
                visual=visual_payload,
                confidence=float(decision.necessity or 0.0),
                evidence=[
                    str(e).strip()
                    for e in (raw.get("evidence") or [])
                    if str(e).strip()
                ],
            )
        except Exception:  # noqa: BLE001 - 单个 section 失败不影响其他 section
            logger.warning(
                "visual extractor failed section=%s kind=%s",
                section.section_id,
                decision.visual,
                exc_info=True,
            )
            return None


__all__ = ["VisualExtractor"]
