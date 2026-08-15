from __future__ import annotations

from collections.abc import AsyncIterator

from llm_client import LLMClient
from tools.prompt_utils import build_render_prompt

from ....models import NotesState
from ..display import (
    build_review_markdown,
    draft_from_context,
    original_from_context,
)
from ..prompts import REVIEW_RENDER_PROMPT, REVIEW_RENDER_TEMPLATE_PROMPT


class ReviewRender:
    """默认按草稿确定性排版；仅当用户提供模板时才走 LLM 渲染。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        return build_render_prompt(
            context,
            template,
            REVIEW_RENDER_PROMPT,
            REVIEW_RENDER_TEMPLATE_PROMPT,
        )

    async def materialize(self, approved_context: str, template: str = "") -> str:
        del template
        draft = draft_from_context(approved_context)
        original = original_from_context(approved_context)
        return build_review_markdown(original, draft)

    async def run(self, approved_context: str, template: str = "") -> str:
        prompt, user = self._prompt_and_user(approved_context, template)
        temp = 0.0 if (template or "").strip() else None
        try:
            return await self.client.text(prompt, user, temperature=temp)
        except TypeError:
            return await self.client.text(prompt, user)

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user):
            yield chunk

    @staticmethod
    def extract_structure(state: NotesState) -> list[dict]:
        draft = (state.get("lines") or {}).get("review", {}).get("draft") or {}
        issues = draft.get("issues")
        return list(issues) if isinstance(issues, list) else []
