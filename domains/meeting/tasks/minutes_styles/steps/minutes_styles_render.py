from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from infra.llm import LLMClient
from core.runner.prompt_utils import build_render_prompt

from ..prompts import MULTI_STYLES_RENDER_PROMPT, MULTI_STYLES_RENDER_TEMPLATE_PROMPT
from core.graph.engine_text import scrape_draft

def _draft_from_context(approved_context: str) -> dict[str, Any]:
    """从渲染上下文里抽出已批准草稿（实现见 domain_engine_text.scrape_draft）。"""
    return scrape_draft(approved_context, ('已批准多样式纪要草稿：',))


def _empty_render_text(draft: dict) -> str:
    title = str(draft.get("title") or "").strip() or "多样式纪要"
    return f"{title}\n\n暂无结构化段落"


def clamp_brief_minutes(text: str, max_chars: int = 600) -> str:
    """brief 模式字数熔断门禁：限制正文在 max_chars 以内，保持高管速览极度精炼。"""
    if not text or len(text) <= max_chars:
        return text or ""

    cutoff = min(len(text), max_chars - 35)
    last_nl = text.rfind("\n", 0, cutoff)
    if last_nl > 250:
        truncated = text[:last_nl].rstrip()
    else:
        last_period = text.rfind("。", 0, cutoff)
        if last_period > 250:
            truncated = text[:last_period + 1].rstrip()
        else:
            truncated = text[:cutoff].rstrip()

    return truncated + "\n\n> 💡 *(速览模式字数熔断：正文已自动脱水收敛至骨架)*"


class MultiStylesRender:
    """Render the approved 多样式纪要 result."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def render_draft(state: dict) -> str:
        """把已批准的多样式纪要草稿纯 Python 确定性组装为规范 Markdown 正文（零 LLM 调用）。"""
        draft = (
            (state.get("lines") or {})
            .get("minutes_styles", {})
            .get("draft")
            or {}
        )
        if not draft:
            return "暂无多样式纪要"
        title = str(draft.get("title") or "").strip() or "多样式纪要"
        summary = str(draft.get("summary") or "").strip()
        sections = list(draft.get("sections") or [])

        blocks: list[str] = [f"# {title}"]
        if summary:
            blocks.append(f"> **速览摘要**：{summary}")

        for sec in sections:
            if not isinstance(sec, dict):
                continue
            sec_title = str(sec.get("title") or "").strip() or "要点"
            sec_content = str(sec.get("content") or "").strip()
            if sec_content:
                blocks.append(f"## {sec_title}\n\n{sec_content}")

        return "\n\n".join(blocks) if len(blocks) > 1 else f"# {title}\n\n暂无结构化段落"

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        return build_render_prompt(
            context,
            template,
            MULTI_STYLES_RENDER_PROMPT,
            MULTI_STYLES_RENDER_TEMPLATE_PROMPT,
        )

    @staticmethod
    def _should_skip_llm(approved_context: str) -> str | None:
        """只有草稿完全没有段落时才短路，避免对着空稿补一篇。"""
        draft = _draft_from_context(approved_context)
        sections = draft.get("sections")
        if not isinstance(sections, list) or not sections:
            return _empty_render_text(draft)
        return None

    async def run(self, approved_context: str, template: str = "") -> str:
        blocked = self._should_skip_llm(approved_context)
        if blocked is not None:
            return blocked
        prompt, user = self._prompt_and_user(approved_context, template)
        rendered = await self.client.text(prompt, user, label="minutes_styles/render")
        draft = _draft_from_context(approved_context)
        mode = str(draft.get("mode") or "").strip().lower()
        if mode == "brief":
            rendered = clamp_brief_minutes(rendered, max_chars=600)
        return rendered

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        blocked = self._should_skip_llm(approved_context)
        if blocked is not None:
            yield blocked
            return
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user, label="minutes_styles/render"):
            yield chunk

