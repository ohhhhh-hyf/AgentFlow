"""Runtime facade for meeting memory v2."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .bind import (
    BindResult,
    bind_meeting,
    has_overlap,
    is_strong_anchor,
    is_weak_project_name,
    pick_project_name,
    project_core,
)
from .extract import MeetingFact, extract_meeting_fact
from .inject import build_memory_context
from .state import backfill_meeting_titles, rebuild_state, sort_project_meetings
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


@dataclass
class InjectResult:
    context: str = ""
    bind: BindResult = field(default_factory=BindResult)
    comparison: list[str] = field(default_factory=list)
    warning: str = ""


def _semantic_bind_fallback(fact: MeetingFact, user_id: str) -> BindResult | None:
    """Rules missed or were ambiguous: unique vector winner only."""
    if not (user_id or "").strip():
        return None
    try:
        from tools.memory.embed import MEMORY_EMBED_MIN_SCORE, get_embedder

        embedder = get_embedder(user_id=user_id)
    except Exception:  # noqa: BLE001
        return None
    if not getattr(embedder, "enabled", False):
        return None
    query = " ".join(
        x for x in (
            getattr(fact, "title", ""),
            getattr(fact, "summary", ""),
            " ".join(getattr(fact, "anchors", []) or []),
        ) if x
    )
    if not query.strip():
        return None
    try:
        cands = [
            c for c in embedder.search_projects(
                query, user_id, top_k=3, domain="meeting"
            )
            if float(c.get("score") or 0.0) >= MEMORY_EMBED_MIN_SCORE
        ]
    except Exception:  # noqa: BLE001
        logger.warning("meeting memory semantic match failed, fallback to rules", exc_info=True)
        return None
    if not cands:
        return None
    top = cands[0]
    if len(cands) > 1:
        second = float(cands[1].get("score") or 0.0)
        top_score = float(top.get("score") or 0.0)
        if second >= MEMORY_EMBED_MIN_SCORE and not (
            top_score >= second * 1.15 or top_score - second >= 0.08
        ):
            return None
    pid = str(top.get("project_id") or "")
    if not pid:
        return None
    logger.info(
        "meeting memory semantic fallback title=%r score=%.2f project=%s",
        getattr(fact, "title", ""), float(top.get("score") or 0.0), pid,
    )
    return BindResult(
        project_id=pid,
        mode="auto",
        confidence="high",
        evidence=[f"semantic:{float(top.get('score') or 0.0):.2f}"],
        core_name=str(top.get("project_key") or ""),
    )


def _single_project_prior(
    registry: dict[str, Any],
    meetings: list[dict[str, Any]],
    fact: MeetingFact,
) -> BindResult | None:
    """If this user has one active project and this meeting overlaps it, bind."""
    pids: list[str] = []
    seen: set[str] = set()
    for row in meetings:
        pid = str(row.get("project_id") or "").strip()
        if pid and pid not in seen:
            seen.add(pid)
            pids.append(pid)
    if not pids:
        for pid in (registry.get("projects") or {}):
            if str(pid) not in seen:
                pids.append(str(pid))
    if len(pids) != 1:
        return None
    pid = pids[0]
    project = (registry.get("projects") or {}).get(pid)
    if not isinstance(project, dict):
        project = {"name": pid, "aliases": [], "anchors": []}
    if not has_overlap(project, fact):
        return None
    return BindResult(
        project_id=pid,
        mode="auto",
        confidence="high",
        evidence=["single_project_prior"],
        core_name=str(project.get("name") or pid),
    )


def _provisional_create(fact: MeetingFact) -> BindResult:
    """First meeting with no strong core: still open a project so state can land."""
    name = pick_project_name(fact) or project_core(fact.title) or (fact.title or "").strip()
    name = name or "未命名项目"
    from tools.memory.store import safe_id

    return BindResult(
        project_id=safe_id(name),
        mode="auto_create",
        confidence="high",
        evidence=[f"auto_create:{name}"],
        core_name=project_core(name) or name,
    )


def resolve_bind(
    registry: dict[str, Any],
    fact: MeetingFact,
    explicit_project: str,
    user_id: str,
    meetings: list[dict[str, Any]] | None = None,
) -> BindResult:
    """Rules → unique semantic → single-project prior → auto_create / pending."""
    bind = bind_meeting(registry, fact, explicit_project=explicit_project)
    if bind.mode == "explicit":
        return bind
    if bind.is_bound and bind.mode != "auto_create":
        return bind

    meetings = meetings if meetings is not None else []
    if bind.mode == "auto_create" or bind.confidence == "medium" or not bind.project_id:
        fallback = _semantic_bind_fallback(fact, user_id)
        if fallback is not None:
            return fallback
        prior = _single_project_prior(registry, meetings, fact)
        if prior is not None:
            return prior
    if bind.mode == "auto_create" and bind.is_bound:
        return bind
    if bind.confidence == "medium":
        return bind
    projects = registry.get("projects") or {}
    if not projects:
        return _provisional_create(fact)
    return bind


def _meeting_embed_record(
    project_root: Path,
    user_id: str,
    pid: str,
    project: dict[str, Any],
    state_doc: dict[str, Any],
    meetings: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = sort_project_meetings(meetings, pid)
    sessions: list[dict[str, Any]] = []
    for seq, m in enumerate(rows, start=1):
        sessions.append({
            "seq": seq,
            "title": m.get("title") or "",
            "at": m.get("time") or "",
            "purpose": m.get("summary") or "",
            "decisions": [x for x in (m.get("decisions") or []) if str(x).strip()],
            "open_questions": [x for x in (m.get("open_items") or []) if str(x).strip()],
            "risks": [x for x in (m.get("risks") or []) if str(x).strip()],
        })
    latest_summary = str(rows[-1].get("summary") or "") if rows else ""
    return {
        "project_id": pid,
        "project_key": str(project.get("name") or pid),
        "display_name": str(project.get("name") or pid),
        "name_aliases": [str(a) for a in (project.get("aliases") or []) if str(a).strip()],
        "key_terms": [str(a) for a in (project.get("anchors") or []) if str(a).strip()][:12],
        "entities": [str(a) for a in (project.get("anchors") or []) if str(a).strip()][:10],
        "run_count": len(sessions),
        "active_summary": latest_summary,
        "recent_topics": [str(m.get("title") or "") for m in rows[-6:] if m.get("title")],
        "meeting": {
            "open_items": [
                {"item": str(i.get("text") or "")}
                for i in list(state_doc.get("actions") or []) + list(state_doc.get("open_items") or [])
                if isinstance(i, dict) and i.get("status") == "open" and str(i.get("text") or "").strip()
            ][:6],
            "decisions": [
                {"decision": str(i.get("text") or "")}
                for i in (state_doc.get("decisions") or [])
                if isinstance(i, dict) and str(i.get("text") or "").strip()
                and i.get("status") != "superseded"
            ][-3:],
            "sessions": sessions,
        },
    }


def _sync_meeting_vectors(
    project_root: Path,
    user_id: str,
    pid: str,
    project: dict[str, Any],
    state_doc: dict[str, Any] | None,
) -> None:
    if not pid:
        return
    try:
        from tools.memory.embed import get_embedder

        embedder = get_embedder(user_id=user_id)
        if not getattr(embedder, "enabled", False):
            return
        record = _meeting_embed_record(
            project_root, user_id, pid, project, state_doc or {},
            list_meetings(project_root, user_id),
        )
        if embedder.sync_record(user_id, "meeting", record):
            logger.info("meeting memory vectors synced project=%s", pid)
    except Exception:  # noqa: BLE001
        logger.warning("meeting memory vector sync failed, skipped", exc_info=True)


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
        core = project_core(anchor) or anchor
        if core and is_strong_anchor(core) and core not in anchors:
            anchors.append(core)
    project["anchors"] = anchors[:24]
    aliases = [str(x) for x in (project.get("aliases") or []) if str(x).strip()]
    title = (fact.title or "").strip()
    core = pick_project_name(fact) or project_core(title)
    current_name = str(project.get("name") or "")
    if core and core not in aliases and core != current_name:
        if is_weak_project_name(current_name) and not is_weak_project_name(core):
            if current_name and current_name not in aliases:
                aliases.append(current_name)
            project["name"] = core
        else:
            aliases.append(core)
    if title and title not in aliases and title != project.get("name"):
        aliases.append(title)
    project["aliases"] = list(dict.fromkeys(aliases))[:12]
    project.setdefault("negative_anchors", [])
    project["updated_at"] = stamp


def build_line_extra(
    state: dict[str, Any],
    line_name: str,
    *,
    line_extra: dict[str, str] | None = None,
) -> InjectResult:
    """Build memory context after meeting_understanding and before line generation."""
    empty = InjectResult()
    if line_name not in {"minutes", "minutes_styles"}:
        return empty
    meta = decode_meta(line_extra)
    if not meta.get("user_id"):
        return empty
    project_root = Path(meta.get("project_root") or ".")
    user_id = meta["user_id"]
    transcript = str(state.get("transcript") or "")
    fact = extract_meeting_fact(
        state.get("meeting_understanding") or {},
        transcript,
        request_id=meta.get("request_id") or "",
        time=meta.get("time") or "",
    )
    registry = load_registry(project_root, user_id)
    meetings = list_meetings(project_root, user_id)
    bind = resolve_bind(registry, fact, meta.get("project") or "", user_id, meetings)
    warning = bind.warning or ""
    if not bind.is_bound:
        return InjectResult(bind=bind, warning=warning)
    project = _project_entry(registry, bind.project_id, meta.get("project") or "")
    state_doc = load_state(project_root, user_id, bind.project_id)
    if not state_doc:
        return InjectResult(bind=bind, warning=warning)
    state_doc = backfill_meeting_titles(state_doc, meetings)
    context, comparison = build_memory_context(
        project_id=bind.project_id,
        project=project,
        state=state_doc,
        bind=bind,
        meetings=meetings,
        current_fact=fact,
    )
    return InjectResult(
        context=context,
        bind=bind,
        comparison=comparison,
        warning=warning,
    )


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
    bind: BindResult | dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Persist meeting fact. Headline is display-only and must not rebind identity."""
    if not (user_id or "").strip():
        return None
    try:
        fact = extract_meeting_fact(
            understanding or {},
            transcript,
            request_id=request_id,
            time=meeting_time or "",
        )
        registry = load_registry(project_root, user_id)
        meetings = list_meetings(project_root, user_id)
        resolved: BindResult
        if isinstance(bind, BindResult) and bind.project_id:
            resolved = bind
        elif isinstance(bind, dict) and bind.get("project_id"):
            resolved = BindResult(
                project_id=str(bind.get("project_id") or ""),
                mode=str(bind.get("mode") or "auto"),
                confidence=str(bind.get("confidence") or "low"),
                evidence=list(bind.get("evidence") or []),
                warning=str(bind.get("warning") or ""),
                core_name=str(bind.get("core_name") or ""),
            )
        else:
            resolved = resolve_bind(registry, fact, project or "", user_id, meetings)
        headline = _report_headline(reports, "minutes") or _report_headline(reports, "minutes_styles")
        if headline:
            fact.title = headline
        fact.project_id = resolved.project_id if resolved.is_bound else ""
        fact.bind = resolved.as_dict()
        meeting = fact.as_dict()
        rendered = _report_text(reports, "minutes") or _report_text(reports, "minutes_styles")
        if rendered:
            meeting["rendered_preview"] = rendered[:1000]
        state_doc: dict[str, Any] | None = None
        project_entry: dict[str, Any] = {}
        if resolved.is_bound:
            pid = resolved.project_id
            display_name = (
                (project or "").strip()
                or resolved.core_name
                or pick_project_name(fact)
                or pid
            )
            project_entry = _project_entry(registry, pid, display_name)
            _merge_registry_project(project_entry, fact, fact.time)
            append_or_replace_meeting(project_root, user_id, meeting)
            all_meetings = list_meetings(project_root, user_id)
            state_doc = rebuild_state(
                all_meetings,
                pid,
                project_name=str(project_entry.get("name") or display_name or pid),
            )
            save_state(project_root, user_id, pid, state_doc)
            save_registry(project_root, user_id, registry)
            _sync_meeting_vectors(
                project_root, user_id, pid, project_entry, state_doc
            )
        else:
            append_or_replace_meeting(project_root, user_id, meeting)
        return meeting
    except Exception:
        logger.warning("meeting memory v2 persist failed", exc_info=True)
        return None


__all__ = [
    "InjectResult",
    "META_KEY",
    "build_line_extra",
    "decode_meta",
    "encode_meta",
    "persist_after_run",
    "resolve_bind",
]
