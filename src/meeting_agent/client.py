from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import TypeVar

from .models import ModelMixin
from .validation import OutputValidationError, validate_payload

T = TypeVar("T", bound=ModelMixin)


class DeepSeekClient:
    """DeepSeek 调用封装：请求 JSON 输出，并做严格结构校验。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key or self.api_key == "your_api_key_here":
            raise ValueError("请在 .env 中填写真实的 DEEPSEEK_API_KEY")
        self.base_url = (
            base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        ).rstrip("/")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.timeout = timeout
        self.max_retries = max_retries

    def _post(self, messages: list[dict[str, str]]) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
                return body["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API 返回 HTTP {exc.code}：{detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"无法连接 DeepSeek API：{exc.reason}") from exc

    @staticmethod
    def _parse_and_validate(content: str, response_model: type[T]) -> T:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OutputValidationError(f"不是合法 JSON：{exc}") from exc
        return validate_payload(response_model, data)

    async def structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        output_contract: str,
    ) -> T:
        contract = output_contract.strip()
        messages = [
            {
                "role": "system",
                "content": (
                    system_prompt
                    + "\n\n输出规则："
                    + "\n1. 只输出一个 JSON 对象，不要输出 Markdown 或解释。"
                    + "\n2. 字段名称、字段数量、字段类型必须与模板完全一致。"
                    + "\n3. 不得增加字段，不得省略字段，不得用字符串代替数组。"
                    + "\n4. 未知文本使用 null，无内容的数组使用 []。"
                    + f"\n唯一合法的输出模板：\n{contract}"
                ),
            },
            {"role": "user", "content": user_prompt},
        ]
        last_content = ""
        last_error = ""

        for attempt in range(self.max_retries + 1):
            last_content = await asyncio.to_thread(self._post, messages)
            try:
                return self._parse_and_validate(last_content, response_model)
            except OutputValidationError as exc:
                last_error = str(exc)
                if attempt < self.max_retries:
                    messages.extend(
                        [
                            {"role": "assistant", "content": last_content},
                            {
                                "role": "user",
                                "content": (
                                    "输出未通过严格校验。不要改变事实，"
                                    "请按唯一模板重新输出。"
                                    f"\n校验错误：{last_error}"
                                ),
                            },
                        ]
                    )

        from .agents.schema_repair_agent import SchemaRepairAgent

        repair_agent = SchemaRepairAgent(self)
        repaired = await repair_agent.run(last_content, contract, last_error)
        try:
            return self._parse_and_validate(repaired, response_model)
        except OutputValidationError as exc:
            raise RuntimeError(
                f"{response_model.__name__} 输出无法满足结构契约：{exc}"
            ) from exc
