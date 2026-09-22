from __future__ import annotations

import json
from collections.abc import AsyncIterator

from tools.llm import LLMClient
from tools.core.prompt_utils import build_render_prompt

from ..prompts import MULTI_STYLES_RENDER_PROMPT, MULTI_STYLES_RENDER_TEMPLATE_PROMPT
from tools.core.domain_engine_text import scrape_draft

def _draft_from_context(approved_context: str) -> dict[str, Any]:
    """从渲染上下文里抽出已批准草稿（实现见 domain_engine_text.scrape_draft）。"""
    return scrape_draft(approved_context, ('已批准多样式纪要草稿：',))


def _empty_render_text(draft: dict) -> str:
    title = str(draft.get("title") or "").strip() or "多样式纪要"
    return f"{title}\n\n暂无结构化段落"


class MultiStylesRender:
    """Render the approved 多样式纪要 result."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        return build_render_prompt(
            context,
            template,
            MULTI_STYLES_RENDER_PROMPT,
            MULTI_STYLES_RENDER_TEMPLATE_PROMPT,
        )

    @staticmethod
    def _should_skip_llm(approved_context: str) -> str | None:
        """只有草稿完全没有段落时才短路，避免对着空稿补一篇。"""
        draft = _draft_from_context(approved_context)
        sections = draft.get("sections")
        if not isinstance(sections, list) or not sections:
            return _empty_render_text(draft)
        return None

    async def run(self, approved_context: str, template: str = "") -> str:
        blocked = self._should_skip_llm(approved_context)
        if blocked is not None:
            return blocked
        prompt, user = self._prompt_and_user(approved_context, template)
        return await self.client.text(prompt, user, label="minutes_styles/render")

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        blocked = self._should_skip_llm(approved_context)
        if blocked is not None:
            yield blocked
            return
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user, label="minutes_styles/render"):
            yield chunk

