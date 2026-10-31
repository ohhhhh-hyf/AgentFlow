"""Visual Minutes 独立流水线。"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .agents.extractor import VisualExtractor
from .agents.master import MasterPlanner, fallback_master
from .agents.planner import SectionPlanner
from .config import MAX_EXTRACT_CONCURRENCY
from .llm import VisualLLM
from .models.ir import VisualDocumentIR
from .parsing.parser import parse_minutes
from .parsing.retrieval import retrieve_transcript
from .rendering.compositor import DocumentCompositor
from .validation.validator import validate_document

logger = logging.getLogger(__name__)


@dataclass
class VisualMinutesResult:
    """独立流水线的完整输出。"""

    html: str
    ir: VisualDocumentIR

    @property
    def warnings(self) -> List[str]:
        return self.ir.warnings


async def build_visual_ir(
    minutes_markdown: str,
    meeting_transcript: str,
    *,
    llm: VisualLLM | None = None,
) -> VisualDocumentIR:
    """执行 Parser → Planner → Extractor/Master → Validator。"""
    parsed = parse_minutes(minutes_markdown)
    if not parsed.sections:
        return VisualDocumentIR(master=fallback_master(parsed), sections=[])

    try:
        client = llm or VisualLLM()

        _t_plan_start = time.time()
        planner = SectionPlanner(client)
        plan = await planner.plan(parsed.sections)
        _plan_dur = round(time.time() - _t_plan_start, 2)
        decisions = plan.sections
        warnings = list(plan.warnings)
        planned = [d for d in decisions if d.visual != "none"]
        logger.info(
            "[visual_minutes:plan] sections=%d planned=%s dur=%.2fs",
            len(parsed.sections),
            ",".join(f"{d.section_id}:{d.visual}" for d in planned) or "none",
            _plan_dur,
        )

        _t_extract_start = time.time()
        master_planner = MasterPlanner(client)
        extractor = VisualExtractor(client)
        semaphore = asyncio.Semaphore(MAX_EXTRACT_CONCURRENCY)

        async def _extract(decision):
            section = next(
                (s for s in parsed.sections if s.section_id == decision.section_id),
                None,
            )
            if section is None:
                return None
            transcript = retrieve_transcript(section.plain_text, meeting_transcript)
            async with semaphore:
                return await extractor.extract(section, decision, transcript)

        master_task = asyncio.create_task(
            master_planner.plan(parsed, decisions, meeting_transcript)
        )
        extract_tasks = [asyncio.create_task(_extract(d)) for d in planned]
        results = await asyncio.gather(master_task, *extract_tasks)
        _extract_dur = round(time.time() - _t_extract_start, 2)
        logger.info(
            "[visual_minutes:extract] widgets=%d master=ok dur=%.2fs",
            len(planned),
            _extract_dur,
        )
        master_result = results[0]
        extracted = results[1:]
        warnings.extend(master_result.warnings)

        for decision, item in zip(planned, extracted):
            if item is None or item.visual is None:
                warnings.append(f"visual extraction failed: {decision.section_id}")

        visuals = [
            item for item in extracted if item is not None and item.visual is not None
        ]
        ir = VisualDocumentIR(
            master=master_result.master,
            sections=visuals,
            warnings=warnings,
        )
        return validate_document(ir, parsed)
    except Exception:  # noqa: BLE001 - 视觉链路整体失败时退回纯纪要
        logger.exception("visual pipeline failed; minutes-only fallback")
        ir = VisualDocumentIR(
            master=fallback_master(parsed),
            sections=[],
            warnings=["visual pipeline failed; minutes-only fallback"],
        )
        return validate_document(ir, parsed)


async def agenerate_visual_minutes(
    minutes_markdown: str,
    meeting_transcript: str,
    output_path: Optional[str] = None,
    *,
    llm: VisualLLM | None = None,
) -> VisualMinutesResult:
    """异步执行端到端流水线。"""
    ir = await build_visual_ir(minutes_markdown, meeting_transcript, llm=llm)
    parsed = parse_minutes(minutes_markdown)
    html = DocumentCompositor().composite(parsed, ir)
    logger.info(
        "[visual_minutes:render] html_bytes=%d warnings=%d",
        len(html.encode("utf-8")),
        len(ir.warnings),
    )
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
    return VisualMinutesResult(html=html, ir=ir)


def generate_visual_minutes(
    minutes_markdown: str,
    meeting_transcript: str,
    output_path: Optional[str] = None,
    *,
    llm: VisualLLM | None = None,
) -> VisualMinutesResult:
    """同步阻塞入口。"""
    return asyncio.run(
        agenerate_visual_minutes(
            minutes_markdown,
            meeting_transcript,
            output_path,
            llm=llm,
        )
    )


__all__ = [
    "VisualMinutesResult",
    "agenerate_visual_minutes",
    "build_visual_ir",
    "generate_visual_minutes",
]
