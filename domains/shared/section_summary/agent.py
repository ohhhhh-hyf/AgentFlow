"""Section Summary Agent：逐字稿 -> 分段速览 Markdown。"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from infra.llm import LLMClient

from .client import default_client
from .config import DEFAULT_TEMPERATURE, LLM_LABEL, USER_PROMPT
from .errors import SectionSummaryFormatError
from .fallback import fallback_sections
from .models import SectionSummary, SectionSummaryResult
from .parser import format_transcript_for_prompt, parse_transcript
from .prompts import build_prompt
from .renderer import render_markdown
from .validation import normalize_sections

logger = logging.getLogger(__name__)


class SectionSummaryAgent:
    """一次 LLM 调用完成切分 + 标题 + 关键词 + 纪要。"""

    def __init__(self, client: Optional[LLMClient] = None) -> None:
        self.client = client or default_client()

    async def arun(self, transcript: str) -> SectionSummaryResult:
        # 解析失败属于输入问题，直接抛给调用方，不做 LLM 兜底
        lines = parse_transcript(transcript)
        formatted = format_transcript_for_prompt(lines)

        warnings: List[str] = []
        sections: List[SectionSummary] = []
        raw = ""
        try:
            raw = await self.client.text(
                build_prompt(formatted),
                USER_PROMPT,
                temperature=DEFAULT_TEMPERATURE,
                json_mode=False,
                label=LLM_LABEL,
            )
            sections, norm_warnings = normalize_sections(raw, lines)
            warnings.extend(norm_warnings)
            if not sections:
                raise SectionSummaryFormatError("模型未返回有效分段")
        except Exception as exc:  # noqa: BLE001 - 视觉链路失败必须优雅降级
            logger.warning(
                "section summary failed; fallback applied",
                exc_info=True,
            )
            warnings.append(
                f"LLM 分段失败，已使用规则兜底：{str(exc)[:200]}"
            )
            sections = fallback_sections(lines)

        if not sections:
            warnings.append("规则兜底也未生成有效分段")

        markdown = render_markdown(sections)
        logger.info(
            "[section_summary] lines=%d sections=%d markdown_chars=%d warnings=%d",
            len(lines),
            len(sections),
            len(markdown),
            len(warnings),
        )
        return SectionSummaryResult(
            markdown=markdown,
            sections=sections,
            warnings=list(dict.fromkeys(warnings)),
            raw_response=raw,
        )

    def run(self, transcript: str) -> SectionSummaryResult:
        return asyncio.run(self.arun(transcript))


__all__ = ["SectionSummaryAgent"]
