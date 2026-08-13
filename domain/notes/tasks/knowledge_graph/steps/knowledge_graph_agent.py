from __future__ import annotations

from llm_client import LLMClient
from tools.memory.graph import apply_graph_memory

from ....models import KnowledgeGraph
from ..contracts import KNOWLEDGE_GRAPH_GENERATION_OUTPUT_CONTRACT
from ..prompts import KNOWLEDGE_GRAPH_GENERATION_SYSTEM_PROMPT


class KnowledgeGraphAgent:
    """Generate the structured 知识图谱 draft."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> KnowledgeGraph:
        raw = await self.client.structured(
            KNOWLEDGE_GRAPH_GENERATION_SYSTEM_PROMPT,
            shared_context,
            KnowledgeGraph,
            KNOWLEDGE_GRAPH_GENERATION_OUTPUT_CONTRACT,
        )
        data = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
        merged = apply_graph_memory(data, shared_context)
        return KnowledgeGraph.validate(merged)
