from __future__ import annotations

from domain._shared import StructuredGenerationAgent

from ....models import Quiz
from ..contracts import QUIZ_GENERATION_OUTPUT_CONTRACT
from ..prompts import QUIZ_GENERATION_SYSTEM_PROMPT


class QuizAgent(StructuredGenerationAgent):
    """从笔记拆解可提问点并生成自测题。"""

    system_prompt = QUIZ_GENERATION_SYSTEM_PROMPT
    output_model = Quiz
    output_contract = QUIZ_GENERATION_OUTPUT_CONTRACT
    label = "quiz/agent"
