"""LangGraph 编排与双通道混合执行测试：用 FakeClient / BrokenClient，不访问真实 DeepSeek。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import run_deadline_agent  # noqa: E402


class FakeClient:
    """模拟新版大模型直接输出精简扁平的 Sparse IR。"""

    async def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        del system_prompt, user_prompt
        return {
            "items": [
                {
                    "index": 0,
                    "raw": "会议后两周",
                    "rule": "offset_weeks",
                    "amount": 2,
                }
            ]
        }


def test_graph_fast_path_direct_resolve() -> None:
    """纯日期表达由 Fast-Path 极速解析，无需经过 LLM。"""
    result = asyncio.run(
        run_deadline_agent(
            meeting_start_time="2026-10-29 14:30:45",
            texts=["明天", "下周三"],
        )
    )
    assert result["error"] is None
    assert len(result["results"]) == 2
    assert result["results"][0]["deadline"] == "2026/10/30"
    assert result["results"][0]["kind"] == "date"
    assert result["results"][1]["deadline"] == "2026/11/04"
    assert result["results"][1]["kind"] == "date"


class CompositeClient:
    """模拟 LLM 解析“日期 + 时段”的组合表达。"""

    async def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        del system_prompt, user_prompt
        return {
            "items": [
                {
                    "index": 0,
                    "raw": "明天下午",
                    "rule": "offset_days",
                    "amount": 1,
                    "slot": "下午",
                }
            ]
        }


def test_graph_composite_expression_goes_to_llm() -> None:
    result = asyncio.run(
        run_deadline_agent(
            meeting_start_time="2026-10-29 14:30:45",
            texts=["明天下午"],
            client=CompositeClient(),
        )
    )
    assert result["results"][0]["deadline"] == "2026/10/30"
    assert result["results"][0]["time_slot"] == "下午"
    assert result["results"][0]["kind"] == "date"


def test_graph_extract_and_resolve_via_llm() -> None:
    """复杂非标准表述自动降级分流到 LLM 节点，以精简扁平 IR 完成解析。"""
    result = asyncio.run(
        run_deadline_agent(
            meeting_start_time="2026-10-29 14:30:45",
            texts=["会议后两周"],
            client=FakeClient(),
        )
    )
    assert result["error"] is None
    assert len(result["results"]) == 1
    assert result["results"][0]["deadline"] == "2026/11/12"
    assert result["results"][0]["kind"] == "date"


def test_graph_handles_missing_index_as_error_result() -> None:
    """当 LLM 客户端返回异常或缺失索引时，单条项优雅捕获为 error，不崩溃整批处理。"""
    class BrokenClient:
        async def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
            del system_prompt, user_prompt
            return {"items": []}

    result = asyncio.run(
        run_deadline_agent(
            meeting_start_time="2026-10-29 14:30:45",
            texts=["外部系统上线后两周"],
            client=BrokenClient(),
        )
    )
    assert result["results"][0]["deadline"] is None
    assert result["results"][0]["error"] is not None


def test_graph_disable_fast_path() -> None:
    """显式指定 use_fast_path=False 时，所有请求强制走 LLM。"""
    result = asyncio.run(
        run_deadline_agent(
            meeting_start_time="2026-10-29 14:30:45",
            texts=["会议后两周"],
            client=FakeClient(),
            use_fast_path=False,
        )
    )
    assert result["results"][0]["deadline"] == "2026/11/12"


class RangeClient:
    async def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        del system_prompt, user_prompt
        return {
            "items": [
                {
                    "index": 0,
                    "raw": "一周内",
                    "range": {
                        "start": {"rule": "same_day"},
                        "end": {"rule": "offset_weeks", "amount": 1},
                    },
                }
            ]
        }


def test_graph_range_expression() -> None:
    result = asyncio.run(
        run_deadline_agent(
            meeting_start_time="2026-10-29 14:30:45",
            texts=["一周内"],
            client=RangeClient(),
        )
    )
    item = result["results"][0]
    assert item["deadline"] == "2026/11/05"
    assert item["deadline_start"] == "2026/10/29"
    assert item["deadline_end"] == "2026/11/05"
    assert item["kind"] == "range"
