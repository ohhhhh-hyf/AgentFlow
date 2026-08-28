from __future__ import annotations

from client import LLMClient
from tools.memory.graph import apply_graph_memory, sanitize_graph

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
            KNOWLEDGE_GRAPH_GENERATION_OUTPUT_CONTRACT, label='graph/agent')
        data = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
        # 生成侧校验：先剥悬空边/去重/规范化，再合并已积累图谱（拦截而非导出补救）
        data = sanitize_graph(data)
        merged = apply_graph_memory(data, shared_context)
        return KnowledgeGraph.validate(merged)

