from __future__ import annotations

import re
from collections.abc import AsyncIterator

from core.execution.hard_execution import parse_lang_mode
from core.runner.prompt_utils import build_render_prompt

from infra.llm import LLMClient
from ..prompt_map import minutes_prompt_set, resolve_prompt_view


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


class MinutesGenerationRender:
    """把已批准的纪要草稿渲染为最终正文（支持模板与流式）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _format_list_items(items: list[str]) -> list[str]:
        """格式化列表项，支持个人视角的独占加粗组名（如 **与我相关**：、**姓名**：）。"""
        lines: list[str] = []
        for it in items:
            s = str(it or "").strip()
            if not s:
                continue
            # 独占组名行（如 **与我相关**：、**重点协同**：、**姓名**：）
            if s.startswith("**") and (s.endswith("：") or s.endswith(":")):
                if lines and lines[-1] != "":
                    lines.append("")
                lines.append(s)
            else:
                if not s.startswith(("- ", "* ", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                    lines.append(f"- {s}")
                else:
                    lines.append(s)
        return lines

    @staticmethod
    def render_draft(state: dict) -> str:
        """把已批准的纪要草稿纯 Python 确定性组装为规范 Markdown 正文（零 LLM 调用）。"""
        minutes_state = (state.get("lines") or {}).get("minutes") or {}
        draft = minutes_state.get("draft") or {}
        lang = str(state.get("lang") or "zh").strip().lower()
        is_en = lang == "en"

        if not draft:
            return "Please refer directly to the meeting transcript." if is_en else "请直接参考会议原文。"

        objective = bool(state.get("objective_perspective"))
        user = state.get("user") or {}
        name = str(user.get("name") or "").strip()
        is_personal = (
            (not objective)
            and bool(name)
            and str(user.get("perspective") or "").strip().lower() != "objective"
        )

        headline = str(draft.get("headline") or "").strip()
        if headline:
            title = headline
        elif is_personal:
            title = f"{name}'s Meeting Minutes" if is_en else f"{name}视角会议纪要"
        elif objective:
            title = "Meeting Minutes" if is_en else "客观会议纪要"
        else:
            title = "Meeting Minutes" if is_en else "会议纪要"

        blocks: list[str] = []

        # 1. executive_summary -> 全文摘要 / Executive Summary
        exec_sum = list(draft.get("executive_summary") or [])
        if exec_sum:
            summary_paras = [str(p).strip() for p in exec_sum if str(p).strip()]
            if summary_paras:
                sec = "## Executive Summary" if is_en else "## 全文摘要"
                blocks.append(f"{sec}\n\n" + "\n\n".join(summary_paras))

        # 2. key_decisions -> 关键决策 / Key Decisions
        decisions = list(draft.get("key_decisions") or [])
        if decisions:
            formatted_decisions = MinutesGenerationRender._format_list_items(decisions)
            if formatted_decisions:
                sec = "## Key Decisions" if is_en else "## 关键决策"
                blocks.append(f"{sec}\n\n" + "\n".join(formatted_decisions))

        # 3. personally_relevant_points -> 执行要点 / Action Items
        points = list(draft.get("personally_relevant_points") or [])
        if points:
            formatted_points = MinutesGenerationRender._format_list_items(points)
            if formatted_points:
                if is_en:
                    sec_title = "## Individual Action Items" if is_personal else "## Action Items"
                else:
                    sec_title = "## 职责相关事项" if is_personal else "## 全员执行要点"
                blocks.append(f"{sec_title}\n\n" + "\n".join(formatted_points))

        # 4. risks_and_blockers -> 风险与阻塞 / Risks & Blockers
        risks = list(draft.get("risks_and_blockers") or [])
        if risks:
            formatted_risks = MinutesGenerationRender._format_list_items(risks)
            if formatted_risks:
                sec = "## Risks & Blockers" if is_en else "## 风险与阻塞"
                blocks.append(f"{sec}\n\n" + "\n".join(formatted_risks))

        # 5. unresolved_questions -> 未决问题 / Open Questions
        questions = list(draft.get("unresolved_questions") or [])
        if questions:
            formatted_questions = MinutesGenerationRender._format_list_items(questions)
            if formatted_questions:
                sec = "## Open Questions" if is_en else "## 未决问题"
                blocks.append(f"{sec}\n\n" + "\n".join(formatted_questions))

        # 6. history_comparison -> 与历史对比 / Historical Comparison
        comparison = list(draft.get("history_comparison") or [])
        if comparison:
            formatted_comp = [
                f"- {str(c).strip()}" if not str(c).strip().startswith(("- ", "* ")) else str(c).strip()
                for c in comparison
                if str(c).strip()
            ]
            if formatted_comp:
                sec = "## Historical Comparison" if is_en else "## 与历史对比"
                blocks.append(f"{sec}\n\n" + "\n".join(formatted_comp))

        if not blocks:
            empty_msg = "Please refer directly to the meeting transcript." if is_en else "请直接参考会议原文。"
            return f"# {title}\n\n{empty_msg}"

        return f"# {title}\n\n" + "\n\n".join(blocks)

    @staticmethod
    def _prompt_and_user(context: str, template: str, *, lang: str | None = None) -> tuple[str, str]:
        """组装渲染 prompt 与用户消息（普通与流式共用）。

        模板分支逻辑由 tools.core.prompt_utils.build_render_prompt 提供：
        有模板时模板原样拼进用户消息（LLM 只替换占位符，其余逐字符保留）。
        无模板时，根据视角模式动态分发客观或个人渲染提示词。
        """
        view = resolve_prompt_view(context)
        prompt_set = minutes_prompt_set(view)
        untemplated_prompt = prompt_set.render
        template_prompt = prompt_set.render_template

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

            untemplated_prompt = _wrap_en(untemplated_prompt)
            template_prompt = _wrap_en(template_prompt)

        return build_render_prompt(
            context,
            template,
            untemplated_prompt,
            template_prompt,
        )

    async def run(
        self,
        approved_context: str,
        template: str = "",
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        lang: str | None = None,
    ) -> str:
        """整段渲染纪要正文（纯文本）。有模板时用低温度稳住结构。

        ``max_tokens`` 由编排层按目标字数给出：本地端点没有隐含输出上限（托管 API 自带
        ~8k），退化时会一路写满上下文（实测 49k token / 9 分钟），必须由调用方设硬上限。
        """
        prompt, user = self._prompt_and_user(approved_context, template, lang=lang)
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
        lang: str | None = None,
    ) -> AsyncIterator[str]:
        """流式渲染纪要正文：LLM token 逐块产出（SSE）。"""
        prompt, user = self._prompt_and_user(approved_context, template, lang=lang)
        async for chunk in self.client.stream_text(prompt, user, label="minutes/render"):
            yield chunk

