from __future__ import annotations

from llm_client import LLMClient

from ..models import NotesUnderstanding
from .contracts import NOTES_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT
from .prompts import NOTES_UNDERSTANDING_SYSTEM_PROMPT


class NotesUnderstandingAgent:
    """从笔记原文中提取主题、章节、术语和待澄清问题。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, transcript: str) -> NotesUnderstanding:
        return await self.client.structured(
            NOTES_UNDERSTANDING_SYSTEM_PROMPT,
            f"笔记原文：\n{transcript}",
            NotesUnderstanding,
            NOTES_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT,
            label="core/notes_understanding",
        )