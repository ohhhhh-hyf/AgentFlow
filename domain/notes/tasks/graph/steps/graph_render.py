from __future__ import annotations

from collections.abc import AsyncIterator

import json

from tools.llm import LLMClient
from tools.exports.html.knowledge_graph import build_learning_map
from tools.core.prompt_utils import build_render_prompt

from ..prompts import KNOWLEDGE_GRAPH_RENDER_PROMPT, KNOWLEDGE_GRAPH_RENDER_TEMPLATE_PROMPT
from tools.core.domain_engine_text import scrape_draft


def _draft_from_context(approved_context: str) -> dict[str, Any]:
    """从渲染上下文里抽出已批准草稿（实现见 domain_engine_text.scrape_draft）。"""
    return scrape_draft(approved_context, ('已批准知识图谱草稿：',))


class KnowledgeGraphRender:
    """把已批准的知识图谱数据渲染为树形 Markdown 大纲。

    图数据（nodes/edges）经 Report 的 draft.nodes / draft.edges 字段
    直达导出层（交互 HTML 网状图谱）；本类只负责树形大纲文本。
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

    async def materialize(self, approved_context: str, template: str = "") -> str:
        """无模板时按 nodes/edges 拼学习地图，不调 LLM。"""
        del template
        draft = _draft_from_context(approved_context)
        return build_learning_map(
            list(draft.get("nodes") or []),
            list(draft.get("edges") or []),
            title=str(draft.get("title") or "").strip(),
        )

    async def run(self, approved_context: str, template: str = "") -> str:
        prompt, user = self._prompt_and_user(approved_context, template)
        try:
            return await self.client.text(prompt, user, label='graph/render')
        except TypeError:
            return await self.client.text(prompt, user, label='graph/render')

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user, label='graph/render'):
            yield chunk

