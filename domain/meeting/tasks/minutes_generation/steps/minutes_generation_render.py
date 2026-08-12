from __future__ import annotations

from collections.abc import AsyncIterator

from tools.prompt_utils import build_render_prompt

from llm_client import LLMClient
from ..prompts import MINUTES_RENDER_PROMPT, MINUTES_RENDER_TEMPLATE_PROMPT


class MinutesGenerationRender:
    """把已批准的纪要草稿渲染为最终正文（支持模板与流式）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        """组装渲染 prompt 与用户消息（普通与流式共用）。

        模板分支逻辑由 tools.prompt_utils.build_render_prompt 提供：
        有模板时模板原样拼进用户消息（LLM 只替换占位符，其余逐字符保留）。
        """
        return build_render_prompt(
            context,
            template,
            MINUTES_RENDER_PROMPT,
            MINUTES_RENDER_TEMPLATE_PROMPT,
        )

    async def run(self, approved_context: str, template: str = "") -> str:
        """整段渲染纪要正文（纯文本）。有模板时用低温度稳住结构。"""
        prompt, user = self._prompt_and_user(approved_context, template)
        temp = 0.0 if (template or "").strip() else None
        try:
            return await self.client.text(prompt, user, temperature=temp)
        except TypeError:
            return await self.client.text(prompt, user)

    async def stream(self, approved_context: str, template: str = "") -> AsyncIterator[str]:
        """流式渲染纪要正文：LLM token 逐块产出（SSE）。"""
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user):
            yield chunk
