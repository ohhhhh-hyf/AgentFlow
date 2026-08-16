from __future__ import annotations

from pathlib import Path

from llm_client import LLMClient

from ....models import Library
from ..report import expand_inputs, ingest_library, kb_from_env, source_paths_from_context


class LibraryAgent:
    """多文件入库，并计算知识增量与冲突。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Library:
        raw = source_paths_from_context(shared_context)
        if not raw:
            return Library.validate(
                {
                    "message": "没有找到入库文件。",
                    "increment": "0",
                    "files": [],
                    "increment_by_file": [],
                    "conflicts": [],
                    "items": [],
                }
            )
        try:
            data = ingest_library(kb_from_env(), expand_inputs(raw))
        except Exception as exc:
            return Library.validate(
                {
                    "message": str(exc),
                    "increment": "0",
                    "files": [],
                    "increment_by_file": [],
                    "conflicts": [],
                    "items": [],
                }
            )
        return Library.validate(data)
