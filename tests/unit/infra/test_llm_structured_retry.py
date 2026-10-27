"""structured 校验失败重试：缺字段时保留第一次内容。"""
from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass

from core.schema.validation import OutputValidationError
from infra.llm import LLMClient


@dataclass
class TwoFieldModel:
    a: str
    b: list[str]

    @classmethod
    def validate(cls, data: dict) -> TwoFieldModel:
        missing = [key for key in ("a", "b") if key not in data]
        if missing:
            raise OutputValidationError(
                f"TwoFieldModel 字段不一致：缺失={missing}，多余=[]"
            )
        return cls(a=str(data["a"]), b=list(data["b"]))


class FakeStructuredClient(LLMClient):
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.max_retries = 2
        self._monitor_lock = threading.Lock()
        self.retries_total = 0
        self.failures_total = 0
        self.calls: list[list[dict]] = []

    async def _in_thread(self, fn, /, *args, **kwargs):
        self.calls.append([dict(message) for message in args[0]])
        return self.responses.pop(0)

    async def _retry_delay(self, attempt: int) -> None:
        return None


def _messages_for_retry(client: FakeStructuredClient) -> tuple[str, str]:
    second = client.calls[1]
    assistant = next(
        message["content"] for message in second if message["role"] == "assistant"
    )
    user = next(
        message["content"]
        for message in second
        if message["role"] == "user" and "输出未通过严格校验" in message["content"]
    )
    return assistant, user


def test_structured_preserves_full_content_when_missing_fields() -> None:
    long_a = "A" * 3000
    first = json.dumps({"a": long_a}, ensure_ascii=False)
    second = json.dumps({"a": long_a, "b": []}, ensure_ascii=False)
    client = FakeStructuredClient([first, second])

    result = asyncio.run(
        client.structured(
            "system",
            "user",
            TwoFieldModel,
            "{}",
            preserve_content_on_validation_error=True,
        )
    )

    assert result.a == long_a
    assert result.b == []

    assistant, user = _messages_for_retry(client)
    assert long_a in assistant
    assert "超长内容截断" not in assistant
    assert "保留已有字段内容" in user
    assert "只补齐缺失字段" in user
    assert "篇幅精炼" not in user


def test_structured_default_retry_keeps_old_behavior() -> None:
    long_a = "A" * 3000
    first = json.dumps({"a": long_a}, ensure_ascii=False)
    second = json.dumps({"a": long_a, "b": []}, ensure_ascii=False)
    client = FakeStructuredClient([first, second])

    result = asyncio.run(
        client.structured("system", "user", TwoFieldModel, "{}")
    )

    assert result.a == long_a
    assert result.b == []

    assistant, user = _messages_for_retry(client)
    assert long_a not in assistant
    assert "超长内容截断" in assistant
    assert "篇幅精炼" in user
