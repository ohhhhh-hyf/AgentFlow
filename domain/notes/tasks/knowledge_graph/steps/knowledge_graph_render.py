from __future__ import annotations

from collections.abc import AsyncIterator

import json

from client import LLMClient
from tools.knowledge_graph import build_learning_map
from tools.prompt_utils import build_render_prompt

from ..prompts import KNOWLEDGE_GRAPH_RENDER_PROMPT, KNOWLEDGE_GRAPH_RENDER_TEMPLATE_PROMPT


def _draft_from_context(approved_context: str) -> dict:
    marker = "已批准知识图谱草稿："
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
        temp = 0.0 if (template or "").strip() else None
        try:
            return await self.client.text(prompt, user, temperature=temp, label='knowledge_graph/render')
        except TypeError:
            return await self.client.text(prompt, user, label='knowledge_graph/render')

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user, label='knowledge_graph/render'):
            yield chunk

