"""Filesystem store for the meeting memory v2 layout."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.memory.store import safe_id


def meeting_root(project_root: Path, user_id: str) -> Path:
    root = project_root / "data" / safe_id(user_id) / "meeting"
    root.mkdir(parents=True, exist_ok=True)
    (root / "states").mkdir(parents=True, exist_ok=True)
    return root


def registry_path(project_root: Path, user_id: str) -> Path:
    return meeting_root(project_root, user_id) / "registry.json"


def meetings_path(project_root: Path, user_id: str) -> Path:
    return meeting_root(project_root, user_id) / "meetings.jsonl"


def state_path(project_root: Path, user_id: str, project_id: str) -> Path:
    return meeting_root(project_root, user_id) / "states" / f"{safe_id(project_id)}.json"


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else dict(default)
    except Exception:
        return dict(default)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_registry(project_root: Path, user_id: str) -> dict[str, Any]:
    data = _read_json(registry_path(project_root, user_id), {"projects": {}})
    if not isinstance(data.get("projects"), dict):
        data["projects"] = {}
    return data


def save_registry(project_root: Path, user_id: str, registry: dict[str, Any]) -> None:
    registry.setdefault("projects", {})
    _write_json(registry_path(project_root, user_id), registry)


def load_state(project_root: Path, user_id: str, project_id: str) -> dict[str, Any]:
    return _read_json(state_path(project_root, user_id, project_id), {})


def save_state(project_root: Path, user_id: str, project_id: str, state: dict[str, Any]) -> None:
    _write_json(state_path(project_root, user_id, project_id), state)


def list_meetings(project_root: Path, user_id: str) -> list[dict[str, Any]]:
    path = meetings_path(project_root, user_id)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict) and item.get("meeting_id"):
            rows.append(item)
    return rows


def append_or_replace_meeting(project_root: Path, user_id: str, meeting: dict[str, Any]) -> None:
    """Append a meeting fact, replacing an existing row with the same meeting_id."""
    if not meeting.get("meeting_id"):
        return
    path = meetings_path(project_root, user_id)
    rows = [
        item for item in list_meetings(project_root, user_id)
        if str(item.get("meeting_id")) != str(meeting.get("meeting_id"))
    ]
    rows.append(meeting)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


__all__ = [
    "append_or_replace_meeting",
    "list_meetings",
    "load_registry",
    "load_state",
    "meeting_root",
    "meetings_path",
    "registry_path",
    "save_registry",
    "save_state",
    "state_path",
]
