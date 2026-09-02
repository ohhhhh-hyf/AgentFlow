"""Runtime facade for meeting memory v2."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from tools.memory.store import safe_id

from .bind import bind_meeting
from .extract import MeetingFact, extract_meeting_fact
from .inject import build_memory_context
from .state import backfill_meeting_titles, update_state
from .store import (
    append_or_replace_meeting,
    list_meetings,
    load_registry,
    load_state,
    save_registry,
    save_state,
)

logger = logging.getLogger(__name__)

META_KEY = "__meeting_memory__"


def encode_meta(
    project_root: Path,
    user_id: str,
    project: str = "",
    request_id: str = "",
    meeting_time: str = "",
) -> str:
    return json.dumps(
        {
            "project_root": str(project_root),
            "user_id": user_id or "",
            "project": project or "",
            "request_id": request_id or "",
            "time": meeting_time or "",
        },
        ensure_ascii=False,
    )


def decode_meta(line_extra: dict[str, str] | None) -> dict[str, str]:
    raw = (line_extra or {}).get(META_KEY) or ""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return {str(k): str(v or "") for k, v in data.items()}
    except Exception:
        return {}


def _project_entry(registry: dict[str, Any], project_id: str, explicit_name: str = "") -> dict[str, Any]:
    projects = registry.setdefault("projects", {})
    project = projects.get(project_id)
    if not isinstance(project, dict):
        project = {
            "name": explicit_name or project_id,
            "aliases": [],
            "anchors": [],
            "negative_anchors": [],
            "updated_at": "",
        }
        projects[project_id] = project
    if explicit_name and explicit_name not in [project.get("name"), *(project.get("aliases") or [])]:
        if not project.get("name") or project.get("name") == project_id:
            project["name"] = explicit_name
        else:
            aliases = [str(x) for x in (project.get("aliases") or []) if str(x).strip()]
            aliases.append(explicit_name)
            project["aliases"] = list(dict.fromkeys(aliases))[:12]
    return project


def _merge_registry_project(project: dict[str, Any], fact: MeetingFact, stamp: str) -> None:
    anchors = [str(x).strip() for x in (project.get("anchors") or []) if str(x).strip()]
    for anchor in fact.anchors:
        if anchor and anchor not in anchors:
            anchors.append(anchor)
    project["anchors"] = anchors[:40]
    project.setdefault("aliases", [])
    project.setdefault("negative_anchors", [])
    project["updated_at"] = stamp


def build_line_extra(
    state: dict[str, Any],
    line_name: str,
    *,
    line_extra: dict[str, str] | None = None,
) -> str:
    """Build memory context after meeting_understanding and before line generation."""
    if line_name not in {"minutes", "minutes_styles"}:
        return ""
    meta = decode_meta(line_extra)
    if not meta.get("user_id"):
        return ""
    project_root = Path(meta.get("project_root") or ".")
    user_id = meta["user_id"]
    transcript = str(state.get("transcript") or "")
    fact = extract_meeting_fact(
        state.get("meeting_understanding") or {},
        transcript,
        request_id=meta.get("request_id") or "",
    )
    registry = load_registry(project_root, user_id)
    bind = bind_meeting(registry, fact, explicit_project=meta.get("project") or "")
    if bind.mode == "explicit" or bind.confidence == "high":
        project = _project_entry(registry, bind.project_id, meta.get("project") or "")
        state_doc = load_state(project_root, user_id, bind.project_id)
        state_doc = backfill_meeting_titles(state_doc, list_meetings(project_root, user_id))
        context = build_memory_context(
            project_id=bind.project_id,
            project=project,
            state=state_doc,
            bind=bind,
        )
        return context
    return ""


def _report_text(reports: dict[str, Any], line: str) -> str:
    report = reports.get(line)
    if report is None:
        return ""
    if hasattr(report, "model_dump"):
        data = report.model_dump()
    elif isinstance(report, dict):
        data = report
    else:
        return ""
    for key in ("personalized_minutes", "personalized_text"):
        text = data.get(key)
        if isinstance(text, str) and text.strip():
            return text
    return ""


def _report_headline(reports: dict[str, Any], line: str) -> str:
    """取 minutes/minutes_styles 报告里的纪要标题（headline），用于覆盖记忆中的会议标题。"""
    report = reports.get(line)
    if report is None:
        return ""
    if hasattr(report, "model_dump"):
        data = report.model_dump()
    elif isinstance(report, dict):
        data = report
    else:
        return ""
    for key in ("headline", "title"):
        text = data.get(key)
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def persist_after_run(
    project_root: Path,
    user_id: str,
    project: str,
    request_id: str,
    transcript: str,
    reports: dict[str, Any],
    understanding: dict[str, Any] | None,
    *,
    meeting_time: str = "",
) -> dict[str, Any] | None:
    """Persist meeting fact, update project state for explicit/high bindings, sync index."""
    if not (user_id or "").strip():
        return None
    try:
        fact = extract_meeting_fact(
            understanding or {},
            transcript,
            request_id=request_id,
            time=meeting_time or "",
        )
        # 本场纪要已生成：用 minutes 的 headline（纪要标题）作为该场会议标题写入记忆，
        # 后续历史溯源卡片展示的「来源会议」即为纪要标题，而非议题名/主题行解析结果。
        headline = _report_headline(reports, "minutes") or _report_headline(reports, "minutes_styles")
        if headline:
            fact.title = headline
        registry = load_registry(project_root, user_id)
        bind = bind_meeting(registry, fact, explicit_project=project or "")
        fact.project_id = bind.project_id if bind.confidence == "high" else ""
        fact.bind = bind.as_dict()
        meeting = fact.as_dict()
        rendered = _report_text(reports, "minutes") or _report_text(reports, "minutes_styles")
        if rendered:
            meeting["rendered_preview"] = rendered[:1000]
        state_doc: dict[str, Any] | None = None
        if bind.mode == "explicit" or bind.confidence == "high":
            pid = bind.project_id
            project_entry = _project_entry(registry, pid, project or "")
            _merge_registry_project(project_entry, fact, fact.time)
            prev = load_state(project_root, user_id, pid)
            prev = backfill_meeting_titles(prev, list_meetings(project_root, user_id))
            state_doc = update_state(
                prev,
                fact,
                pid,
                project_name=str(project_entry.get("name") or project or pid),
            )
            save_state(project_root, user_id, pid, state_doc)
            save_registry(project_root, user_id, registry)
        append_or_replace_meeting(project_root, user_id, meeting)
        return meeting
    except Exception:
        logger.warning("会议记忆 v2 写回失败", exc_info=True)
        return None


__all__ = ["META_KEY", "build_line_extra", "decode_meta", "encode_meta", "persist_after_run"]
