from __future__ import annotations

from domain._shared import StructuredDomainSupervisor

from ....models import MinutesSupervisorReview
from ..contracts import MINUTES_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import MINUTES_SUPERVISOR_DOMAIN_PROMPT


class MinutesGenerationSupervisor(StructuredDomainSupervisor):
    """纪要生成任务的领域监督者。

    prompt = 全局整体标准（注入） + 纪要领域审核规则，
    一次 LLM 调用完成双重评判，决定 approve / revise / reject。
    """

    domain_prompt = MINUTES_SUPERVISOR_DOMAIN_PROMPT
    review_model = MinutesSupervisorReview
    output_contract = MINUTES_SUPERVISOR_OUTPUT_CONTRACT
    label = "minutes/supervisor"
    extra_kwargs = {"max_tokens": 3000}
