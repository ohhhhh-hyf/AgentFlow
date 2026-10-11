from __future__ import annotations

from collections.abc import AsyncIterator

from infra.llm import LLMClient
from core.runner.prompt_utils import build_render_prompt

from ..prompts import RISK_RENDER_PROMPT, RISK_RENDER_TEMPLATE_PROMPT


INVALID_RISK_PLACEHOLDERS = {
    "null",
    "none",
    "无",
    "未提及",
    "未明确",
    "待排期",
    "待指定",
    "-",
    "待认领",
    "未分配",
    "待定",
    "待确认",
    "有风险",
    "存在风险",
    "风险隐患",
    "暂无风险",
    "存在隐患",
    "潜在风险",
    "风险",
    "无风险",
    "待评估",
    "风险较大",
    "有一定风险",
}


def validate_risk_items(items: list[dict], min_chars: int = 4) -> list[dict]:
    """确定性安全门禁：校验风险条目完整性，剔除干瘪占位风险。

    规则：
    1. 过滤非字典与空描述；
    2. 过滤描述长度低于 min_chars（默认 4 字）的碎片；
    3. 过滤明显无事实支撑的泛泛占位短语（如 '有风险', '存在风险', '暂无风险' 等）。
    """
    if not items:
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        risk_raw = str(item.get("risk") or "").strip()
        if not risk_raw or len(risk_raw) < min_chars:
            continue
        if risk_raw.lower() in INVALID_RISK_PLACEHOLDERS or risk_raw in INVALID_RISK_PLACEHOLDERS:
            continue
        out.append(dict(item))
    return out


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
    def extract_structure(state: dict) -> list[dict]:
        """从草稿中抽取并通过安全气囊校验的风险条目列表。"""
        draft = (state.get("lines") or {}).get("risks", {}).get("draft") or {}
        items = draft.get("risks") or []
        return validate_risk_items(items)

    @staticmethod
    def render_draft(state: dict) -> str:
        """无模板时按草稿字段排清单，与渲染 prompt 格式一致，不调 LLM。"""
        from core.graph.engine_text import render_risk_items

        items = RiskRender.extract_structure(state)
        return render_risk_items(items)

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user, label="risk/render"):
            yield chunk
