from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from .config import DEFAULT_BASE_URL, ENV_API_KEY, ENV_BASE_URL, _env

DEFAULT_VLM_MODEL = "deepseek-v4-flash-vision-exp"
ENV_VLM_API_KEY = "VLM_API_KEY"
ENV_VLM_BASE_URL = "VLM_BASE_URL"
ENV_VLM_MODEL = "VLM_MODEL"
ENV_VLM_TIMEOUT = "VLM_TIMEOUT"


class VLMClient:
    """OpenAI 兼容视觉模型客户端。

    默认复用 DeepSeek 的 API Key/Base URL，也可以用 VLM_* 环境变量单独覆盖。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        resolved_key = api_key or _env(ENV_VLM_API_KEY) or _env(ENV_API_KEY)
        if not resolved_key:
            raise ValueError(
                f"未找到 VLM API Key，请配置 {ENV_VLM_API_KEY} 或 {ENV_API_KEY}"
            )

        resolved_base = (
            base_url
            or _env(ENV_VLM_BASE_URL)
            or _env(ENV_BASE_URL)
            or DEFAULT_BASE_URL
        ).rstrip("/")
        resolved_model = model or _env(ENV_VLM_MODEL) or DEFAULT_VLM_MODEL
        resolved_timeout = timeout
        if resolved_timeout is None:
            raw_timeout = _env(ENV_VLM_TIMEOUT)
            resolved_timeout = float(raw_timeout) if raw_timeout else 120.0

        self.api_key = resolved_key
        self.base_url = resolved_base
        self.model = resolved_model
        self.timeout = resolved_timeout
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on install
            raise ModuleNotFoundError(
                "使用 VLMClient 需要安装 openai 包：pip install openai"
            ) from exc

        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    @staticmethod
    def image_to_data_url(image_path: str | Path) -> str:
        path = Path(image_path)
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
        return f"data:{mime};base64,{encoded}"

    def describe_image(
        self,
        image_path: str | Path,
        prompt: str = "请识别图片中的文本内容，并尽量保留阅读顺序。",
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> str:
        """输入本地图片，返回视觉模型输出文本。"""
        data_url = self.image_to_data_url(image_path)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if extra_body:
            kwargs["extra_body"] = extra_body

        response = self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "\n".join(part for part in parts if part)
        return str(content or "")


__all__ = ["VLMClient"]
