from __future__ import annotations

from collections.abc import AsyncIterator

from infra.llm import LLMClient
from core.runner.prompt_utils import build_render_prompt

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
    def render_draft(state: dict) -> str:
        """把已批准的共识决策草稿纯 Python 确定性组装为规范 Markdown 正文（零 LLM 调用）。"""
        draft = (
            (state.get("lines") or {})
            .get("consensus_decision", {})
            .get("draft")
            or {}
        )
        if not draft:
            return "暂无明确共识与因果决策议题"

        summary = draft.get("summary") or {}
        health_headline = str(summary.get("health_headline") or "").strip()
        issues = list(draft.get("issues") or [])

        grade_map = {
            "hard_alignment": "一致赞成",
            "conditional_concession": "附带前提同意",
            "unresolved_concern": "保留意见",
            "active_disagreement": "分歧待决",
        }

        blocks: list[str] = ["# 会议共识与因果决策分析"]
        if health_headline:
            blocks.append(f"> 🎯 **决策总评**：{health_headline}")

        if not issues:
            blocks.append("暂无明确共识与因果决策议题")
            return "\n\n".join(blocks)

        for idx, item in enumerate(issues, start=1):
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic") or f"议题 {idx}").strip()
            grade_raw = str(item.get("consensus_grade") or "").strip()
            grade_cn = grade_map.get(grade_raw, grade_raw)
            accord = str(item.get("accord") or "").strip()
            trigger = str(item.get("trigger") or "").strip()
            caveat = str(item.get("caveat") or "").strip()
            trade_off = item.get("trade_off") or {}
            gain = str(trade_off.get("gain") or "").strip() if isinstance(trade_off, dict) else ""
            sacrifice = str(trade_off.get("sacrifice") or "").strip() if isinstance(trade_off, dict) else ""

            card_lines = [f"## {idx}. {topic}【{grade_cn}】"]
            if trigger:
                card_lines.append(f"- **议题起因**：{trigger}")
            if accord:
                card_lines.append(f"- **达成决议**：{accord}")
            if caveat and caveat.lower() not in ("null", "none", "无"):
                card_lines.append(f"- **约束预警**：{caveat}")
            if gain or sacrifice:
                trade_parts = []
                if gain:
                    trade_parts.append(f"收益: {gain}")
                if sacrifice:
                    trade_parts.append(f"代价: {sacrifice}")
                card_lines.append(f"- **方案权衡**：{'；'.join(trade_parts)}")

            blocks.append("\n".join(card_lines))

        return "\n\n".join(blocks)

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
        """从 state 中提取最终议题列表（结构化产出并经过确定性门禁修复）。"""
        from .consensus_decision_gate import validate_and_repair_consensus_issues

        draft = (
            (state.get("lines") or {})
            .get("consensus_decision", {})
            .get("draft")
            or {}
        )
        raw_issues = list(draft.get("issues") or [])
        return validate_and_repair_consensus_issues(raw_issues)
