"""应用层：CLI 参数、领域加载、输入解析。

兼容入口仍是 ``from tools.runner import run`` /
``from tools.runtime_context import load_domain``。
"""
from tools.io import load_transcript, load_user
from tools.runner import (
    build_parser,
    collect_modes,
    collect_templates,
    parse_domain_name,
    run,
)
from tools.runtime_context import DomainContext, load_domain, normalize_tasks

__all__ = [
    "DomainContext",
    "build_parser",
    "collect_modes",
    "collect_templates",
    "load_domain",
    "load_transcript",
    "load_user",
    "normalize_tasks",
    "parse_domain_name",
    "run",
]
