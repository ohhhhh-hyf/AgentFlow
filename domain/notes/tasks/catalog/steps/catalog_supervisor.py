from __future__ import annotations

from supervisor import GlobalSupervisor

from llm_client import LLMClient
from ....models import CatalogSupervisorReview
from ..contracts import CATALOG_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import CATALOG_SUPERVISOR_DOMAIN_PROMPT


class CatalogSupervisor:
    """审核知识目录结构，不拦轻微标记偏差。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            CATALOG_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> CatalogSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            CatalogSupervisorReview,
            CATALOG_SUPERVISOR_OUTPUT_CONTRACT, label='catalog/supervisor')
