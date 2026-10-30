"""Visual Minutes 与 infra.llm 的适配层。"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from infra.llm import LLMClient
from infra.llm.config import load_env

from .config import (
    DEFAULT_VISUAL_TEMPERATURE,
    ENV_FILE,
    VISUAL_LLM_LABEL,
    VISUAL_LLM_TEMPERATURE_ENV,
)


def extract_json_object(text: str) -> dict[str, Any]:
    """从模型输出提取 JSON 对象，兼容代码块与前后噪声。"""
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


def _resolve_temperature() -> float:
    """视觉任务默认 0.2；.env 中的 VISUAL_LLM_TEMPERATURE 可覆盖。"""
    raw = os.getenv(VISUAL_LLM_TEMPERATURE_ENV, "").strip()
    if not raw:
        return DEFAULT_VISUAL_TEMPERATURE
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(
            f"{VISUAL_LLM_TEMPERATURE_ENV} 必须是数字，当前为：{raw!r}"
        ) from exc


class VisualLLM:
    """把部署版 LLMClient 适配成 Visual Minutes 的 JSON 调用。

    连接方式、API Key、模型、温度、max_tokens 等全部由根目录 .env
    与 ``infra.llm.LLMClient`` 决定；本适配层不绑定任何供应商。
    """

    def __init__(self, client: LLMClient | None = None) -> None:
        if client is None:
            load_env(ENV_FILE)
        self.client = client or LLMClient()
        self.temperature = _resolve_temperature()

    async def json_call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        label: str = VISUAL_LLM_LABEL,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        temp = self.temperature if temperature is None else float(temperature)
        try:
            content = await self.client.text(
                system_prompt,
                user_prompt,
                json_mode=True,
                temperature=temp,
                max_tokens=max_tokens,
                label=label,
            )
        except RuntimeError as exc:
            # 部分自部署网关不接受 response_format；仅对明确 HTTP 400 降级一次。
            if "HTTP 400" not in str(exc):
                raise
            content = await self.client.text(
                system_prompt,
                user_prompt,
                json_mode=False,
                temperature=temp,
                max_tokens=max_tokens,
                label=label,
            )
        return extract_json_object(content)


__all__ = ["VisualLLM", "extract_json_object"]
