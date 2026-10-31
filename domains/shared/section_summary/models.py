"""Section Summary 的数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class TranscriptLine:
    """一条带时间戳的发言。"""

    index: int
    timestamp: str
    seconds: int
    speaker: str
    text: str


class SectionSummary(BaseModel):
    """一个分段速览单元。"""

    model_config = ConfigDict(extra="ignore")

    time_start: str
    title: str
    key_words: List[str] = Field(default_factory=list)
    section_summary: str


@dataclass
class SectionSummaryResult:
    """分段速览的完整输出。"""

    markdown: str
    sections: List[SectionSummary] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    raw_response: str = ""


__all__ = ["SectionSummary", "SectionSummaryResult", "TranscriptLine"]
