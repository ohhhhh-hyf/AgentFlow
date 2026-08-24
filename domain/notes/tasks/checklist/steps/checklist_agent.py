from __future__ import annotations

from client import LLMClient

from ....models import Checklist
from ..assemble import assemble_checklist
from ..contracts import CHECKLIST_GENERATION_OUTPUT_CONTRACT
from ..gather import build_checklist_briefing, load_session
from ..prompts import CHECKLIST_GENERATION_SYSTEM_PROMPT


class ChecklistAgent:
    """Catalog 定范围；有老师文本则激活重点，否则按目录+知识库写卡片。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Checklist:
        catalog, activated, teacher = load_session(shared_context)
        empty = {
            "course": "",
            "catalog_version": "",
            "cards": [],
            "uncertain_quotes": ["没有可用的知识目录，请先运行 catalog"],
            "strategy": [],
            "phases": [],
        }
        if not catalog:
            return Checklist.validate(empty)
        briefing = build_checklist_briefing(catalog, activated, teacher)
        llm_draft = await self.client.structured(
            CHECKLIST_GENERATION_SYSTEM_PROMPT,
            briefing,
            Checklist,
            CHECKLIST_GENERATION_OUTPUT_CONTRACT, label='checklist/agent')
        merged = assemble_checklist(catalog, activated, llm_draft.model_dump(), teacher)
        return Checklist.validate(merged)

