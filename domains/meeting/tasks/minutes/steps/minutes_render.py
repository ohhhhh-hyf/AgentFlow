from __future__ import annotations

import re
from collections.abc import AsyncIterator

from core.runner.prompt_utils import build_render_prompt

from infra.llm import LLMClient
from ..prompts import MINUTES_RENDER_PROMPT, MINUTES_RENDER_TEMPLATE_PROMPT


def compact_untemplated_minutes(text: str) -> str:
    """普通纪要 / 溯源纪要：段与段只保留一个换行，去掉空行。

    文末「历史记忆引用」附录单独保留；正文和附录之间的 ``---`` 全部去掉，
    避免压缩时重复插入分隔线。
    """
    body = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    marker = "## 历史记忆引用"
    appendix = ""
    if marker in body:
        body, appendix = body.split(marker, 1)
        appendix = marker + appendix
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
        if not draft:
            return "请直接参考会议原文。"

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
            title = f"{name}视角会议纪要"
        elif objective:
            title = "客观会议纪要"
        else:
            title = "会议纪要"

        blocks: list[str] = []

        # 1. executive_summary -> 全文摘要
        exec_sum = list(draft.get("executive_summary") or [])
        if exec_sum:
            summary_paras = [str(p).strip() for p in exec_sum if str(p).strip()]
            if summary_paras:
                blocks.append("## 全文摘要\n\n" + "\n\n".join(summary_paras))

        # 2. key_decisions -> 关键决策
        decisions = list(draft.get("key_decisions") or [])
        if decisions:
            formatted_decisions = MinutesGenerationRender._format_list_items(decisions)
            if formatted_decisions:
                blocks.append("## 关键决策\n\n" + "\n".join(formatted_decisions))

        # 3. personally_relevant_points -> 执行要点
        points = list(draft.get("personally_relevant_points") or [])
        if points:
            formatted_points = MinutesGenerationRender._format_list_items(points)
            if formatted_points:
                sec_title = "## 职责相关事项" if is_personal else "## 全员执行要点"
                blocks.append(f"{sec_title}\n\n" + "\n".join(formatted_points))

        # 4. risks_and_blockers -> 风险与阻塞
        risks = list(draft.get("risks_and_blockers") or [])
        if risks:
            formatted_risks = MinutesGenerationRender._format_list_items(risks)
            if formatted_risks:
                blocks.append("## 风险与阻塞\n\n" + "\n".join(formatted_risks))

        # 5. unresolved_questions -> 未决问题
        questions = list(draft.get("unresolved_questions") or [])
        if questions:
            formatted_questions = MinutesGenerationRender._format_list_items(questions)
            if formatted_questions:
                blocks.append("## 未决问题\n\n" + "\n".join(formatted_questions))

        # 6. history_comparison -> 与历史对比
        comparison = list(draft.get("history_comparison") or [])
        has_memory = bool(minutes_state.get("memory_context"))
        if comparison and not has_memory:
            formatted_comp = [
                f"- {str(c).strip()}" if not str(c).strip().startswith(("- ", "* ")) else str(c).strip()
                for c in comparison
                if str(c).strip()
            ]
            if formatted_comp:
                blocks.append("## 与历史对比\n\n" + "\n".join(formatted_comp))

        if not blocks:
            return f"# {title}\n\n请直接参考会议原文。"

        return f"# {title}\n\n" + "\n\n".join(blocks)

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        """组装渲染 prompt 与用户消息（普通与流式共用）。

        模板分支逻辑由 tools.core.prompt_utils.build_render_prompt 提供：
        有模板时模板原样拼进用户消息（LLM 只替换占位符，其余逐字符保留）。
        """
        return build_render_prompt(
            context,
            template,
            MINUTES_RENDER_PROMPT,
            MINUTES_RENDER_TEMPLATE_PROMPT,
        )

    async def run(
        self,
        approved_context: str,
        template: str = "",
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """整段渲染纪要正文（纯文本）。有模板时用低温度稳住结构。

        ``max_tokens`` 由编排层按目标字数给出：本地端点没有隐含输出上限（托管 API 自带
        ~8k），退化时会一路写满上下文（实测 49k token / 9 分钟），必须由调用方设硬上限。
        """
        prompt, user = self._prompt_and_user(approved_context, template)
        has_template = bool((template or "").strip())
        temp = temperature if temperature is not None else (0.0 if has_template else None)
        # 这里过去用 try/except TypeError 兜「老客户端没有 max_tokens」：但 LLMClient.text
        # 本来就接受 temperature/max_tokens/label，那个 except 分支撑不到签名不匹配，
        # 只会在 text() 内部真抛 TypeError 时静默**再打一次 LLM**（重复计费）。已删除。
        text = await self.client.text(
            prompt, user, temperature=temp, max_tokens=max_tokens, label="minutes/render"
        )
        # 无模板时的收尾压缩**不在这里做**（2026-09-22 核对后删除）：编排层只在有模板时调
        # 本方法（见 tools/runtime/render.py 的 use_block / 返工 / 压缩扩写各分支），无模板
        # 正文的压缩由域钩子 compact_plain 在 tools/runtime/render 与 tools/exports/outputs
        # 两处统一执行（见 domain/meeting/hooks.py）。原地保留会让人以为这里也管压缩。
        return text

    async def stream(self, approved_context: str, template: str = "") -> AsyncIterator[str]:
        """流式渲染纪要正文：LLM token 逐块产出（SSE）。"""
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user, label="minutes/render"):
            yield chunk

