from __future__ import annotations

import json
from collections.abc import AsyncIterator

from llm_client import LLMClient
from ..display import (
    build_last_class_html,
    build_last_class_markdown,
    draft_from_context,
    original_from_context,
    resolve_collection,
    subject_from_context,
    user_id_from_context,
)
from ..prompts import LAST_CLASS_RENDER_PROMPT, LAST_CLASS_RENDER_TEMPLATE_PROMPT


class LastClassRender:
    """默认按草稿确定性排版（知识库检索 + 来源挂载）；有模板时走 LLM 渲染。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def _collection(self, approved_context: str) -> str:
        return resolve_collection(
            user_id=user_id_from_context(approved_context),
            subject=subject_from_context(approved_context),
        )

    async def materialize(self, approved_context: str, template: str = "") -> str:
        del template
        draft = draft_from_context(approved_context)
        collection = self._collection(approved_context)
        original = original_from_context(approved_context) or approved_context
        return build_last_class_markdown(original, draft, collection)

    async def run(self, approved_context: str, template: str = "") -> str:
        draft = draft_from_context(approved_context)
        collection = self._collection(approved_context)
        # 确定性路径优先；无草稿时给提示
        if not draft.get("focus_points"):
            return "请直接参考老师划重点原文。"
        original = original_from_context(approved_context) or approved_context
        return build_last_class_markdown(original, draft, collection)

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        text = await self.run(approved_context, template)
        if text:
            yield text
