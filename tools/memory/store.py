"""记忆落盘：data/memory/records/{domain}/{user_id}/projects/{project_id}/record.json。

与向量索引（data/memory/chromadb/）同目录树分工：
- records/ = 事实本体（状态：决策/未决/sessions 全文，人可读、可备份）
- chromadb/ = 检索索引（档案级+摘录级向量，可从 records 重建）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_id(name: str) -> str:
    cleaned = "".join(
        ch if ch.isalnum() or ch in "-_" else "_"
        for ch in (name or "").strip()
    )[:80] or "default"
    if cleaned.upper() in _WINDOWS_RESERVED:
        cleaned = f"{cleaned}_"
    return cleaned


def user_dir(project_root: Path, domain: str, user_id: str) -> Path:
    """用户顶层隔离：``data/{user_id}/memory/records/{domain}``。"""
    out = project_root / "data" / safe_id(user_id) / "memory" / "records" / domain
    out.mkdir(parents=True, exist_ok=True)
    return out


def record_dir(project_root: Path, domain: str, user_id: str, project_id: str) -> Path:
    out = user_dir(project_root, domain, user_id) / "projects" / safe_id(project_id)
    out.mkdir(parents=True, exist_ok=True)
    return out


def record_path(project_root: Path, domain: str, user_id: str, project_id: str) -> Path:
    return record_dir(project_root, domain, user_id, project_id) / "record.json"


def history_path(project_root: Path, domain: str, user_id: str, project_id: str) -> Path:
    return record_dir(project_root, domain, user_id, project_id) / "history.jsonl"


def _identity_fields(user_id: str, project_id: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "project_id": project_id,
        "updated_at": "",
        "run_count": 0,
        "display_name": "",
        "project_key": "",
        "name_aliases": [],
        "entities": [],
        # 关联增强字段（供向量身份文本 / 记忆关联排序）
        "key_terms": [],
        "recent_topics": [],
        "active_summary": "",
        "last_meeting_at": "",
        # 变更事件日志（状态跟踪：决策新增/未决开闭/风险变化，可溯源到场次）
        "events": [],
    }


def empty_record(
    user_id: str,
    project_id: str,
    domain: str = "",
) -> dict[str, Any]:
    """按域建空档：会议只有 meeting，笔记只有 notes + graph。"""
    rec = _identity_fields(user_id, project_id)
    if (domain or "").strip() == "notes":
        rec["subject"] = ""
        rec["notes"] = {
            "subject": "",
            "key_terms": [],
            "sessions": [],
        }
        rec["graph"] = {
            "title": "",
            "nodes": [],
            "edges": [],
        }
        return rec
    rec["meeting"] = {
        "purpose": "",
        "summary": "",
        "topics": [],
        "open_items": [],
        "closed_items": [],
        "decisions": [],
        "risks": [],
        "sessions": [],
    }
    return rec


def shape_record(record: dict[str, Any], domain: str) -> dict[str, Any]:
    """落盘前去掉跨域空壳，旧档案下次写回时也会收干净。"""
    rec = dict(record or {})
    if (domain or "").strip() == "notes":
        rec.pop("meeting", None)
        return rec
    rec.pop("notes", None)
    rec.pop("graph", None)
    rec.pop("subject", None)
    return rec


def load_record(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("project_id"):
            return data
    except Exception:  # noqa: BLE001 - 损坏不影响主流程
        pass
    return {}


def save_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_history(path: Path, event: dict[str, Any]) -> None:
    event = dict(event or {})
    event.setdefault("recorded_at", datetime.now().isoformat(timespec="seconds"))
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def list_records(project_root: Path, domain: str, user_id: str) -> list[dict[str, Any]]:
    root = user_dir(project_root, domain, user_id) / "projects"
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        rec = load_record(folder / "record.json")
        if rec:
            rows.append(rec)
    return rows


def next_project_id(existing: list[dict[str, Any]]) -> str:
    taken = {str(r.get("project_id") or "") for r in existing}
    n = 1
    while f"p{n}" in taken:
        n += 1
    return f"p{n}"


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
