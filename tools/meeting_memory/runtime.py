"""Runtime facade for meeting memory v2."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .bind import BindResult, bind_meeting
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

# ── 语义归属兜底（方案 B，meeting 版）────────────────────────
# bind_meeting 是纯规则（名称包含/LCSubstring/anchors）；项目标题换说法时
# 规则零重叠 → auto_create 建出重复项目、历史记忆断裂。此处用记忆向量库
# （data/{user_id}/memory/chromadb，与 notes 域共用实例、domain="meeting" 区分）
# 做兜底：唯一高分离候选才绑定（与 tools/memory/resolve.py 同款保守门）。
# embedding/chroma 不可用或异常 → 返回 None 维持规则结果，绝不阻断主流程。
def _semantic_bind_fallback(fact: MeetingFact, user_id: str) -> BindResult | None:
    """规则未命中（auto_create）时的语义归属兜底。"""
    if not (user_id or "").strip():
        return None
    try:
        from tools.memory.embed import MEMORY_EMBED_MIN_SCORE, get_embedder

        embedder = get_embedder(user_id=user_id)
    except Exception:  # noqa: BLE001 - 语义层不可用降级规则
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
        logger.warning("会议记忆语义归属查询失败，降级规则绑定", exc_info=True)
        return None
    if not cands:
        return None
    top = cands[0]
    if len(cands) > 1 and float(cands[1].get("score") or 0.0) >= MEMORY_EMBED_MIN_SCORE:
        return None  # 多候选并列 → 证据不足，维持 auto_create（防错绑）
    logger.info(
        "会议记忆语义兜底：标题 %r 规则零重叠，按向量相似度 %.2f 绑定历史项目 %s",
        getattr(fact, "title", ""), float(top.get("score") or 0.0),
        str(top.get("project_id") or ""),
    )
    return BindResult(
        project_id=str(top.get("project_id") or ""),
        mode="auto",
        confidence="high",
        evidence=[f"semantic:{float(top.get('score') or 0.0):.2f}"],
    )


def _resolve_bind(registry: dict[str, Any], fact: MeetingFact, explicit_project: str, user_id: str) -> BindResult:
    """规则绑定 + 语义兜底的统一入口。

    规则命中（explicit / anchor / clear-winner / medium）维持原判；
    仅在规则零重叠（auto_create）时尝试语义兜底——救回标题变体的历史项目。"""
    bind = bind_meeting(registry, fact, explicit_project=explicit_project)
    if bind.mode == "auto_create":
        fallback = _semantic_bind_fallback(fact, user_id)
        if fallback is not None:
            return fallback
    return bind


def _meeting_embed_record(
    project_root: Path,
    user_id: str,
    pid: str,
    project: dict[str, Any],
    state_doc: dict[str, Any],
    meetings: list[dict[str, Any]],
) -> dict[str, Any]:
    """把 meeting_memory v2 的事实结构适配成 tools/memory/embed.py 的档案形状。

    复用 sync_record 的"删旧+档案级+摘录级"幂等写入；字段映射：
    v2 state.open_items/risks/decisions → meeting.open_items[].item /
    meeting.decisions[].decision / sessions[].open_questions|risks。"""
    rows = [
        m for m in (meetings or [])
        if str(m.get("project_id") or "") == pid
    ]
    rows.sort(key=lambda m: str(m.get("time") or ""))
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
                for i in (state_doc.get("open_items") or [])
                if isinstance(i, dict) and str(i.get("text") or "").strip()
            ][:6],
            "decisions": [
                {"decision": str(i.get("text") or "")}
                for i in (state_doc.get("decisions") or [])
                if isinstance(i, dict) and str(i.get("text") or "").strip()
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
    """persist 写回后把会议记忆同步进记忆向量库（domain="meeting"）。

    档案可随时从 json 本体重建；同步失败不阻断主流程。"""
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
            logger.info(
                "会议记忆向量已同步：%s（domain=meeting，档案+摘录）", pid
            )
    except Exception:  # noqa: BLE001 - 向量同步异常不阻断写回
        logger.warning("会议记忆向量同步异常，跳过", exc_info=True)



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
    bind = _resolve_bind(registry, fact, meta.get("project") or "", user_id)
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
        bind = _resolve_bind(registry, fact, project or "", user_id)
        fact.project_id = bind.project_id if bind.confidence == "high" else ""
        fact.bind = bind.as_dict()
        meeting = fact.as_dict()
        rendered = _report_text(reports, "minutes") or _report_text(reports, "minutes_styles")
        if rendered:
            meeting["rendered_preview"] = rendered[:1000]
        state_doc: dict[str, Any] | None = None
        project_entry: dict[str, Any] = {}
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
        if state_doc is not None:
            _sync_meeting_vectors(
                project_root, user_id, bind.project_id, project_entry, state_doc
            )
        return meeting
    except Exception:
        logger.warning("会议记忆 v2 写回失败", exc_info=True)
        return None


__all__ = ["META_KEY", "build_line_extra", "decode_meta", "encode_meta", "persist_after_run"]
