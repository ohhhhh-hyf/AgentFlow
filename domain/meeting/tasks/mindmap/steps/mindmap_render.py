from __future__ import annotations

from collections.abc import AsyncIterator

from llm_client import LLMClient
from tools.prompt_utils import build_render_prompt

from ..prompts import MINDMAP_RENDER_PROMPT, MINDMAP_RENDER_TEMPLATE_PROMPT


class MindmapRender:
    """Render the approved 思维导图 result."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        return build_render_prompt(
            context,
            template,
            MINDMAP_RENDER_PROMPT,
            MINDMAP_RENDER_TEMPLATE_PROMPT,
        )

    async def run(self, approved_context: str, template: str = "") -> str:
        prompt, user = self._prompt_and_user(approved_context, template)
        temp = 0.0 if (template or "").strip() else None
        try:
            return await self.client.text(prompt, user, temperature=temp, label="mindmap/render")
        except TypeError:
            return await self.client.text(prompt, user, label="mindmap/render")

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user, label="mindmap/render"):
            yield chunk
