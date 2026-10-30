"""Calendar 与 infra.llm 的适配层。

Calendar 只依赖一个很小的 ``chat_json`` 接口；
真正的部署地址、鉴权、模型名与重试策略全部由 ``infra.llm.LLMClient`` 负责。
"""
from __future__ import annotations

import json
import re
from typing import Any

from infra.llm import LLMClient

from .config import CALENDAR_LLM_LABEL


def extract_json_object(text: str) -> dict[str, Any]:
    """从模型输出提取 JSON 对象，兼容 Markdown 代码块与前置噪声。"""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(raw[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("模型输出必须是 JSON 对象")
    return value


class CalendarLLM:
    """把部署版 LLMClient 适配成 calendar 需要的 ``chat_json`` 接口。"""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        try:
            content = await self.client.text(
                system_prompt,
                user_prompt,
                json_mode=True,
                temperature=0.0,
                max_tokens=4096,
                label=CALENDAR_LLM_LABEL,
            )
        except RuntimeError as exc:
            # 部分自部署 OpenAI 兼容网关不接受 response_format；
            # 仅对明确的 HTTP 400 做一次无 json_mode 降级，网络错误继续抛出。
            if "HTTP 400" not in str(exc):
                raise
            content = await self.client.text(
                system_prompt,
                user_prompt,
                json_mode=False,
                temperature=0.0,
                max_tokens=4096,
                label=CALENDAR_LLM_LABEL,
            )
        return extract_json_object(content)


__all__ = ["CalendarLLM", "extract_json_object"]
