from __future__ import annotations

from collections.abc import AsyncIterator

from client import LLMClient

from ..display import build_checklist_markdown, draft_from_context


class ChecklistRender:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, approved_context: str, template: str = "") -> str:
        del template
        draft = draft_from_context(approved_context)
        if not (draft.get("cards") or draft.get("course")):
            return "没有可复习的知识点。请先运行 catalog / 资料入库；若提供了老师重点，请确认文本能对上目录名称。"
        return build_checklist_markdown(draft)

    async def stream(self, approved_context: str, template: str = "") -> AsyncIterator[str]:
        text = await self.run(approved_context, template)
        if text:
            yield text

