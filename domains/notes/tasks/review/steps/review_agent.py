from __future__ import annotations

from domains.shared.supervisor import StructuredGenerationAgent

from ....models import Review
from ..contracts import REVIEW_GENERATION_OUTPUT_CONTRACT
from ..prompts import REVIEW_GENERATION_SYSTEM_PROMPT


class ReviewAgent(StructuredGenerationAgent):
    """从笔记中抽取知识点与记录问题。"""

    system_prompt = REVIEW_GENERATION_SYSTEM_PROMPT
    output_model = Review
    output_contract = REVIEW_GENERATION_OUTPUT_CONTRACT
    label = "review/agent"
