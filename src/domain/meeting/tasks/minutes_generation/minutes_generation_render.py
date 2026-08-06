from __future__ import annotations

from collections.abc import AsyncIterator

from llm_client import LLMClient
from .prompts import MINUTES_RENDER_PROMPT, MINUTES_RENDER_TEMPLATE_PROMPT


class MinutesGenerationRender:
    """把已批准的纪要草稿渲染为最终正文（支持模板与流式）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        """组装渲染 prompt 与用户消息（普通与流式共用）。

        有模板时：模板原样拼进用户消息，不做任何包裹或修饰，
        模板是什么就输出什么（LLM 只替换占位符，其余逐字符保留）。
        """
        template = template or ""
        if template.strip():
            prompt = MINUTES_RENDER_TEMPLATE_PROMPT
            user = f"{context}\n\n{template}"
        else:
            prompt = MINUTES_RENDER_PROMPT
            user = context
        return prompt, user

    async def run(self, approved_context: str, template: str = "") -> str:
        """整段渲染纪要正文（纯文本）。"""
        prompt, user = self._prompt_and_user(approved_context, template)
        return await self.client.text(prompt, user)

    async def stream(self, approved_context: str, template: str = "") -> AsyncIterator[str]:
        """流式渲染纪要正文：LLM token 逐块产出（SSE）。"""
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user):
            yield chunk
