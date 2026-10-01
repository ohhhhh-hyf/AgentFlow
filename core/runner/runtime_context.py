"""Runtime domain discovery for the CLI entrypoint (backward-compatibility alias for core.runner.context)."""
from __future__ import annotations

from core.runner.context import (
    SHORT_ALIASES,
    DomainContext,
    env_path,
    load_domain,
    normalize_tasks,
)

__all__ = ["DomainContext", "SHORT_ALIASES", "env_path", "load_domain", "normalize_tasks"]
