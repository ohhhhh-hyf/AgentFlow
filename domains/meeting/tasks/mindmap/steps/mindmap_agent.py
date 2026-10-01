from __future__ import annotations

from domains.shared.supervisor import StructuredGenerationAgent

from ....models import Mindmap
from ..contracts import MINDMAP_GENERATION_OUTPUT_CONTRACT
from ..prompts import MINDMAP_GENERATION_SYSTEM_PROMPT


class MindmapAgent(StructuredGenerationAgent):
    """Generate the structured 思维导图 draft."""

    system_prompt = MINDMAP_GENERATION_SYSTEM_PROMPT
    output_model = Mindmap
    output_contract = MINDMAP_GENERATION_OUTPUT_CONTRACT
    label = "mindmap/agent"
