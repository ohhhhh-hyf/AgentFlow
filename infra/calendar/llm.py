"""Calendar 与 infra.llm 的适配层。

Calendar 只依赖一个很小的 ``chat_json`` 接口；
真正的部署地址、鉴权、模型名与重试策略全部由 ``infra.llm.LLMClient`` 负责。
"""
from __future__ import annotations

import logging
from typing import Any

from infra.llm import LLMClient

logger = logging.getLogger("infra.calendar")


class CalendarLLM:
    """把部署版 LLMClient 适配成 calendar 需要的 ``chat_json`` 接口。"""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        logger.info("[calendar:llm:start] calling calendar llm (timeout=15s)...")
        res = await self.client.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=4096,
            timeout=15.0,
        )
        if isinstance(res, dict):
            return res
        raise ValueError(f"预期返回字典，实际返回: {type(res)}")


def extract_json_object(text: str) -> dict[str, Any]:
    """从模型输出提取 JSON 对象，兼容 Markdown 代码块与前置噪声。"""
    res = LLMClient.extract_json_payload(text)
    if isinstance(res, dict):
        return res
    raise ValueError(f"预期返回 JSON 字典，实际返回: {type(res)}")


__all__ = ["CalendarLLM", "extract_json_object"]
