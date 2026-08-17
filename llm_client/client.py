from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Iterable
from typing import Any, TypeVar

try:
    import websockets
except ModuleNotFoundError:  # pragma: no cover - depends on selected backend
    websockets = None

from tools.validation import OutputValidationError, validate_payload

from .config import LLMSettings, resolve_llm_settings

T = TypeVar("T")
logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI 兼容 Chat Completions 客户端（DeepSeek / Kimi / vLLM 等）。

    支持：
    - 后端：DeepSeek HTTP（LLM_BACKEND=http）、WebSocket（LLM_BACKEND=websocket）、
      本地 vLLM 服务器（LLM_BACKEND=vllm，OpenAI 兼容 HTTP）
    - 每次调用覆盖 temperature / json_mode / max_tokens / timeout
    - 网络错误指数退避重试
    - 可选进程内文本缓存（``use_cache=True``）
    - token usage 累计（``usage_totals`` / ``last_usage``）
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        settings: LLMSettings | None = None,
    ) -> None:
        cfg = settings or resolve_llm_settings(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            max_retries=max_retries,
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
        self.timeout = cfg.timeout
        self.max_retries = cfg.max_retries
        # 调用统计
        self.last_usage: dict[str, int] = {}
        self.usage_totals: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "calls": 0,
            "cache_hits": 0,
        }
        # 进程内缓存：key → content（仅 text 且 use_cache=True）
        self._response_cache: dict[str, str] = {}

    @staticmethod
    def _retry_delay_seconds(attempt: int) -> float:
        """指数退避：attempt 从 0 开始，依次 1s → 2s → 4s。"""
        return 1.0 * (2**attempt)

    async def _retry_delay(self, attempt: int) -> None:
        """异步版指数退避（不阻塞事件循环）。"""
        await asyncio.sleep(self._retry_delay_seconds(attempt))

    def _record_usage(self, usage: dict | None, *, count_call: bool = True) -> None:
        if count_call:
            self.usage_totals["calls"] += 1
        if not usage or not isinstance(usage, dict):
            self.last_usage = {}
            return
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
        total = int(usage.get("total_tokens") or (prompt + completion))
        self.last_usage = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }
        self.usage_totals["prompt_tokens"] += prompt
        self.usage_totals["completion_tokens"] += completion
        self.usage_totals["total_tokens"] += total
        if total:
            logger.debug(
                "LLM usage provider=%s model=%s prompt=%s completion=%s total=%s",
                self.provider,
                self.model,
                prompt,
                completion,
                total,
            )

    def _cache_key(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        json_mode: bool,
        max_tokens: int | None,
    ) -> str:
        payload = {
            "model": self.model,
            "temperature": temperature,
            "json_mode": json_mode,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _post(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = True,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> str:
        temp = self.temperature if temperature is None else float(temperature)
        tok = self.max_tokens if max_tokens is None else max_tokens
        to = self.timeout if timeout is None else float(timeout)

        if self.backend == "websocket":
            # websocket 路径暂不支持逐参数覆盖 temperature 以外的全部选项
            prev = self.temperature
            try:
                self.temperature = temp
                return asyncio.run(self._ws_chat(messages, stream=False))
            finally:
                self.temperature = prev

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temp,
        }
        if tok is not None:
            body["max_tokens"] = tok
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.provider == "vllm":
            # vLLM（OpenAI 兼容）支持 top_p / top_k；DeepSeek 官方不支持 top_k，故仅 vllm 透传
            body["top_p"] = self.top_p
            body["top_k"] = self.top_k
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
            with urllib.request.urlopen(request, timeout=to) as response:
                raw = response.read().decode("utf-8")
                try:
                    resp = json.loads(raw)
                    self._record_usage(resp.get("usage"), count_call=True)
                    return resp["choices"][0]["message"].get("content") or ""
                except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                    raise RuntimeError(
                        f"{label} API 返回非标准响应：{raw[:200]!r}"
                    ) from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{label} API 返回 HTTP {exc.code}：{detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"无法连接 {label} API：{exc.reason}") from exc

    def _stream_sync(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> Iterable[str]:
        """同步读取流式响应，逐块产出 content 增量。"""
        temp = self.temperature if temperature is None else float(temperature)
        tok = self.max_tokens if max_tokens is None else max_tokens
        to = self.timeout if timeout is None else float(timeout)

        if self.backend == "websocket":
            prev = self.temperature
            try:
                self.temperature = temp
                for attempt in range(self.max_retries + 1):
                    try:
                        text = asyncio.run(self._ws_chat(messages, stream=False))
                    except RuntimeError:
                        if attempt >= self.max_retries:
                            raise
                        time.sleep(self._retry_delay_seconds(attempt))
                        continue
                    if text:
                        yield text
                    return
            finally:
                self.temperature = prev
            return

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temp,
            "stream": True,
        }
        if tok is not None:
            body["max_tokens"] = tok
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.provider == "vllm":
            # vLLM（OpenAI 兼容）支持 top_p / top_k；DeepSeek 官方不支持 top_k，故仅 vllm 透传
            body["top_p"] = self.top_p
            body["top_k"] = self.top_k
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
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=to) as response:
                    for raw_line in response:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:") :].strip()
                        if data == "[DONE]":
                            self.usage_totals["calls"] += 1
                            return
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        # 部分后端在 stream 末包 usage
                        if obj.get("usage"):
                            self._record_usage(obj.get("usage"))
                        delta = obj["choices"][0].get("delta") or {}
                        content = delta.get("content") or ""
                        if content:
                            started = True
                            yield content
                if not started:
                    self.usage_totals["calls"] += 1
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
                "debug_usage": False,
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
                        raw = await asyncio.wait_for(
                            websocket.recv(), timeout=self.timeout
                        )
                    except websockets.exceptions.ConnectionClosedOK:
                        break
                    if not raw:
                        continue
                    obj = json.loads(raw)
                    if obj.get("usage"):
                        self._record_usage(obj.get("usage"))
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
        self.usage_totals["calls"] += 1
        return "".join(chunks)

    async def stream_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> AsyncIterator[str]:
        """流式调用 LLM 返回纯文本增量块（SSE，非 JSON 模式）。"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _producer() -> None:
            try:
                for chunk in self._stream_sync(
                    messages,
                    json_mode=False,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                ):
                    try:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
                    except RuntimeError:
                        return
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
    def _extract_json_payload(content: str) -> str:
        """去掉围栏/前后废话，只保留第一个 JSON 对象或数组。"""
        text = (content or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            fence = text.rfind("```")
            if fence >= 0:
                text = text[:fence].strip()
            if text[:4].lower() == "json":
                text = text[4:].lstrip()
        if text.startswith("{") or text.startswith("["):
            return text
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start : end + 1]
        return text

    @staticmethod
    def _parse_and_validate(content: str, response_model: type[T]) -> T:
        payload = LLMClient._extract_json_payload(content)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise OutputValidationError(f"不是合法 JSON：{exc}") from exc
        return validate_payload(response_model, data)

    async def structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        output_contract: str,
        *,
        temperature: float | None = 0.0,
        max_tokens: int | None = None,
        timeout: float | None = None,
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
                    + "\n5. 模板中字符串字段的占位是空字符串 \"\"、数组占位是 []："
                    "按字段语义填真实内容，不要原样输出占位。"
                    + "\n6. 模板下方若有「字段说明」段，仅用于理解字段含义，"
                    "禁止把说明文字照抄进输出值；输出只包含 JSON 对象本身。"
                    + f"\n输出模板：\n{contract}"
                ),
            },
            {"role": "user", "content": user_prompt},
        ]
        last_content = ""
        last_error = ""
        # structured 默认更低温度以稳住 schema
        temp = 0.0 if temperature is None else temperature

        for attempt in range(self.max_retries + 1):
            try:
                last_content = await asyncio.to_thread(
                    self._post,
                    messages,
                    json_mode=True,
                    temperature=temp,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
            except RuntimeError:
                if attempt >= self.max_retries:
                    raise
                await self._retry_delay(attempt)
                continue
            if not (last_content or "").strip():
                last_error = "模型返回空正文"
                if attempt < self.max_retries:
                    await self._retry_delay(attempt)
                    continue
                break
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

        if not (last_content or "").strip():
            raise RuntimeError(
                f"{response_model.__name__} 输出无法满足结构契约：模型返回空正文"
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
        *,
        temperature: float | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
        timeout: float | None = None,
        use_cache: bool = False,
    ) -> str:
        """调用 LLM 返回文本。

        Args:
            temperature: 覆盖默认采样温度；None 用客户端默认。
            json_mode: 是否要求 JSON object 响应格式。
            max_tokens: 覆盖默认 max_tokens。
            timeout: 覆盖默认超时（秒）。
            use_cache: 命中相同 messages+参数时返回缓存（适合编译类幂等调用）。
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        temp = self.temperature if temperature is None else float(temperature)
        cache_key = ""
        if use_cache:
            cache_key = self._cache_key(
                messages,
                temperature=temp,
                json_mode=json_mode,
                max_tokens=max_tokens,
            )
            hit = self._response_cache.get(cache_key)
            if hit is not None:
                self.usage_totals["cache_hits"] += 1
                logger.debug("LLM cache hit key=%s…", cache_key[:12])
                return hit

        for attempt in range(self.max_retries + 1):
            try:
                content = await asyncio.to_thread(
                    self._post,
                    messages,
                    json_mode=json_mode,
                    temperature=temp,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
                if use_cache and cache_key:
                    self._response_cache[cache_key] = content
                return content
            except RuntimeError:
                if attempt >= self.max_retries:
                    raise
                await self._retry_delay(attempt)
        raise RuntimeError("text() 重试耗尽（不可达）")
