from __future__ import annotations

from domain._shared import StructuredDomainSupervisor

from ....models import KnowledgeGraphSupervisorReview
from ..contracts import KNOWLEDGE_GRAPH_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import KNOWLEDGE_GRAPH_SUPERVISOR_DOMAIN_PROMPT


class KnowledgeGraphSupervisor(StructuredDomainSupervisor):
    """Review the 知识图谱 draft."""

    domain_prompt = KNOWLEDGE_GRAPH_SUPERVISOR_DOMAIN_PROMPT
    review_model = KnowledgeGraphSupervisorReview
    output_contract = KNOWLEDGE_GRAPH_SUPERVISOR_OUTPUT_CONTRACT
    label = "graph/supervisor"
    extra_kwargs = {"temperature": 0.0}
