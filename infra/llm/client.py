"""统一纯净版 LLMClient (纯原生实现, 零旧代码依赖).

支持:
- stream_text: 流式返回增量文本 (SSE, 用于纪要流式直出)
- chat_json: 结构化返回解析后的 JSON 对象/数组 (用于待办与智能分类)
- text: 同步/异步单次文本补全
- 自动指数退避重试 (对网络超时/429/5xx 错误自动重试)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Iterable
from typing import Any

from .config import LLMSettings, resolve_llm_settings

logger = logging.getLogger("infra.llm.client")


class LLMClient:
    """OpenAI 兼容 Chat Completions 极简客户端."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        settings: LLMSettings | None = None,
    ) -> None:
        self.cfg = settings or resolve_llm_settings(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.api_key = self.cfg.api_key
        self.base_url = self.cfg.base_url
        self.model = self.cfg.model
        self.temperature = self.cfg.temperature
        self.timeout = self.cfg.timeout
        self.max_retries = self.cfg.max_retries

        # 统计指标
        self.usage_totals: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "calls": 0,
        }
        self._lock = threading.Lock()

    def _retry_delay(self, attempt: int) -> float:
        return min(1.0 * (2**attempt), 8.0)

    def _build_request(self, body: dict[str, Any]) -> urllib.request.Request:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        url = f"{self.base_url}/chat/completions"
        return urllib.request.Request(url, data=payload, headers=headers, method="POST")

    def _stream_sync(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> Iterable[str]:
        """同步读取 SSE 流式响应, 逐块产出 content 增量."""
        temp = self.temperature if temperature is None else float(temperature)
        to_val = self.timeout if timeout is None else float(timeout)

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temp,
            "stream": True,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        req = self._build_request(body)
        started = False

        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=to_val) as resp:
                    for raw_line in resp:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:") :].strip()
                        if data == "[DONE]":
                            with self._lock:
                                self.usage_totals["calls"] += 1
                            return
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        # 记录 usage (若返回)
                        if usage := obj.get("usage"):
                            with self._lock:
                                self.usage_totals["prompt_tokens"] += usage.get("prompt_tokens", 0)
                                self.usage_totals["completion_tokens"] += usage.get("completion_tokens", 0)
                                self.usage_totals["total_tokens"] += usage.get("total_tokens", 0)

                        delta = obj.get("choices", [{}])[0].get("delta", {})
                        if content := delta.get("content"):
                            started = True
                            yield content
                return
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                if started or attempt >= self.max_retries:
                    logger.error("[LLMClient] stream 失败 (attempt=%d): %s", attempt, exc)
                    raise RuntimeError(f"LLM 流式调用失败: {exc}") from exc
                time.sleep(self._retry_delay(attempt))

    async def stream_text(
        self,
        system_prompt: str = "",
        user_prompt: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        *,
        prompt: str = "",
        system: str = "",
    ) -> AsyncIterator[str]:
        """异步生成器: 流式直出文本块 (NDJSON 消费通道)."""
        sys_val = system or system_prompt or ""
        usr_val = prompt or user_prompt or ""
        messages = [
            {"role": "system", "content": sys_val},
            {"role": "user", "content": usr_val},
        ]
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _producer() -> None:
            try:
                for chunk in self._stream_sync(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=_producer, daemon=True).start()

        t0 = time.perf_counter()
        first_token_logged = False
        chunks_count = 0
        logger.info(f"[LLM:STREAM:START] model={self.model} stream=True")

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            if not first_token_logged:
                ttft = time.perf_counter() - t0
                logger.info(f"[LLM:STREAM:FIRST_TOKEN] ttft={ttft:.3f}s")
                first_token_logged = True
            chunks_count += 1
            yield item

        dur = time.perf_counter() - t0
        logger.info(f"[LLM:STREAM:DONE] dur={dur:.3f}s chunks={chunks_count}")

    def _chat_sync(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """非流式单次同步调用."""
        temp = self.temperature if temperature is None else float(temperature)
        to_val = self.timeout if timeout is None else float(timeout)

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temp,
            "stream": False,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        req = self._build_request(body)
        t0 = time.perf_counter()

        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=to_val) as resp:
                    raw_data = resp.read().decode("utf-8", errors="replace")
                    obj = json.loads(raw_data)
                    with self._lock:
                        self.usage_totals["calls"] += 1
                        if usage := obj.get("usage"):
                            self.usage_totals["prompt_tokens"] += usage.get("prompt_tokens", 0)
                            self.usage_totals["completion_tokens"] += usage.get("completion_tokens", 0)
                            self.usage_totals["total_tokens"] += usage.get("total_tokens", 0)
                    dur = time.perf_counter() - t0
                    logger.info(f"[LLM:CHAT:DONE] model={self.model} dur={dur:.3f}s")
                    return obj["choices"][0]["message"]["content"]
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                if attempt >= self.max_retries:
                    logger.error("[LLMClient] 非流式调用失败 (attempt=%d): %s", attempt, exc)
                    raise RuntimeError(f"LLM 调用失败: {exc}") from exc
                time.sleep(self._retry_delay(attempt))

        raise RuntimeError("LLM 调用超过最大重试次数")

    async def text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """异步单次文本返回."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await asyncio.to_thread(
            self._chat_sync,
            messages,
            json_mode=False,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> Any:
        """异步调用并解析结构化 JSON 对象/数组."""
        raw = await self.text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        return self.extract_json_payload(raw)

    @staticmethod
    def extract_json_payload(content: str) -> Any:
        """提纯并解析字符串中的 JSON 对象或数组."""
        text = (content or "").strip()
        # 去除 markdown 代码块
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text).strip()

        # 直接尝试解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 判定哪种开括号最先出现，优先提取最外层容器
        pos_brace = text.find("{")
        pos_bracket = text.find("[")

        first = "{"
        if pos_bracket != -1 and (pos_brace == -1 or pos_bracket < pos_brace):
            first = "["

        if first == "[":
            m_arr = re.search(r"(\[[\s\S]*\])", text)
            if m_arr:
                try:
                    return json.loads(m_arr.group(1))
                except Exception:
                    pass
            m_obj = re.search(r"(\{[\s\S]*\})", text)
            if m_obj:
                try:
                    return json.loads(m_obj.group(1))
                except Exception:
                    pass
        else:
            m_obj = re.search(r"(\{[\s\S]*\})", text)
            if m_obj:
                try:
                    return json.loads(m_obj.group(1))
                except Exception:
                    pass
            m_arr = re.search(r"(\[[\s\S]*\])", text)
            if m_arr:
                try:
                    return json.loads(m_arr.group(1))
                except Exception:
                    pass

        raise ValueError(f"无法从大模型响应中提取有效 JSON: {text[:200]!r}")
