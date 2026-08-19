from __future__ import annotations

import re
from pathlib import Path

from llm_client import LLMClient
from tools.knowledge.tool import collection_for

from ....models import Library
from ..report import expand_inputs, ingest_library, kb_from_env, source_paths_from_context


def _subject_from_context(text: str) -> str:
    """从共享上下文提取「【学科/课程】xxx」，供按学科分库。"""
    m = re.search(r"【学科/课程】\s*([^【】\n]+)", text or "")
    return m.group(1).strip() if m else ""


def _user_id_from_context(text: str) -> str:
    """从共享上下文提取「【用户ID】xxx」，供按用户隔离知识库。"""
    m = re.search(r"【用户ID】\s*([^【】\n]+)", text or "")
    return m.group(1).strip() if m else ""


class LibraryAgent:
    """多文件入库，并计算知识增量与冲突（按用户 + 学科分库）。"""

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
            data = ingest_library(
                kb_from_env(),
                expand_inputs(raw),
                user_id=_user_id_from_context(shared_context),
                subject=_subject_from_context(shared_context),
            )
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
