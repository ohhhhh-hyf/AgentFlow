"""按知识库集合持久化知识目录，供下次增量更新。"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from tools.knowledge.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

CATALOG_DIR = PROJECT_ROOT / "data" / "knowledge" / "catalogs"  # 兼容旧路径（无 user 场景）


def _safe_name(collection: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", (collection or "default").strip()) or "default"
    return name[:120]


def _catalog_dir_for(collection: str) -> Path:
    """catalog 目录按 user 顶层隔离：``data/{user_id}/knowledge/catalogs``。

    collection 形如 ``{user_id}__{subject}``（resolve_collection 产出）；
    无 user 段时回退旧统一目录（兼容）。
    """
    head = (collection or "").split("__", 1)[0]
    if not head or head == "default":
        return CATALOG_DIR
    from tools.memory.store import safe_id

    return PROJECT_ROOT / "data" / safe_id(head) / "knowledge" / "catalogs"


def catalog_path(collection: str) -> Path:
    return _catalog_dir_for(collection) / f"{_safe_name(collection)}.json"


def load_catalog(collection: str) -> dict[str, Any] | None:
    path = catalog_path(collection)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not (data.get("chapters") or []):
        return None
    return data


def save_catalog(collection: str, draft: dict[str, Any]) -> Path:
    path = catalog_path(collection)
    path.parent.mkdir(parents=True, exist_ok=True)
    chapters = draft.get("chapters") or []
    if not chapters:
        if path.exists():
            logger.warning("拒绝用空目录覆盖已有文件：%s", path)
            return path
        logger.warning("目录草稿没有章节，跳过写入：%s", collection)
        return path
    payload = {
        "course": draft.get("course") or "",
        "version": draft.get("version") or "1",
        "mode": draft.get("mode") or "build",
        "chapters": draft.get("chapters") or [],
        "unmatched_content": draft.get("unmatched_content") or [],
        "uncertain_nodes": draft.get("uncertain_nodes") or [],
        "added_chapters": draft.get("added_chapters") or [],
        "added_topics": draft.get("added_topics") or [],
        "added_knowledge_points": draft.get("added_knowledge_points") or [],
        "updated_knowledge_points": draft.get("updated_knowledge_points") or [],
        "merged_nodes": draft.get("merged_nodes") or [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
