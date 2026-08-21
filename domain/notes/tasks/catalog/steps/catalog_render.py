from __future__ import annotations

from collections.abc import AsyncIterator

from llm_client import LLMClient

from ..display import build_catalog_markdown, draft_from_context, normalize_catalog_draft


class CatalogRender:
    """按已批准草稿排成目录 Markdown。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, approved_context: str, template: str = "") -> str:
        del template
        draft = normalize_catalog_draft(draft_from_context(approved_context))
        if not (draft.get("chapters") or draft.get("course")):
            return "这次没有整理出可用目录，已有目录文件不会被空结果覆盖。"
        return build_catalog_markdown(draft)

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        text = await self.run(approved_context, template)
        if text:
            yield text
