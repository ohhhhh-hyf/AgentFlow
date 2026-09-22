from __future__ import annotations

import json
from collections.abc import AsyncIterator

from tools.llm import LLMClient

from ....models import NotesState
from ..report import build_library_markdown
from tools.core.domain_engine_text import scrape_draft


def _draft_from_context(approved_context: str) -> dict[str, Any]:
    """从渲染上下文里抽出已批准草稿（实现见 domain_engine_text.scrape_draft）。"""
    return scrape_draft(approved_context, ('已批准资料入库草稿：', '已批准library草稿：'))


class LibraryRender:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def materialize(self, approved_context: str, template: str = "") -> str:
        del template
        return build_library_markdown(_draft_from_context(approved_context))

    async def run(self, approved_context: str, template: str = "") -> str:
        return await self.materialize(approved_context, template)

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        yield await self.materialize(approved_context, template)

