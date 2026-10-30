"""基于 LangGraph 的企业级待办时间转换 Agent。

架构设计（工业级混合双通道）：
                      ┌─── [全部由规则引擎命中] ────────────────────────────────────────┐
                      │                                                                  ▼
    START -> fast_extract -> [是否有未匹配项?] -> llm_extract_pending -> resolve_deadlines -> END
                      │
                      └─── [有复杂语义项] ──> 仅将未匹配项送入 LLM (节省 80%+ Token)

1. fast_extract：基于 fast_path 规则库，毫秒级直接解析 85%+ 高频标准表达；
2. llm_extract_pending：仅对无法被规则覆盖的复杂长句调用 DeepSeek 提取 IR；
3. resolve_deadlines：确定性日历工具根据 meeting_start_time 精确计算绝对时间。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Protocol, Sequence, TypedDict

from langgraph.graph import END, START, StateGraph

from .config import DEFAULT_TIMEZONE
from .fast_path import try_fast_extract
from .llm import CalendarLLM
from .models import DeadlineIR, ExtractionResponse, ResolvedDeadline
from .prompts import DEADLINE_EXTRACTION_SYSTEM_PROMPT, build_extraction_user_prompt
from .tool import resolve_deadlines


class CalendarLLMProtocol(Protocol):
    """calendar 只需要一个批量 JSON 调用接口。"""

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> Dict[str, Any]: ...


class CalendarState(TypedDict, total=False):
    meeting_start_time: str
    timezone: str
    texts: List[str]
    use_fast_path: bool
    fast_irs: Dict[int, Dict[str, Any]]
    pending_items: List[Dict[str, Any]]
    irs: List[Dict[str, Any]]
    results: List[Dict[str, Any]]
    error: Optional[str]


def _ambiguous_ir(index: int, raw: str, reason: str) -> DeadlineIR:
    return DeadlineIR(
        index=index,
        raw=raw,
        status="ambiguous",
        reason=reason,
    )


async def _llm_extract_pending(
    pending_items: List[Dict[str, Any]],
    client: Optional[CalendarLLMProtocol] = None,
) -> Dict[int, DeadlineIR]:
    """仅向 LLM 提交未命中规则的项进行批提取。"""
    if not pending_items:
        return {}

    llm = client or CalendarLLM()
    last_error = ""

    for attempt in range(2):
        user_prompt = build_extraction_user_prompt(pending_items)
        if attempt:
            user_prompt += (
                f"\n\n注意：上一次解析未通过校验：{last_error}\n"
                "请严格输出合法 JSON，items 的 index 必须与输入一致。"
            )
        try:
            payload = await llm.chat_json(
                DEADLINE_EXTRACTION_SYSTEM_PROMPT,
                user_prompt,
            )
            resp = ExtractionResponse.model_validate(payload)
            by_index: Dict[int, DeadlineIR] = {}
            for ir in resp.items:
                by_index[ir.index] = ir

            missing = [item["index"] for item in pending_items if item["index"] not in by_index]
            if missing:
                raise ValueError(f"缺少输入项对应的 index：{missing}")

            # 纠正 raw 为原始文本（防止模型篡改原文）
            for item in pending_items:
                idx = item["index"]
                by_index[idx] = by_index[idx].model_copy(update={"raw": item["text"]})
            return by_index

        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)

    # 重试仍失败：逐条构建 ambiguous 兜底，防止中断批流程
    fallback_map: Dict[int, DeadlineIR] = {}
    for item in pending_items:
        idx = item["index"]
        fallback_map[idx] = _ambiguous_ir(
            index=idx,
            raw=item["text"],
            reason=f"deadline extraction failed: {last_error}",
        )
    return fallback_map


async def extract_irs(
    texts: Sequence[str],
    client: Optional[CalendarLLMProtocol] = None,
    use_fast_path: bool = True,
) -> List[DeadlineIR]:
    """两阶段混合提取 IR：Fast-Path 快路径优先，复杂表达降级给 LLM。"""
    raw_texts = [str(t or "").strip() for t in texts]
    total_count = len(raw_texts)
    if total_count == 0:
        return []

    resolved_irs: Dict[int, DeadlineIR] = {}
    pending_items: List[Dict[str, Any]] = []

    for index, text in enumerate(raw_texts):
        if not text:
            resolved_irs[index] = DeadlineIR(index=index, raw=text, status="none")
            continue

        if use_fast_path:
            fast_ir = try_fast_extract(index, text)
            if fast_ir is not None:
                resolved_irs[index] = fast_ir
                continue

        pending_items.append({"index": index, "text": text})

    # 若存在需要 LLM 解析的复杂项
    if pending_items:
        llm_irs = await _llm_extract_pending(pending_items, client)
        resolved_irs.update(llm_irs)

    # 按照原本顺序组装结果
    return [resolved_irs[i] for i in range(total_count)]


# ── LangGraph 节点定义 ───────────────────────────────────────────

def _build_fast_extract_node():
    async def fast_extract_node(state: CalendarState) -> Dict[str, Any]:
        texts = [str(t or "").strip() for t in state.get("texts") or []]
        use_fast = state.get("use_fast_path", True)

        fast_irs: Dict[int, Dict[str, Any]] = {}
        pending_items: List[Dict[str, Any]] = []

        for index, text in enumerate(texts):
            if not text:
                fast_irs[index] = DeadlineIR(index=index, raw=text, status="none").model_dump()
                continue
            if use_fast:
                ir = try_fast_extract(index, text)
                if ir is not None:
                    fast_irs[index] = ir.model_dump()
                    continue
            pending_items.append({"index": index, "text": text})

        return {
            "fast_irs": fast_irs,
            "pending_items": pending_items,
        }

    return fast_extract_node


def _route_after_fast(state: CalendarState) -> str:
    """根据是否全部命中 Fast-Path 进行动态分支路由。"""
    pending = state.get("pending_items") or []
    if pending:
        return "llm_extract"
    return "resolve_deadlines"


def _build_llm_extract_node(client: Optional[CalendarLLMProtocol]):
    async def llm_extract_node(state: CalendarState) -> Dict[str, Any]:
        pending = state.get("pending_items") or []
        fast_irs = state.get("fast_irs") or {}
        error: Optional[str] = None

        try:
            llm_results = await _llm_extract_pending(pending, client)
            for idx, ir in llm_results.items():
                fast_irs[idx] = ir.model_dump()
        except Exception as exc:  # noqa: BLE001
            error = f"time extraction failed: {exc}"
            for item in pending:
                idx = item["index"]
                fast_irs[idx] = _ambiguous_ir(
                    index=idx,
                    raw=item["text"],
                    reason=error,
                ).model_dump()

        return {"fast_irs": fast_irs, "error": error}

    return llm_extract_node


def _build_resolve_node():
    async def resolve_node(state: CalendarState) -> Dict[str, Any]:
        fast_irs = state.get("fast_irs") or {}
        total = len(state.get("texts") or [])
        irs: List[DeadlineIR] = []
        for i in range(total):
            ir_dict = fast_irs.get(i)
            if ir_dict:
                irs.append(DeadlineIR.model_validate(ir_dict))
            else:
                raw_text = state.get("texts", [""])[i] if i < len(state.get("texts", [])) else ""
                irs.append(DeadlineIR(index=i, raw=raw_text, status="none"))

        try:
            results = resolve_deadlines(
                meeting_start=state["meeting_start_time"],
                irs=irs,
                timezone=state.get("timezone") or DEFAULT_TIMEZONE,
            )
            return {
                "irs": [ir.model_dump() for ir in irs],
                "results": [result.model_dump() for result in results],
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "irs": [ir.model_dump() for ir in irs],
                "results": [],
                "error": f"deadline resolution failed: {exc}",
            }

    return resolve_node


def build_graph(
    client: Optional[CalendarLLMProtocol] = None,
):
    """编译企业级混合分流 LangGraph 图。"""
    builder = StateGraph(CalendarState)

    builder.add_node("fast_extract", _build_fast_extract_node())
    builder.add_node("llm_extract", _build_llm_extract_node(client))
    builder.add_node("resolve_deadlines", _build_resolve_node())

    # START -> fast_extract -> 条件分支 (命中全部走resolve，未全部命中走LLM)
    builder.add_edge(START, "fast_extract")
    builder.add_conditional_edges(
        "fast_extract",
        _route_after_fast,
        {
            "llm_extract": "llm_extract",
            "resolve_deadlines": "resolve_deadlines",
        },
    )
    builder.add_edge("llm_extract", "resolve_deadlines")
    builder.add_edge("resolve_deadlines", END)

    return builder.compile()


async def run_deadline_agent(
    meeting_start_time: str,
    texts: Sequence[str],
    timezone: str = DEFAULT_TIMEZONE,
    client: Optional[CalendarLLMProtocol] = None,
    use_fast_path: bool = True,
) -> Dict[str, Any]:
    """执行完整图，返回 results 与 error。"""
    graph = build_graph(client)
    state: CalendarState = {
        "meeting_start_time": meeting_start_time,
        "timezone": timezone,
        "texts": [str(text or "") for text in texts],
        "use_fast_path": use_fast_path,
    }
    final = await graph.ainvoke(state)
    results = [
        ResolvedDeadline.model_validate(item).model_dump()
        for item in final.get("results") or []
    ]
    return {
        "meeting_start_time": meeting_start_time,
        "timezone": timezone,
        "results": results,
        "error": final.get("error"),
    }


def run_deadline_agent_sync(
    meeting_start_time: str,
    texts: Sequence[str],
    timezone: str = DEFAULT_TIMEZONE,
    client: Optional[CalendarLLMProtocol] = None,
    use_fast_path: bool = True,
) -> Dict[str, Any]:
    """同步入口，方便 CLI 和业务同步服务直接调用。"""
    return asyncio.run(
        run_deadline_agent(
            meeting_start_time=meeting_start_time,
            texts=texts,
            timezone=timezone,
            client=client,
            use_fast_path=use_fast_path,
        )
    )


__all__ = [
    "CalendarLLMProtocol",
    "build_graph",
    "extract_irs",
    "run_deadline_agent",
    "run_deadline_agent_sync",
]
