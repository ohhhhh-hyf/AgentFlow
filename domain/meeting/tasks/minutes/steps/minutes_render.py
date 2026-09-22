from __future__ import annotations

import re
from collections.abc import AsyncIterator

from tools.core.prompt_utils import build_render_prompt

from tools.llm import LLMClient
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
    ) -> str:
        """整段渲染纪要正文（纯文本）。有模板时用低温度稳住结构。

        ``max_tokens`` 由编排层按目标字数给出：本地端点没有隐含输出上限（托管 API 自带
        ~8k），退化时会一路写满上下文（实测 49k token / 9 分钟），必须由调用方设硬上限。
        """
        prompt, user = self._prompt_and_user(approved_context, template)
        has_template = bool((template or "").strip())
        temp = 0.0 if has_template else None
        try:
            text = await self.client.text(
                prompt, user, temperature=temp, max_tokens=max_tokens, label="minutes/render"
            )
        except TypeError:
            text = await self.client.text(prompt, user, label="minutes/render")
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

