from __future__ import annotations

from collections.abc import AsyncIterator

from tools.llm import LLMClient
from tools.core.prompt_utils import build_render_prompt
from tools.exports.html.agenda_minutes import format_agenda_minutes_markdown

from ....models import MeetingState
from ..prompts import AGENDA_MINUTES_RENDER_PROMPT, AGENDA_MINUTES_RENDER_TEMPLATE_PROMPT


class AgendaMinutesRender:
    """把已批准的议程驱动纪要草稿渲染为最终正文（支持普通排版与模板渲染）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        return build_render_prompt(
            context,
            template,
            AGENDA_MINUTES_RENDER_PROMPT,
            AGENDA_MINUTES_RENDER_TEMPLATE_PROMPT,
        )

    async def run(self, approved_context: str, template: str = "") -> str:
        prompt, user = self._prompt_and_user(approved_context, template)
        temp = 0.0 if (template or "").strip() else None
        return await self.client.text(
            prompt, user, temperature=temp, label="agenda_minutes/render"
        )

    @staticmethod
    def render_draft(state: dict) -> str:
        """无模板时按草稿字段直接排版高规格议程全景 Markdown，0 额外 LLM 开销。"""
        draft = (
            (state.get("lines") or {})
            .get("agenda_minutes", {})
            .get("draft")
            or {}
        )
        return format_agenda_minutes_markdown(draft)

    @staticmethod
    def extract_structure(state: dict) -> list[dict]:
        """提取结构化议题列表，供 Report 与下游消费。"""
        draft = (
            (state.get("lines") or {})
            .get("agenda_minutes", {})
            .get("draft")
            or {}
        )
        return list(draft.get("agenda_items") or [])

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(
            prompt, user, label="agenda_minutes/render"
        ):
            yield chunk
