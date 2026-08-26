"""按知识库集合持久化知识目录，供下次增量更新。

命名规则（v2）：
- 目录按 user 顶层隔离：``data/{user_id}/knowledge/catalogs/``
- 文件名 = ``{学科安全名}_{md5(学科)[:8]}.json``：ASCII 可读部分 + 指纹，
  中文学科/特殊字符不再被抹平成同一下划线而互相覆盖（旧 ``user_id__subject`` 方案）。
- 无 user 时回退旧统一目录 ``data/knowledge/catalogs/``（兼容）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from tools.knowledge.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

CATALOG_DIR = PROJECT_ROOT / "data" / "knowledge" / "catalogs"  # 兼容旧路径（无 user 场景）


def _subject_filename(subject: str) -> str:
    """学科 → 安全文件名主体：ASCII 可读部分 + md5 指纹（防中文/特殊字符撞名）。

    例：``数学`` → ``subject_<md5前8位>``；``math`` → ``math_<md5前8位>``。
    指纹由原始学科字符串算出，不同学科（含同形不同码）必然不同文件名。
    """
    ascii_part = re.sub(r"[^a-zA-Z0-9._-]+", "_", (subject or "").strip())
    ascii_part = ascii_part.strip("._") or "subject"
    ascii_part = ascii_part[:60]
    digest = hashlib.md5((subject or "").encode("utf-8")).hexdigest()[:8]
    return f"{ascii_part}_{digest}"


def catalog_dir_for(user_id: str = "") -> Path:
    """catalog 目录按 user 顶层隔离：``data/{user_id}/knowledge/catalogs``。"""
    uid = (user_id or "").strip()
    if not uid:
        return CATALOG_DIR
    from tools.memory.store import safe_id

    return PROJECT_ROOT / "data" / safe_id(uid) / "knowledge" / "catalogs"


def catalog_path(user_id: str = "", subject: str = "") -> Path:
    return catalog_dir_for(user_id) / f"{_subject_filename(subject)}.json"


def _ocr_output_stems(user_id: str, subject: str) -> list[str]:
    """Standard 会把原图 xx 存成 ocr/{subject}/md/xx.md，meta 则是 catalogs/xx_meta.json。"""
    from tools.memory.store import safe_id

    uid = (user_id or "").strip()
    if not uid:
        return []
    base = PROJECT_ROOT / "data" / safe_id(uid) / "ocr" / safe_id(subject)
    stems: list[str] = []
    seen: set[str] = set()
    folder = base / "md"
    if folder.is_dir():
        for path in folder.iterdir():
            if not path.is_file() or path.suffix.lower() != ".md":
                continue
            stem = path.stem
            if stem and stem not in seen:
                seen.add(stem)
                stems.append(stem)
    return stems


def _meta_source_name(path: Path) -> str:
    name = path.name
    stem = name[: -len("_meta.json")] if name.endswith("_meta.json") else path.stem
    return f"{stem}.md"


def load_catalog_metas(user_id: str = "", subject: str = "", limit: int = 50) -> list[dict[str, Any]]:
    folder = catalog_dir_for(user_id)
    if not folder.exists():
        return []

    seen: set[str] = set()
    paths: list[Path] = []

    def add(path: Path) -> None:
        if not path.is_file():
            return
        key = str(path).lower()
        if key in seen:
            return
        seen.add(key)
        paths.append(path)

    for stem in _ocr_output_stems(user_id, subject):
        add(folder / f"{stem}_meta.json")
    prefix = _subject_filename(subject)
    for path in folder.glob(f"{prefix}_*_meta.json"):
        add(path)

    paths.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    metas: list[dict[str, Any]] = []
    for path in paths:
        if len(metas) >= limit:
            break
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            payload = dict(data)
            payload["source"] = _meta_source_name(path)
            metas.append(payload)
    return metas


def load_catalog(user_id: str = "", subject: str = "") -> dict[str, Any] | None:
    path = catalog_path(user_id, subject)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not (data.get("chapters") or []):
        return None
    return data


def save_catalog(user_id: str, subject: str, draft: dict[str, Any]) -> Path:
    path = catalog_path(user_id, subject)
    path.parent.mkdir(parents=True, exist_ok=True)
    chapters = draft.get("chapters") or []
    if not chapters:
        if path.exists():
            logger.warning("拒绝用空目录覆盖已有文件：%s", path)
            return path
        logger.warning("目录草稿没有章节，跳过写入：%s", path)
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
