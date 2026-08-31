from __future__ import annotations

import json

from supervisor import GlobalSupervisor

from client import LLMClient
from ....models import CatalogSupervisorReview
from ..contracts import CATALOG_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import CATALOG_SUPERVISOR_DOMAIN_PROMPT
from .catalog_agent import _catalog_structure_issues


def _draft_from_review_context(context: str) -> dict:
    blob = context or ""
    for marker in ("知识目录草稿：", "catalog草稿："):
        if marker in blob:
            blob = blob.rsplit(marker, 1)[1]
            break
    start = blob.find("{")
    if start < 0:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(blob[start:])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _local_review(context: str) -> CatalogSupervisorReview | None:
    draft = _draft_from_review_context(context)
    if not draft:
        return None
    issues = _catalog_structure_issues(draft)
    if issues:
        return CatalogSupervisorReview.validate(
            {
                "decision": "revise",
                "catalog_check": {"status": "fail", "findings": issues[:8]},
                "feedback": issues[:8],
            }
        )
    return CatalogSupervisorReview.validate(
        {
            "decision": "approve",
            "catalog_check": {"status": "pass", "findings": []},
            "feedback": [],
        }
    )


class CatalogSupervisor:
    """审核知识目录结构，不拦轻微标记偏差。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            CATALOG_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> CatalogSupervisorReview:
        local = _local_review(context)
        if local is not None:
            return local
        return await self.client.structured(
            self._system_prompt,
            context,
            CatalogSupervisorReview,
            CATALOG_SUPERVISOR_OUTPUT_CONTRACT, label='catalog/supervisor')

