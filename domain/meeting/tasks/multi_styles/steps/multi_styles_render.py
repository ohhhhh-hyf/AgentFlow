from __future__ import annotations

import json
from collections.abc import AsyncIterator

from llm_client import LLMClient
from tools.prompt_utils import build_render_prompt

from ..prompts import MULTI_STYLES_RENDER_PROMPT, MULTI_STYLES_RENDER_TEMPLATE_PROMPT

def _draft_from_context(approved_context: str) -> dict:
    """从渲染上下文里抽出已批准草稿（取第一段可解析 JSON）。"""
    marker = "已批准多样式纪要草稿："
    blob = approved_context or ""
    if marker in blob:
        blob = blob.split(marker, 1)[1]
    start = blob.find("{")
    if start < 0:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(blob[start:])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


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
        return await self.client.text(prompt, user, label="multi_styles/render")

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        blocked = self._should_skip_llm(approved_context)
        if blocked is not None:
            yield blocked
            return
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user, label="multi_styles/render"):
            yield chunk
