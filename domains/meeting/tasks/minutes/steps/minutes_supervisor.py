from __future__ import annotations

from core.execution.hard_execution import (
    is_agenda_enhanced_mode,
    parse_perspective_mode,
    parse_lang_mode,
)
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

    async def review(self, context: str, *, lang: str | None = None) -> MinutesSupervisorReview:
        mode = parse_perspective_mode(context)
        is_agenda = is_agenda_enhanced_mode(context)
        if is_agenda:
            raw_domain_prompt = MINUTES_AGENDA_SUPERVISOR_PROMPT
            label_mode = "agenda"
        elif mode == "personal":
            raw_domain_prompt = MINUTES_PERSONAL_SUPERVISOR_PROMPT
            label_mode = "personal"
        else:
            raw_domain_prompt = MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
            label_mode = "objective"

        lang_val = lang or parse_lang_mode(context)
        if (lang_val or "").strip().lower() == "en":
            role_prefix = "英文（English）"
            body_prompt = raw_domain_prompt
            first_period = body_prompt.find("。\n")
            if first_period > 0:
                body_prompt = body_prompt[first_period + 2 :].strip()
            domain_prompt = (
                f"【核心人设与交付目标】\n"
                f"你是专职的【{role_prefix}】纪要质量监督者，本次任务基于统一标准严格审核{role_prefix}纪要草稿并决定放行或返工。\n\n"
                f"{body_prompt}\n\n"
                f"## 语言红线与审核准则\n"
                f"1. 严格拦截任何未翻译的中文残留段落；\n"
                f"2. 半角标点、[TBD] 状态标签与标准英文缩写属于标准公文规范，一律 approve 放行。"
            )
        else:
            domain_prompt = raw_domain_prompt

        system_prompt = GlobalSupervisor.build_prompt(domain_prompt)
        return await self.client.structured(
            system_prompt,
            context,
            self.review_model,
            self.output_contract,
            label=f"minutes/supervisor/{label_mode}",
            **self.extra_kwargs,
        )
