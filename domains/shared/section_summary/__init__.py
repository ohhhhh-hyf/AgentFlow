"""Section Summary（会议分段速览）。

输入带时间戳的会议逐字稿，输出：

    time_start  title
    关键词：kw1、kw2、kw3
    section_summary
"""
from __future__ import annotations

from typing import Optional

from infra.llm import LLMClient

from .agent import SectionSummaryAgent
from .errors import (
    SectionSummaryError,
    SectionSummaryFormatError,
    SectionSummaryInputError,
)
from .models import SectionSummary, SectionSummaryResult
from .parser import format_transcript_for_prompt, parse_transcript
from .prompts import SECTION_SUMMARY_PROMPT
from .renderer import render_markdown


async def agenerate_section_summary(
    transcript: str,
    *,
    client: Optional[LLMClient] = None,
) -> SectionSummaryResult:
    """异步：逐字稿 -> 分段速览结果。"""
    return await SectionSummaryAgent(client=client).arun(transcript)


def generate_section_summary(
    transcript: str,
    *,
    client: Optional[LLMClient] = None,
) -> SectionSummaryResult:
    """同步：逐字稿 -> 分段速览结果。"""
    return SectionSummaryAgent(client=client).run(transcript)


def generate_section_summary_markdown(
    transcript: str,
    *,
    client: Optional[LLMClient] = None,
) -> str:
    """同步：逐字稿 -> 分段速览 Markdown。"""
    return generate_section_summary(transcript, client=client).markdown


__all__ = [
    "SECTION_SUMMARY_PROMPT",
    "SectionSummary",
    "SectionSummaryAgent",
    "SectionSummaryError",
    "SectionSummaryFormatError",
    "SectionSummaryInputError",
    "SectionSummaryResult",
    "agenerate_section_summary",
    "format_transcript_for_prompt",
    "generate_section_summary",
    "generate_section_summary_markdown",
    "parse_transcript",
    "render_markdown",
]
