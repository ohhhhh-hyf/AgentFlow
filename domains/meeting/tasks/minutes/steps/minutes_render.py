from __future__ import annotations

import re
from collections.abc import AsyncIterator

from core.execution.hard_execution import parse_lang_mode
from core.runner.prompt_utils import build_render_prompt
from infra.llm import LLMClient

from ..prompt_map import is_agenda_view, render_template_prompt
from ..prompts import localize_agenda_headings_for_en


def compact_untemplated_minutes(text: str) -> str:
    """普通纪要 / 溯源纪要：段与段只保留一个换行，去掉空行。

    文末「历史记忆引用」附录单独保留；正文和附录之间的 ``---`` 全部去掉，
    避免压缩时重复插入分隔线。
    """
    body = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    marker = "## 历史记忆引用"
    en_marker = "## Historical Memory References"
    appendix = ""
    for m in (marker, en_marker):
        if m in body:
            body, appendix = body.split(m, 1)
            appendix = m + appendix
            break
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{2,}", "\n", body).strip()
    body = re.sub(r"(?:\n+-{3,})+\s*$", "", body).strip()
    if appendix:
        appendix = re.sub(r"[ \t]+\n", "\n", appendix).strip()
        appendix = re.sub(r"^(?:-{3,}\s*)+", "", appendix).strip()
        return f"{body}\n{appendix}\n"
    return body


