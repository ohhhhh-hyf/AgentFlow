from __future__ import annotations

import json
from collections.abc import AsyncIterator

from client import LLMClient

from ....models import NotesState
from ..report import build_library_markdown


def _draft_from_context(approved_context: str) -> dict:
    blob = approved_context or ""
    for marker in ("已批准资料入库草稿：", "已批准library草稿："):
        if marker in blob:
            blob = blob.split(marker, 1)[1]
            break
    start = blob.find("{")
    if start < 0:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(blob[start:])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


class LibraryRender:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def materialize(self, approved_context: str, template: str = "") -> str:
        del template
        return build_library_markdown(_draft_from_context(approved_context))

    async def run(self, approved_context: str, template: str = "") -> str:
        return await self.materialize(approved_context, template)

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        yield await self.materialize(approved_context, template)

    @staticmethod
    def extract_structure(state: NotesState) -> list[dict]:
        draft = (state.get("lines") or {}).get("library", {}).get("draft") or {}
        return list(draft.get("conflicts") or [])

