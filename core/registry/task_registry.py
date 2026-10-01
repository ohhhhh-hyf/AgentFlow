"""core.registry.task_registry —— 声明式任务线动态注册表。

彻底替代原 tools/codegen/sync_domain.py 对源码（orchestrator.py, models_generated.py 等）的正则替换与代码注入。
每个任务线模块通过 @register_task 装饰器在定义时自注册。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Type


@dataclass
class TaskBundle:
    """一条自包含任务线的元数据与组件集合。"""

    domain: str
    name: str
    cn_name: str
    kind: Any = None
    agent_cls: Type[Any] | None = None
    supervisor_cls: Type[Any] | None = None
    render_cls: Type[Any] | None = None
    report_cls: Type[Any] | None = None
    empty_draft: dict[str, Any] = field(default_factory=dict)
    reject_review: dict[str, Any] = field(default_factory=dict)
    fallback_rules: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


_REGISTRY: dict[tuple[str, str], TaskBundle] = {}


def register_task(
    domain: str,
    name: str,
    cn_name: str = "",
    kind: Any = None,
    empty_draft: dict[str, Any] | None = None,
    reject_review: dict[str, Any] | None = None,
    fallback_rules: Any = None,
    **metadata: Any,
) -> Callable[[Type[Any]], Type[Any]]:
    """任务线自注册类装饰器。"""

    def decorator(cls: Type[Any]) -> Type[Any]:
        bundle = TaskBundle(
            domain=domain.strip().lower(),
            name=name.strip(),
            cn_name=cn_name or getattr(cls, "cn_name", name),
            kind=kind or getattr(cls, "kind", None),
            agent_cls=getattr(cls, "agent", None),
            supervisor_cls=getattr(cls, "supervisor", None),
            render_cls=getattr(cls, "renderer", None),
            report_cls=getattr(cls, "report", None),
            empty_draft=empty_draft or getattr(cls, "empty_draft", {}),
            reject_review=reject_review or getattr(cls, "reject_review", {}),
            fallback_rules=fallback_rules or getattr(cls, "fallback_rules", None),
            metadata=metadata,
        )
        _REGISTRY[(bundle.domain, bundle.name)] = bundle
        return cls

    return decorator


def get_task(domain: str, name: str) -> TaskBundle | None:
    return _REGISTRY.get((domain.strip().lower(), name.strip()))


def list_tasks(domain: str | None = None) -> list[TaskBundle]:
    if domain:
        d = domain.strip().lower()
        return [b for (dom, _), b in _REGISTRY.items() if dom == d]
    return list(_REGISTRY.values())


__all__ = [
    "TaskBundle",
    "get_task",
    "list_tasks",
    "register_task",
]
