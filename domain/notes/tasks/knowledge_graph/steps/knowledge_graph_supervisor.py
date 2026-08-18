from __future__ import annotations

from supervisor import GlobalSupervisor

from llm_client import LLMClient
from ....models import KnowledgeGraphSupervisorReview
from ..contracts import KNOWLEDGE_GRAPH_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import KNOWLEDGE_GRAPH_SUPERVISOR_DOMAIN_PROMPT


class KnowledgeGraphSupervisor:
    """Review the 知识图谱 draft."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            KNOWLEDGE_GRAPH_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> KnowledgeGraphSupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            KnowledgeGraphSupervisorReview,
            KNOWLEDGE_GRAPH_SUPERVISOR_OUTPUT_CONTRACT, label='knowledge_graph/supervisor')
