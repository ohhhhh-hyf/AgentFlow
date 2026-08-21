from __future__ import annotations

from llm_client import LLMClient

from ....models import Mindmap
from ..contracts import MINDMAP_GENERATION_OUTPUT_CONTRACT
from ..prompts import MINDMAP_GENERATION_SYSTEM_PROMPT


class MindmapAgent:
    """Generate the structured 思维导图 draft."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Mindmap:
        return await self.client.structured(
            MINDMAP_GENERATION_SYSTEM_PROMPT,
            shared_context,
            Mindmap,
            MINDMAP_GENERATION_OUTPUT_CONTRACT,
            label="mindmap/agent",
        )
