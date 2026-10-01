from __future__ import annotations

from collections.abc import AsyncIterator

from infra.llm import LLMClient
from core.runner.prompt_utils import build_render_prompt

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
        temp = 0.0 if (template or "").strip() else None
        try:
            return await self.client.text(prompt, user, temperature=temp, label="risk/render")
        except TypeError:
            return await self.client.text(prompt, user, label="risk/render")

    @staticmethod
    def render_draft(state: dict) -> str:
        """无模板时按草稿字段排清单，与渲染 prompt 格式一致，不调 LLM。"""
        from core.graph.engine_text import render_risk_items

        draft = (state.get("lines") or {}).get("risks", {}).get("draft") or {}
        items = draft.get("risks") or []
        return render_risk_items(items)

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user, label="risk/render"):
            yield chunk
