from __future__ import annotations

import json
from collections.abc import AsyncIterator

from llm_client import LLMClient

from ..align import stamp_minutes


def _draft_from_context(approved_context: str) -> dict:
    marker = "已批准溯源纪要草稿："
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


class MinutesTraceRender:
    """程序落钉，不让模型改标注格式。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, approved_context: str, template: str = "") -> str:
        del template
        draft = _draft_from_context(approved_context)
        body = str(draft.get("minutes_md") or "").strip()
        if not body:
            return "请直接参考会议原文。"
        alignments = [
            item
            for item in (draft.get("alignments") or [])
            if isinstance(item, dict)
        ]
        return stamp_minutes(body, alignments)

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        text = await self.run(approved_context, template)
        if text:
            yield text
