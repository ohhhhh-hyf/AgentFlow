"""Meeting-domain memory built around registry, meeting log, state and index."""
from __future__ import annotations

from .bind import BindResult, bind_meeting
from .extract import MeetingFact, extract_meeting_fact
from .inject import build_memory_context
from .runtime import build_line_extra, persist_after_run
from .store import (
    append_or_replace_meeting,
    load_registry,
    load_state,
    meeting_root,
    save_registry,
    save_state,
)

__all__ = [
    "BindResult",
    "MeetingFact",
    "append_or_replace_meeting",
    "bind_meeting",
    "build_line_extra",
    "build_memory_context",
    "extract_meeting_fact",
    "load_registry",
    "load_state",
    "meeting_root",
    "persist_after_run",
    "save_registry",
    "save_state",
]
