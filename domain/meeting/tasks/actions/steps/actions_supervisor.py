from __future__ import annotations

from domain._shared import StructuredDomainSupervisor

from ....models import ActionItemsSupervisorReview
from ..contracts import ACTION_ITEMS_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import ACTION_ITEMS_SUPERVISOR_DOMAIN_PROMPT


class ActionItemsSupervisor(StructuredDomainSupervisor):
    """待办提取任务的领域监督者。

    prompt = 全局整体标准（注入） + 待办领域审核规则，
    一次 LLM 调用完成双重评判，决定 approve / revise / reject。
    """

    domain_prompt = ACTION_ITEMS_SUPERVISOR_DOMAIN_PROMPT
    review_model = ActionItemsSupervisorReview
    output_contract = ACTION_ITEMS_SUPERVISOR_OUTPUT_CONTRACT
    label = "actions/supervisor"
