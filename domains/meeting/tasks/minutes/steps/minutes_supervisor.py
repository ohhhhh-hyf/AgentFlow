from __future__ import annotations

from core.execution.hard_execution import is_agenda_enhanced_mode, parse_perspective_mode
from domains.shared.supervisor import GlobalSupervisor, StructuredDomainSupervisor

from ....models import MinutesSupervisorReview
from ..contracts import MINUTES_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import (
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
    MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
    MINUTES_PERSONAL_SUPERVISOR_PROMPT,
    MINUTES_SUPERVISOR_DOMAIN_PROMPT,
)


class MinutesGenerationSupervisor(StructuredDomainSupervisor):
    """纪要生成任务的领域监督者。

    双轨分流架构：
    - 客观模式：挂载 MINUTES_OBJECTIVE_SUPERVISOR_PROMPT，聚焦全员覆盖度与公文体放行；
    - 个人模式：挂载 MINUTES_PERSONAL_SUPERVISOR_PROMPT，聚焦个人动作省主语、看板合流与自适应降噪放行。
    """

    domain_prompt = MINUTES_SUPERVISOR_DOMAIN_PROMPT
    review_model = MinutesSupervisorReview
    output_contract = MINUTES_SUPERVISOR_OUTPUT_CONTRACT
    label = "minutes/supervisor"
    extra_kwargs = {"max_tokens": 3000}

    async def review(self, context: str) -> MinutesSupervisorReview:
        mode = parse_perspective_mode(context)
        is_agenda = is_agenda_enhanced_mode(context)
        if is_agenda:
            domain_prompt = MINUTES_AGENDA_SUPERVISOR_PROMPT
            label_mode = "agenda"
        elif mode == "personal":
            domain_prompt = MINUTES_PERSONAL_SUPERVISOR_PROMPT
            label_mode = "personal"
        else:
            domain_prompt = MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
            label_mode = "objective"
        system_prompt = GlobalSupervisor.build_prompt(domain_prompt)
        return await self.client.structured(
            system_prompt,
            context,
            self.review_model,
            self.output_contract,
            label=f"minutes/supervisor/{label_mode}",
            **self.extra_kwargs,
        )
