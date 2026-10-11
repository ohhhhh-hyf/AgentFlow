from __future__ import annotations

from collections.abc import AsyncIterator
import re

from infra.llm import LLMClient
from core.runner.prompt_utils import build_render_prompt
from infra.exporters.html.agenda_minutes import format_agenda_minutes_markdown

from ..prompts import AGENDA_MINUTES_RENDER_PROMPT, AGENDA_MINUTES_RENDER_TEMPLATE_PROMPT


def prune_empty_action_tables(markdown: str) -> str:
    """第四栏空表物理裁剪：若议题下出现仅有表头或内容为空/暂无的后续行动表，彻底剔除该栏目。"""
    if not markdown or "#### 4. 后续行动" not in markdown:
        return markdown or ""

    pattern = re.compile(
        r"(####\s*4\.\s*后续行动\s*\n)(.*?)(?=\n#{1,4}\s+|\Z)",
        re.DOTALL,
    )

    def _replace(match: re.Match) -> str:
        content = match.group(2).strip()
        if not content:
            return ""
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        has_real_action = False
        for ln in lines:
            if ln.startswith("|") and ln.endswith("|"):
                if "责任人" in ln or "时限" in ln or "交付" in ln:
                    continue
                if re.match(r"^\|?[\s\-:]+\|[\s\-:|]+$", ln):
                    continue
                cells = [c.strip() for c in ln.split("|")[1:-1]]
                joined = "".join(cells)
                if joined and not all(c in {"-", "待定", "暂无", "无", "近期", "尽快", "null", "none"} for c in cells):
                    has_real_action = True
                    break
            elif content not in ("暂无", "无", "未提及", "未讨论", "待定", "-"):
                has_real_action = True
                break

        if not has_real_action:
            return ""
        return match.group(0)

    cleaned = pattern.sub(_replace, markdown).rstrip()
    return cleaned + "\n" if cleaned else ""


def validate_and_align_agenda_slots(
    agenda_items: list[dict],
    expected_agendas: list[dict] | list[str] | None = None,
) -> list[dict]:
    """议程数量与槽位对齐门禁：
    1. 去重（重槽清理）：若出现相同 agenda_title，保留信息量更完整的一项；
    2. 补全（漏槽修复）：若已知会前既定议程，比对补齐未讨论或被遗漏的议程槽位并标记 skipped。
    """
    if not agenda_items:
        return []

    seen_titles: dict[str, dict] = {}
    for item in agenda_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("agenda_title") or "").strip()
        if not title:
            continue
        if title not in seen_titles:
            seen_titles[title] = dict(item)
        else:
            existing = seen_titles[title]
            cur_pts = len(item.get("core_content") or [])
            old_pts = len(existing.get("core_content") or [])
            if cur_pts > old_pts:
                seen_titles[title] = dict(item)

    aligned_items = list(seen_titles.values())

    if expected_agendas:
        for idx, exp in enumerate(expected_agendas, 1):
            exp_title = (
                str(exp.get("title") or exp.get("agenda_title") or "").strip()
                if isinstance(exp, dict)
                else str(exp).strip()
            )
            if not exp_title:
                continue
            if not any(exp_title == str(it.get("agenda_title") or "").strip() for it in aligned_items):
                seq_str = f"{idx:02d}"
                aligned_items.append({
                    "agenda_seq": seq_str,
                    "agenda_title": exp_title,
                    "presenter": exp.get("speaker", "") if isinstance(exp, dict) else "",
                    "agenda_category": "share",
                    "status_tag": "本次未讨论",
                    "is_skipped": True,
                    "background_and_goals": "会前既定议题，本次会议未进行讨论。",
                    "core_content": [],
                    "core_insights": "",
                    "action_items": [],
                })

    return aligned_items


class AgendaMinutesRender:
    """把已批准的议程驱动纪要草稿渲染为最终正文（支持普通排版与模板渲染）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        return build_render_prompt(
            context,
            template,
            AGENDA_MINUTES_RENDER_PROMPT,
            AGENDA_MINUTES_RENDER_TEMPLATE_PROMPT,
        )

    async def run(self, approved_context: str, template: str = "") -> str:
        prompt, user = self._prompt_and_user(approved_context, template)
        temp = 0.0 if (template or "").strip() else None
        text = await self.client.text(
            prompt, user, temperature=temp, label="agenda_minutes/render"
        )
        return prune_empty_action_tables(text)

    @staticmethod
    def render_draft(state: dict) -> str:
        """无模板时按草稿字段直接排版高规格议程全景 Markdown，0 额外 LLM 开销。"""
        draft = (
            (state.get("lines") or {})
            .get("agenda_minutes", {})
            .get("draft")
            or {}
        )
        md = format_agenda_minutes_markdown(draft)
        return prune_empty_action_tables(md)

    @staticmethod
    def extract_structure(state: dict) -> list[dict]:
        """提取结构化议题列表，供 Report 与下游消费。"""
        draft = (
            (state.get("lines") or {})
            .get("agenda_minutes", {})
            .get("draft")
            or {}
        )
        items = list(draft.get("agenda_items") or [])
        expected = None
        mu = state.get("meeting_understanding") or {}
        if isinstance(mu, dict) and mu.get("agenda"):
            expected = mu.get("agenda")
        elif state.get("agenda"):
            expected = state.get("agenda")
        return validate_and_align_agenda_slots(items, expected)

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(
            prompt, user, label="agenda_minutes/render"
        ):
            yield chunk
