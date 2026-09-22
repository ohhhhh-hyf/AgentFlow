from __future__ import annotations

from collections.abc import AsyncIterator

from tools.llm import LLMClient
from tools.exports.html.consensus_decision import format_consensus_decision_markdown
from tools.core.prompt_utils import build_render_prompt

from ....models import MeetingState
from ..prompts import (
    CONSENSUS_DECISION_RENDER_PROMPT,
    CONSENSUS_DECISION_RENDER_TEMPLATE_PROMPT,
)


class ConsensusDecisionRender:
    """把已批准的共识决策草稿渲染为最终输出。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        return build_render_prompt(
            context,
            template,
            CONSENSUS_DECISION_RENDER_PROMPT,
            CONSENSUS_DECISION_RENDER_TEMPLATE_PROMPT,
        )

    async def run(self, approved_context: str, template: str = "") -> str:
        prompt, user = self._prompt_and_user(approved_context, template)
        temp = 0.0 if (template or "").strip() else None
        try:
            return await self.client.text(
                prompt, user, temperature=temp, label="consensus_decision/render"
            )
        except TypeError:
            return await self.client.text(prompt, user, label="consensus_decision/render")

    @staticmethod
    def render_draft(state: dict) -> str:
        """无模板时按草稿字段直接排版麦肯锡决策备忘录质感的 Markdown，不调 LLM。"""
        draft = (
            (state.get("lines") or {})
            .get("consensus_decision", {})
            .get("draft")
            or {}
        )
        title = str(state.get("title") or "").strip()
        return format_consensus_decision_markdown(draft, title=title)

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(
            prompt, user, label="consensus_decision/render"
        ):
            yield chunk

    @staticmethod
    def extract_structure(state: MeetingState) -> list[dict]:
        """extract 种类的结构抽取入口。"""
        return ConsensusDecisionRender.extract_issues(state)

    @staticmethod
    def extract_issues(state: MeetingState) -> list[dict]:
        """从 state 中提取最终议题列表（结构化产出）。"""
        draft = (
            (state.get("lines") or {})
            .get("consensus_decision", {})
            .get("draft")
            or {}
        )
        return list(draft.get("issues") or [])
