from __future__ import annotations

from collections.abc import AsyncIterator

from llm_client import LLMClient
from tools.prompt_utils import build_render_prompt

from ..prompts import KNOWLEDGE_GRAPH_RENDER_PROMPT, KNOWLEDGE_GRAPH_RENDER_TEMPLATE_PROMPT


class KnowledgeGraphRender:
    """把已批准的知识图谱数据渲染为树形 Markdown 大纲。

    图数据（nodes/edges）经 Report 的 draft.nodes / draft.edges 字段
    直达 bootstrap，由 graphviz 渲染网状知识图谱；本类只负责树形大纲文本。
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        return build_render_prompt(
            context,
            template,
            KNOWLEDGE_GRAPH_RENDER_PROMPT,
            KNOWLEDGE_GRAPH_RENDER_TEMPLATE_PROMPT,
        )

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
