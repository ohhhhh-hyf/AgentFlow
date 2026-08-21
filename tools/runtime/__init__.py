"""编排内核：图节点工厂、渲染运行时、纯函数。

领域 orchestrator 仍可 ``from tools.domain_engine import DomainNodes``；
新代码落在本包，避免把产品渲染逻辑继续堆进图 mixin。
"""
from __future__ import annotations

from .context import build_render_context, understanding_of
from .kinds import (
    DETERMINISTIC_PIPELINE,
    LLM_DOCUMENT,
    LLM_EXTRACT,
    LinePolicy,
    policy_for,
    resolve_line_policies,
)

__all__ = [
    "DETERMINISTIC_PIPELINE",
    "LLM_DOCUMENT",
    "LLM_EXTRACT",
    "LinePolicy",
    "build_render_context",
    "policy_for",
    "resolve_line_policies",
    "understanding_of",
]
