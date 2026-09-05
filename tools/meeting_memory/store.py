"""Filesystem store for the meeting memory v2 layout (统一布局).

minutes 线的记忆回放数据：``data/{uid}/memory/minutes/`` ——
- registry.json：项目注册表（名称/别名/anchors）
- meetings.jsonl：每场会议事实全量行
- states/{project_id}.json：项目状态（延续事项/风险/决策）

目录按任务线名（meeting_root 的 ``line`` 参数）：minutes 与 minutes_styles
当前共享同一份项目记忆（同一场会议的两种输出、同一套项目状态）；将来
styles 独立记忆时传入 line="minutes_styles" 即获得独立目录。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.memory.store import safe_id


def meeting_root(project_root: Path, user_id: str, line: str = "minutes") -> Path:
    root = project_root / "data" / safe_id(user_id) / "memory" / safe_id(line)
    root.mkdir(parents=True, exist_ok=True)
    (root / "states").mkdir(parents=True, exist_ok=True)
    return root


def registry_path(project_root: Path, user_id: str, line: str = "minutes") -> Path:
    return meeting_root(project_root, user_id, line) / "registry.json"


def meetings_path(project_root: Path, user_id: str, line: str = "minutes") -> Path:
    return meeting_root(project_root, user_id, line) / "meetings.jsonl"


def state_path(
    project_root: Path, user_id: str, project_id: str, line: str = "minutes"
) -> Path:
    return meeting_root(project_root, user_id, line) / "states" / f"{safe_id(project_id)}.json"


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else dict(default)
    except Exception:
        return dict(default)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_registry(project_root: Path, user_id: str, line: str = "minutes") -> dict[str, Any]:
    data = _read_json(registry_path(project_root, user_id, line), {"projects": {}})
    if not isinstance(data.get("projects"), dict):
        data["projects"] = {}
    return data


def save_registry(
    project_root: Path, user_id: str, registry: dict[str, Any], line: str = "minutes"
) -> None:
    registry.setdefault("projects", {})
    _write_json(registry_path(project_root, user_id, line), registry)


def load_state(
    project_root: Path, user_id: str, project_id: str, line: str = "minutes"
) -> dict[str, Any]:
    return _read_json(state_path(project_root, user_id, project_id, line), {})


def save_state(
    project_root: Path, user_id: str, project_id: str,
    state: dict[str, Any], line: str = "minutes",
) -> None:
    _write_json(state_path(project_root, user_id, project_id, line), state)


def list_meetings(project_root: Path, user_id: str, line: str = "minutes") -> list[dict[str, Any]]:
    path = meetings_path(project_root, user_id, line)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line_text in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line_text)
        except Exception:
            continue
        if isinstance(item, dict) and item.get("meeting_id"):
            rows.append(item)
    return rows


def append_or_replace_meeting(
    project_root: Path, user_id: str, meeting: dict[str, Any], line: str = "minutes"
) -> None:
    """Append a meeting fact, replacing an existing row with the same meeting_id."""
    if not meeting.get("meeting_id"):
        return
    path = meetings_path(project_root, user_id, line)
    rows = [
        item for item in list_meetings(project_root, user_id, line)
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
