from __future__ import annotations

import json
import logging
from typing import Any

from infra.llm import LLMClient
from .models import PerspectiveModeling
from .prompts import PERSPECTIVE_MODELING_SYSTEM_PROMPT
from .contracts import PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT
from .personal_contracts import (
    PERSONAL_PERSPECTIVE_GENERATION_OUTPUT_CONTRACT,
    PERSONAL_PROFILE_FIELDS,
    PERSONAL_UNDERSTANDING_FIELDS,
)
from .personal_models import PersonalPerspective
from .personal_prompts import (
    PERSONAL_PERSPECTIVE_MODELING_SYSTEM_PROMPT,
    PERSONAL_PERSPECTIVE_PROMPT_VERSION,
)

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _pick_fields(value: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    data = _as_dict(value)
    return {field: data[field] for field in fields if field in data}


class PerspectiveModelingAgent:
    """Map a static user profile onto the current input context."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(
        self,
        input_context: str,
        user_json: str,
    ) -> PerspectiveModeling:
        return await self.client.structured(
            PERSPECTIVE_MODELING_SYSTEM_PROMPT,
            f"用户画像：\n{user_json}\n\n当前输入材料：\n{input_context}",
            PerspectiveModeling,
            PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT,
            label="core/perspective_modeling",
        )

    async def run_personal(
        self,
        understanding: dict[str, Any],
        evidence_pack: str,
        user_profile: dict[str, Any],
    ) -> PersonalPerspective:
        """个人单线 minutes 的视角建模：7 字段理解 + 证据包 + 6 字段画像。"""
        understanding_7 = _pick_fields(understanding, PERSONAL_UNDERSTANDING_FIELDS)
        profile_6 = _pick_fields(user_profile, PERSONAL_PROFILE_FIELDS)
        user_prompt = (
            "【用户画像】\n"
            f"{json.dumps(profile_6, ensure_ascii=False, indent=2, default=str)}\n\n"
            "【会议理解】\n"
            f"{json.dumps(understanding_7, ensure_ascii=False, indent=2, default=str)}\n\n"
            "【个人证据包】\n"
            f"{str(evidence_pack or '').strip()}"
        )
        logger.debug(
            "personal perspective prompt_version=%s understanding_fields=%d profile_fields=%d evidence_chars=%d",
            PERSONAL_PERSPECTIVE_PROMPT_VERSION,
            len(understanding_7),
            len(profile_6),
            len(str(evidence_pack or "")),
        )
        return await self.client.structured(
            PERSONAL_PERSPECTIVE_MODELING_SYSTEM_PROMPT,
            user_prompt,
            PersonalPerspective,
            PERSONAL_PERSPECTIVE_GENERATION_OUTPUT_CONTRACT,
            label="core/personal_perspective",
        )

