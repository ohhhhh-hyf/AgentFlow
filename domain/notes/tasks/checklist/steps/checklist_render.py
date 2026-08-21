from __future__ import annotations

from collections.abc import AsyncIterator

from llm_client import LLMClient

from ..display import build_checklist_markdown, draft_from_context


class ChecklistRender:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, approved_context: str, template: str = "") -> str:
        del template
        draft = draft_from_context(approved_context)
        if not (draft.get("cards") or draft.get("course")):
            return "没有从老师文本匹配到目录中的知识点。"
        return build_checklist_markdown(draft)

    async def stream(self, approved_context: str, template: str = "") -> AsyncIterator[str]:
        text = await self.run(approved_context, template)
        if text:
            yield text
