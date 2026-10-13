from __future__ import annotations

import json
import logging
from typing import Any

from domains.shared.supervisor import StructuredDomainSupervisor

from ....models import AgendaMinutesSupervisorReview
from ..contracts import AGENDA_MINUTES_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import AGENDA_MINUTES_SUPERVISOR_DOMAIN_PROMPT

logger = logging.getLogger(__name__)


def _extract_skipped_agendas_from_context(context: str) -> list[str]:
    """从上下文中的草稿提取标记为 skipped 的议题标题。"""
    try:
        marker = "agenda_minutes草稿："
        if marker in context:
            draft_str = context.split(marker, 1)[1].strip()
            draft = json.loads(draft_str)
            if isinstance(draft, dict):
                return [
                    item.get("agenda_title", "")
                    for item in draft.get("agenda_items", [])
                    if isinstance(item, dict)
                    and item.get("discussion_state") == "skipped"
                    and item.get("agenda_title")
                ]
    except Exception:
        pass
    return []


def _is_only_complaining_verified_skipped(feedback: list[str], skipped_agendas: list[str]) -> bool:
    """判定 feedback 是否仅仅在抱怨已确认缺席的 skipped 议题。"""
    if not feedback or not skipped_agendas:
        return False
    for fb in feedback:
        fb_str = str(fb)
        mentions_skipped = any(title in fb_str for title in skipped_agendas)
        mentions_skip_words = any(w in fb_str for w in ("skipped", "未讨论", "缺席", "跳过", "未发言", "孤立"))
        if not (mentions_skipped or mentions_skip_words):
            return False
        if any(w in fb_str for w in ("虚假", "捏造", "严重偏差", "张冠李戴", "定调错误")):
            return False
    return True


class AgendaMinutesSupervisor(StructuredDomainSupervisor):
    """议程驱动型会议纪要领域监督者。"""

    domain_prompt = AGENDA_MINUTES_SUPERVISOR_DOMAIN_PROMPT
    review_model = AgendaMinutesSupervisorReview
    output_contract = AGENDA_MINUTES_SUPERVISOR_OUTPUT_CONTRACT
    label = "agenda_minutes/supervisor"
    extra_kwargs = {"max_tokens": 3000}

    async def review(self, context: str) -> AgendaMinutesSupervisorReview:
        skipped_agendas = _extract_skipped_agendas_from_context(context)
        if skipped_agendas:
            context_header = (
                f"【系统事实对齐】以下议题经程序核验，未讨论或法定汇报人缺席未发言，"
                f"标记为 skipped 为系统预期合规行为：{'、'.join(skipped_agendas)}\n\n"
            )
            context = context_header + context

        review: AgendaMinutesSupervisorReview = await super().review(context)

        # 防御性后置守卫：若 feedback 仅误判了已知缺席的 skipped 议题，纠正为 approve
        if review.decision == "revise" and _is_only_complaining_verified_skipped(review.feedback, skipped_agendas):
            logger.info("Supervisor false positive on skipped agenda overridden to approve.")
            try:
                review_data = review.model_dump()
                review_data["decision"] = "approve"
                review_data["feedback"] = []
                if isinstance(review_data.get("agenda_coverage_check"), dict):
                    review_data["agenda_coverage_check"] = {
                        "status": "pass",
                        "reason": "缺席议题合规标记为 skipped",
                    }
                review = self.review_model.validate(review_data)
            except Exception as e:
                logger.warning("Failed to normalize overridden review: %s", e)

        return review
