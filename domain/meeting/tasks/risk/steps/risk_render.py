from __future__ import annotations

from collections.abc import AsyncIterator

from llm_client import LLMClient
from tools.prompt_utils import build_render_prompt

from ....models import MeetingState
from ..prompts import RISK_RENDER_PROMPT, RISK_RENDER_TEMPLATE_PROMPT


class RiskRender:
    """把已批准的风险分析结果渲染为最终输出。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        return build_render_prompt(
            context,
            template,
            RISK_RENDER_PROMPT,
            RISK_RENDER_TEMPLATE_PROMPT,
        )

    async def run(self, approved_context: str, template: str = "") -> str:
        prompt, user = self._prompt_and_user(approved_context, template)
        return await self.client.text(prompt, user)

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user):
            yield chunk

    @staticmethod
    def extract_risks(state: MeetingState) -> list[dict]:
        draft = (
            (state.get("lines") or {})
            .get("risk", {})
            .get("draft")
            or {}
        )
        return list(draft.get("risks") or [])