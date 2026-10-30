"""Visual Minutes 兼容执行入口。

新实现由 planner / extractor / master / validator 组成；
本类保留旧调用方式，便于调用方平滑迁移。
"""
from __future__ import annotations

import asyncio

from .llm import VisualLLM
from .models.ir import VisualDocumentIR
from .pipeline import build_visual_ir


class VisualMinutesAgent:
    def __init__(self, llm: VisualLLM | None = None) -> None:
        self.llm = llm or VisualLLM()

    async def aextract_visual_ir(
        self,
        markdown_minutes: str,
        meeting_transcript: str,
    ) -> VisualDocumentIR:
        return await build_visual_ir(
            markdown_minutes,
            meeting_transcript,
            llm=self.llm,
        )

    def extract_visual_ir(
        self,
        markdown_minutes: str,
        meeting_transcript: str,
    ) -> VisualDocumentIR:
        return asyncio.run(
            self.aextract_visual_ir(markdown_minutes, meeting_transcript)
        )


__all__ = ["VisualMinutesAgent"]
