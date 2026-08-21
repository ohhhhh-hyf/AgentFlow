from __future__ import annotations

from collections.abc import AsyncIterator

from llm_client import LLMClient
from tools.prompt_utils import build_render_prompt

from ....models import NotesState
from ..display import (
    build_quiz_markdown,
    draft_from_context,
    extra_from_context,
    original_from_context,
)
from ..prompts import QUIZ_RENDER_PROMPT, QUIZ_RENDER_TEMPLATE_PROMPT


class QuizRender:
    """默认按草稿做成折叠答案卷；仅当用户提供模板时才走 LLM 渲染。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        return build_render_prompt(
            context,
            template,
            QUIZ_RENDER_PROMPT,
            QUIZ_RENDER_TEMPLATE_PROMPT,
        )

    async def materialize(self, approved_context: str, template: str = "") -> str:
        del template
        draft = draft_from_context(approved_context)
        notes = original_from_context(approved_context)
        extra = extra_from_context(approved_context)
        return build_quiz_markdown(draft, notes=notes, extra=extra)

    async def run(self, approved_context: str, template: str = "") -> str:
        prompt, user = self._prompt_and_user(approved_context, template)
        temp = 0.0 if (template or "").strip() else None
        try:
            return await self.client.text(prompt, user, temperature=temp, label='quiz/render')
        except TypeError:
            return await self.client.text(prompt, user, label='quiz/render')

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user, label='quiz/render'):
            yield chunk

    @staticmethod
    def extract_structure(state: NotesState) -> list[dict]:
        draft = (state.get("lines") or {}).get("quiz", {}).get("draft") or {}
        questions = draft.get("questions")
        return list(questions) if isinstance(questions, list) else []