def _field_list(draft: dict, field: str) -> list:
    """取草稿字段并归一为列表；兼容单字符串，避免逐字符拆分。"""
    value = draft.get(field)
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _format_list_lines(items: list) -> list[str]:
    """格式化列表项，支持独占加粗组名（如 **与我相关**：、**姓名**：）。"""
    lines: list[str] = []
    for it in items:
        s = str(it or "").strip()
        if not s:
            continue
        # 独占组名行（如 **与我相关**：、**重点协同**：、**姓名**：）
        if s.startswith("**") and s.endswith(("：", ":")):
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(s)
        else:
            if not s.startswith(("- ", "* ", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                lines.append(f"- {s}")
            else:
                lines.append(s)
    return lines


def _format_history_lines(items: list) -> list[str]:
    """历史对比列表：保留已有列表符，其余统一补 `- `。"""
    lines: list[str] = []
    for item in items:
        s = str(item or "").strip()
        if not s:
            continue
        lines.append(s if s.startswith(("- ", "* ")) else f"- {s}")
    return lines


def render_fallback_minutes(
    draft: dict,
    *,
    objective: bool = True,
    is_personal: bool = False,
    user_name: str = "",
    is_en: bool = False,
) -> str:
    """7 字段 → 通用兜底纪要的确定性 Markdown 映射（零 LLM 调用）。

    只做字段到栏目的格式化，不做语义推断、不补造事实：
    - headline → 一级标题
    - executive_summary[0] → 全文摘要；[1:] → 要点梳理
    - key_decisions → 关键决策
    - personally_relevant_points → 全员执行要点 / 职责相关事项
    - risks_and_blockers → 风险与阻塞
    - unresolved_questions → 未决问题
    - history_comparison → 与历史对比（有内容才输出）
    """
    empty_msg = (
        "Please refer directly to the meeting transcript."
        if is_en
        else "请直接参考会议原文。"
    )
    if not draft:
        return empty_msg

    headline = str(draft.get("headline") or "").strip()
    if headline:
        title = headline
    elif is_personal and user_name:
        title = f"{user_name}'s Meeting Minutes" if is_en else f"{user_name}视角会议纪要"
    elif objective:
        title = "Meeting Minutes" if is_en else "客观会议纪要"
    else:
        title = "Meeting Minutes" if is_en else "会议纪要"

    blocks: list[str] = []

    summary = [
        str(p).strip()
        for p in _field_list(draft, "executive_summary")
        if str(p).strip()
    ]
    if summary:
        summary_heading = "## Executive Summary" if is_en else "## 全文摘要"
        blocks.append(f"{summary_heading}\n\n{summary[0]}")
        if len(summary) > 1:
            points_heading = "## Key Discussion Points" if is_en else "## 要点梳理"
            blocks.append(f"{points_heading}\n\n" + "\n\n".join(summary[1:]))

    def add_list(field: str, heading_zh: str, heading_en: str) -> None:
        formatted = _format_list_lines(_field_list(draft, field))
        if formatted:
            heading = heading_en if is_en else heading_zh
            blocks.append(f"{heading}\n\n" + "\n".join(formatted))

    add_list("key_decisions", "## 关键决策", "## Key Decisions")
    add_list(
        "personally_relevant_points",
        "## 职责相关事项" if is_personal else "## 全员执行要点",
        "## Individual Action Items" if is_personal else "## Action Items",
    )
    add_list("risks_and_blockers", "## 风险与阻塞", "## Risks & Blockers")
    add_list("unresolved_questions", "## 未决问题", "## Open Questions")

    history = _format_history_lines(_field_list(draft, "history_comparison"))
    if history:
        history_heading = "## Historical Comparison" if is_en else "## 与历史对比"
        blocks.append(f"{history_heading}\n\n" + "\n".join(history))

    if not blocks:
        return f"# {title}\n\n{empty_msg}"

    return f"# {title}\n\n" + "\n\n".join(blocks)


class MinutesGenerationRender:
    """把已批准的纪要草稿渲染为最终正文（支持模板与流式）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _format_list_items(items: list[str]) -> list[str]:
        """格式化列表项，支持个人视角的独占加粗组名（如 **与我相关**：、**姓名**：）。"""
        return _format_list_lines(items)

    @staticmethod
    def render_draft(state: dict) -> str:
        """把已批准的纪要草稿纯 Python 确定性组装为规范 Markdown 正文（零 LLM 调用）。

        先提取视角/语种，再委托 ``render_fallback_minutes`` 做 7 字段 → 栏目映射；
        兜底布局固定为：全文摘要 / 要点梳理 / 关键决策 / 执行要点 / 风险 / 未决 / 历史对比。
        """
        minutes_state = (state.get("lines") or {}).get("minutes") or {}
        draft = minutes_state.get("draft") or {}
        lang = str(state.get("lang") or "zh").strip().lower()

        objective = bool(state.get("objective_perspective"))
        user = state.get("user") or {}
        name = str(user.get("name") or "").strip()
        is_personal = (
            (not objective)
            and bool(name)
            and str(user.get("perspective") or "").strip().lower() != "objective"
        )

        return render_fallback_minutes(
            draft,
            objective=objective,
            is_personal=is_personal,
            user_name=name,
            is_en=lang == "en",
        )

    @staticmethod
    def _prompt_and_user(
        context: str,
        template: str,
        *,
        view: str,
        lang: str | None = None,
    ) -> tuple[str, str]:
        """组装渲染 prompt 与用户消息（普通与流式共用）。

        模板分支逻辑由 core.runner.prompt_utils.build_render_prompt 提供：
        有模板时模板原样拼进用户消息（LLM 只替换占位符，其余逐字符保留）。
        无模板生产路径由 ``render_draft`` 确定性兜底，不再保留无模板 LLM prompt。
        """
        view = (view or "").strip().lower()
        if not view:
            raise ValueError("minutes render view is required")
        template_prompt = render_template_prompt(view)
        is_agenda = is_agenda_view(view)

        lang_val = lang or parse_lang_mode(context)
        if (lang_val or "").strip().lower() == "en":
            role_prefix = "英文（English）"

            def _wrap_en(raw_p: str) -> str:
                body = raw_p
                first_period = body.find("。\n")
                if first_period > 0:
                    body = body[first_period + 2 :].strip()
                elif body.startswith("你是"):
                    first_line_end = body.find("\n")
                    if first_line_end > 0:
                        body = body[first_line_end + 1 :].strip()
                return (
                    f"【核心人设与交付目标】\n"
                    f"你是专职的【{role_prefix}】会议纪要渲染器，本次任务严格依据已审核的{role_prefix}草稿填充模板，直接排版最终 Markdown 正文。\n\n"
                    f"{body}\n\n"
                    f"## 语言红线\n"
                    f"1. 严格保持草稿的{role_prefix}原貌，严禁翻译为中文，严禁夹杂中文字符；\n"
                    f"2. 标点符号统一使用标准半角英文标点（逗号后带空格）。"
                )

            template_prompt = _wrap_en(template_prompt)
            if is_agenda:
                template_prompt = localize_agenda_headings_for_en(template_prompt)

        return build_render_prompt(
            context,
            template,
            "",
            template_prompt,
        )

    async def run(
        self,
        approved_context: str,
        template: str = "",
        *,
        view: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        lang: str | None = None,
    ) -> str:
        """整段渲染纪要正文（纯文本）。有模板时用低温度稳住结构。

        ``max_tokens`` 由编排层按目标字数给出：本地端点没有隐含输出上限（托管 API 自带
        ~8k），退化时会一路写满上下文（实测 49k token / 9 分钟），必须由调用方设硬上限。
        """
        prompt, user = self._prompt_and_user(
            approved_context,
            template,
            view=view,
            lang=lang,
        )
        has_template = bool((template or "").strip())
        temp = temperature if temperature is not None else (0.0 if has_template else None)
        text = await self.client.text(
            prompt, user, temperature=temp, max_tokens=max_tokens, label="minutes/render"
        )
        return text

    async def stream(
        self,
        approved_context: str,
        template: str = "",
        *,
        view: str,
        lang: str | None = None,
    ) -> AsyncIterator[str]:
        """流式渲染纪要正文：LLM token 逐块产出（SSE）。"""
        prompt, user = self._prompt_and_user(
            approved_context,
            template,
            view=view,
            lang=lang,
        )
        async for chunk in self.client.stream_text(prompt, user, label="minutes/render"):
            yield chunk

