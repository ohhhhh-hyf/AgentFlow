from __future__ import annotations

from typing import Any

from domains.shared.supervisor import StructuredDomainSupervisor

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

    async def review(self, context: str, **kwargs: Any) -> ActionItemsSupervisorReview:
        merged_kwargs = dict(self.extra_kwargs)
        valid_keys = {
            "temperature",
            "max_tokens",
            "timeout",
            "allow_missing",
            "preserve_content_on_validation_error",
        }
        for k, v in kwargs.items():
            if k in valid_keys:
                merged_kwargs[k] = v
        if "timeout" not in merged_kwargs:
            merged_kwargs["timeout"] = 45.0  # 防死锁硬超时防御
        return await self.client.structured(
            self._system_prompt,
            context,
            self.review_model,
            self.output_contract,
            label=self.label,
            **merged_kwargs,
        )
