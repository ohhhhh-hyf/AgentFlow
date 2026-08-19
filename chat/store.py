# -*- coding: utf-8 -*-
"""chat 会话存储：按用户顶层物理隔离。

``data/{user_id}/chat/sessions/{session_id}/``
├── history.jsonl   # 逐行消息（{"role": "user"|"assistant", "content"}）
└── facts.json      # 会话内提取的已知用户信息（如 {"name": "用户姓名"}）

任何读写异常都吞掉并记日志——聊天会话不因落盘故障中断。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def chat_dir(project_root: Path, user_id: str) -> Path:
    """chat 域目录：``data/{user_id}/chat``。"""
    from tools.memory.store import safe_id

    out = project_root / "data" / safe_id(user_id) / "chat"
    out.mkdir(parents=True, exist_ok=True)
    return out


def session_dir(project_root: Path, user_id: str, session_id: str) -> Path:
    """单个会话目录：``data/{user_id}/chat/{session_id}``。"""
    from tools.memory.store import safe_id

    out = chat_dir(project_root, user_id) / safe_id(session_id or "default")
    out.mkdir(parents=True, exist_ok=True)
    return out


def history_path(project_root: Path, user_id: str, session_id: str) -> Path:
    return session_dir(project_root, user_id, session_id) / "history.jsonl"


def facts_path(project_root: Path, user_id: str, session_id: str) -> Path:
    return session_dir(project_root, user_id, session_id) / "facts.json"


def load_history(path: Path) -> list[dict[str, str]]:
    """读取会话历史（损坏/缺文件返回空）。"""
    try:
        if not path.is_file():
            return []
        rows: list[dict[str, str]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("role") and row.get("content"):
                rows.append({"role": str(row["role"]), "content": str(row["content"])})
        return rows
    except OSError as exc:  # pragma: no cover
        logger.warning("读取会话历史失败：%s", exc)
        return []


def append_turn(path: Path, role: str, content: str) -> None:
    """追加一条消息。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"role": role, "content": content}, ensure_ascii=False) + "\n")
    except OSError as exc:  # pragma: no cover
        logger.warning("追加会话历史失败：%s", exc)


def load_facts(path: Path) -> dict[str, Any]:
    """读取已知用户信息（缺文件/损坏返回空）。"""
    try:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover
        logger.warning("读取会话 facts 失败：%s", exc)
        return {}


def save_facts(path: Path, facts: dict[str, Any]) -> None:
    """落盘已知用户信息。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as exc:  # pragma: no cover
        logger.warning("保存会话 facts 失败：%s", exc)
