from __future__ import annotations

import asyncio
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Iterable
from typing import TypeVar

try:
    import websockets
except ModuleNotFoundError:  # pragma: no cover - depends on selected backend
    websockets = None

from tools.validation import OutputValidationError, validate_payload

from .config import LLMSettings, resolve_llm_settings

T = TypeVar("T")


class LLMClient:
    """OpenAI 兼容 Chat Completions 客户端（DeepSeek / Kimi / vLLM 等）。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 2,
        settings: LLMSettings | None = None,
    ) -> None:
        cfg = settings or resolve_llm_settings(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        self.provider = cfg.provider
        self.backend = cfg.backend
        self.api_key = cfg.api_key
        self.base_url = cfg.base_url
        self.model = cfg.model
        self.temperature = cfg.temperature
        self.ws_url = cfg.ws_url
        self.ws_sender = cfg.ws_sender
        self.ws_user = cfg.ws_user
        self.top_p = cfg.top_p
        self.top_k = cfg.top_k
        self.max_tokens = cfg.max_tokens
        self.stop = cfg.stop
        self.enable_thinking = cfg.enable_thinking
        self.timeout = timeout
        self.max_retries = max_retries

    @staticmethod
    def _retry_delay_seconds(attempt: int) -> float:
        """指数退避：attempt 从 0 开始，依次 1s → 2s → 4s。"""
        return 1.0 * (2 ** attempt)

    async def _retry_delay(self, attempt: int) -> None:
        """异步版指数退避（不阻塞事件循环）。"""
        await asyncio.sleep(self._retry_delay_seconds(attempt))

    def _post(self, messages: list[dict[str, str]], *, json_mode: bool = True) -> str:
        if self.backend == "websocket":
            return asyncio.run(self._ws_chat(messages, stream=False))

        body: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        label = self.provider
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
                return body["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{label} API 返回 HTTP {exc.code}：{detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"无法连接 {label} API：{exc.reason}") from exc

    def _stream_sync(
        self, messages: list[dict[str, str]], *, json_mode: bool = False
    ) -> Iterable[str]:
        if self.backend == "websocket":
            yield asyncio.run(self._ws_chat(messages, stream=False))
            return

        """同步读取 SSE 流式响应，逐块产出 content 增量（阻塞调用，供线程内使用）。"""
        body: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": True,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        label = self.provider
        started = False
        # 连接阶段失败（尚未产出任何 chunk）时指数退避重试；
        # 一旦开始产出内容，中途断流不再重试（避免已输出块重复）。
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    for raw_line in response:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            return
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        delta = obj["choices"][0]["delta"]
                        content = delta.get("content") or ""
                        if content:
                            started = True
                            yield content
                return
            except urllib.error.HTTPError as exc:
                if started or attempt >= self.max_retries:
                    detail = exc.read().decode("utf-8", errors="replace")
                    raise RuntimeError(
                        f"{label} API 返回 HTTP {exc.code}：{detail}"
                    ) from exc
                time.sleep(self._retry_delay_seconds(attempt))
            except urllib.error.URLError as exc:
                if started or attempt >= self.max_retries:
                    raise RuntimeError(f"无法连接 {label} API：{exc.reason}") from exc
                time.sleep(self._retry_delay_seconds(attempt))

    def _ws_body(self, messages: list[dict[str, str]], *, stream: bool) -> dict:
        body: dict = {
            "api_key": self.api_key,
            "model": self.model,
            "stream": stream,
            "extra_body": {
                "enable_thinking": self.enable_thinking,
            },
            "stream_options": {
                "include_usage": True,
                "debug_usage": True,
            },
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if self.ws_user:
            body["user"] = self.ws_user
        if self.stop:
            body["stop"] = list(self.stop)
        return body

    def _ws_connect(self, headers: dict[str, str]):
        if websockets is None:
            raise RuntimeError(
                "当前环境未安装 websockets，请先执行：pip install -r requirements.txt"
            )
        try:
            return websockets.connect(self.ws_url, additional_headers=headers)
        except TypeError:
            return websockets.connect(self.ws_url, extra_headers=headers)

    @staticmethod
    def _choice_content(choice: dict) -> str:
        message = choice.get("message") or {}
        if message.get("content"):
            return message["content"]
        delta = choice.get("delta") or {}
        if delta.get("content"):
            return delta["content"]
        return choice.get("text") or ""

    async def _ws_chat(self, messages: list[dict[str, str]], *, stream: bool) -> str:
        headers = {"sender": self.ws_sender} if self.ws_sender else {}
        payload = json.dumps(
            self._ws_body(messages, stream=stream),
            ensure_ascii=False,
        )
        chunks: list[str] = []
        label = self.provider
        try:
            async with self._ws_connect(headers) as websocket:
                await websocket.send(payload)
                while True:
                    try:
                        raw = await asyncio.wait_for(websocket.recv(), timeout=self.timeout)
                    except websockets.exceptions.ConnectionClosedOK:
                        break
                    if not raw:
                        continue
                    obj = json.loads(raw)
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    content = self._choice_content(choice)
                    if content:
                        chunks.append(content)
                    if choice.get("finish_reason"):
                        break
        except TimeoutError as exc:
            raise RuntimeError(f"{label} WebSocket 调用超时") from exc
        except OSError as exc:
            raise RuntimeError(f"无法连接 {label} WebSocket：{exc}") from exc
        except Exception as exc:
            if websockets is not None and isinstance(
                exc, websockets.exceptions.WebSocketException
            ):
                raise RuntimeError(f"{label} WebSocket 返回异常：{exc}") from exc
            raise
        if not chunks:
            raise RuntimeError(f"{label} WebSocket 未返回有效内容")
        return "".join(chunks)

    async def stream_text(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[str]:
        """流式调用 LLM 返回纯文本增量块（SSE，非 JSON 模式）。

        同步 SSE 读取在后台线程执行，通过 asyncio.Queue 桥接，
        边读边产出，不阻塞事件循环。
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        loop = asyncio.get_running_loop()
        # asyncio.Queue 非线程安全，必须经 loop.call_soon_threadsafe 桥接，
        # 否则后台线程 put 无法可靠唤醒事件循环中的 get（Windows 下会卡死）
        queue: asyncio.Queue = asyncio.Queue()

        def _producer() -> None:
            try:
                for chunk in self._stream_sync(messages, json_mode=False):
                    try:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
                    except RuntimeError:
                        return  # 事件循环已关闭（调用方提前退出）
            except Exception as exc:  # 跨线程传递异常
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, exc)
                except RuntimeError:
                    return
            finally:
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, None)
                except RuntimeError:
                    pass

        threading.Thread(target=_producer, daemon=True).start()
        while True:
            item = await queue.get()
            if item is None:
                return
            if isinstance(item, Exception):
                raise item
            yield item

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
            try:
                last_content = await asyncio.to_thread(self._post, messages)
            except RuntimeError:
                # 网络类错误（连接失败/超时/限流）：与内容无关，
                # 指数退避后重发同一请求；耗尽则抛出交给上层降级。
                if attempt >= self.max_retries:
                    raise
                await self._retry_delay(attempt)
                continue
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

        from schema_repair import SchemaRepairAgent

        repair_agent = SchemaRepairAgent(self)
        repaired = await repair_agent.run(last_content, contract, last_error)
        try:
            return self._parse_and_validate(repaired, response_model)
        except OutputValidationError as exc:
            raise RuntimeError(
                f"{response_model.__name__} 输出无法满足结构契约：{exc}"
            ) from exc

    async def text(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """调用 LLM 返回纯文本（非 JSON 模式）。

        网络类错误（连接失败/超时/限流）指数退避重试，耗尽后抛出。
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        for attempt in range(self.max_retries + 1):
            try:
                return await asyncio.to_thread(self._post, messages, json_mode=False)
            except RuntimeError:
                if attempt >= self.max_retries:
                    raise
                await self._retry_delay(attempt)
        raise RuntimeError("text() 重试耗尽（不可达）")

