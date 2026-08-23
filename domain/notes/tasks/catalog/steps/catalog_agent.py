from __future__ import annotations

from client import LLMClient

from ....models import Catalog
from ..contracts import CATALOG_GENERATION_OUTPUT_CONTRACT
from ..gather import build_catalog_briefing, subject_from_context, user_id_from_context
from ..merge import merge_catalog, normalize_catalog_enums
from ..prompts import CATALOG_GENERATION_SYSTEM_PROMPT
from ..store import load_catalog


class CatalogAgent:
    """首次建目录；已有目录则增量合并，保持节点 ID 稳定。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Catalog:
        briefing = build_catalog_briefing(shared_context)
        draft = await self.client.structured(
            CATALOG_GENERATION_SYSTEM_PROMPT,
            briefing,
            Catalog,
            CATALOG_GENERATION_OUTPUT_CONTRACT, label='catalog/agent')
        merged = merge_catalog(
            load_catalog(
                user_id=user_id_from_context(shared_context),
                subject=subject_from_context(shared_context),
            ),
            draft.model_dump(),
        )
        merged = normalize_catalog_enums(merged)
        return Catalog.validate(merged)

