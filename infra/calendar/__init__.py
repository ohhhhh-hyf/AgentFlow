"""Calendar：自然语言截止时间解析子包。

对业务方暴露稳定的入口；底层通过 ``infra.llm.LLMClient`` 调用部署版模型。
"""
from __future__ import annotations

from .agent import (
    CalendarLLMProtocol,
    build_graph,
    extract_irs,
    run_deadline_agent,
    run_deadline_agent_sync,
)
from .llm import CalendarLLM, extract_json_object
from .models import DeadlineIR, ResolvedDeadline
from .tool import resolve_deadline, resolve_deadlines

__all__ = [
    "CalendarLLM",
    "CalendarLLMProtocol",
    "DeadlineIR",
    "ResolvedDeadline",
    "build_graph",
    "extract_irs",
    "extract_json_object",
    "resolve_deadline",
    "resolve_deadlines",
    "run_deadline_agent",
    "run_deadline_agent_sync",
]
