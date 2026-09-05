"""按知识库集合持久化知识目录，供下次增量更新。

命名规则（v3）：
- 目录按 user 顶层隔离 + 按 subject 分目录：``data/{user_id}/knowledge/catalogs/{学科安全名}/``
- 文件名 = ``{时间戳}.json``（如 ``20260827_221500_123.json``），历史版本保留
- 增量更新：同一 user+subject 下次生成时，取该 subject 目录下时间最近的 json 作为基线
- 无 user 时回退旧统一目录 ``data/knowledge/catalogs/``（兼容）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.knowledge.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

CATALOG_DIR = PROJECT_ROOT / "data" / "knowledge" / "catalogs"  # 兼容旧路径（无 user 场景）


def _subject_filename(subject: str) -> str:
    """学科 → 拼音目录名（无音调、小写、去空格），英文/数字原样保留。

    统一复用知识库层 ``subject_to_pinyin``（物理 → wuli），
    保证 catalog 目录与知识库 subject 维度一致。
    """
    from tools.knowledge.config import subject_to_pinyin

    return subject_to_pinyin(subject)


def catalog_dir_for(user_id: str = "") -> Path:
    """catalog 目录按 user 顶层隔离：``data/{user_id}/knowledge/catalogs``。"""
    uid = (user_id or "").strip()
    if not uid:
        return CATALOG_DIR
    from tools.memory.store import safe_id

    return PROJECT_ROOT / "data" / safe_id(uid) / "knowledge" / "catalogs"


def subject_dir_for(user_id: str = "", subject: str = "") -> Path:
    """按 subject 分目录：``catalogs/{学科安全名}/``。"""
    return catalog_dir_for(user_id) / _subject_filename(subject)


def latest_catalog_path(user_id: str = "", subject: str = "") -> Path | None:
    """该 user+subject 下时间最近的 catalog json（增量基线/checklist 默认源），无则 None。"""
    folder = subject_dir_for(user_id, subject)
    if not folder.is_dir():
        return None
    matches = sorted(
        folder.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def new_catalog_path(user_id: str = "", subject: str = "", stamp: str = "") -> Path:
    """本次生成的新 catalog 文件路径（纯时间戳命名，如 20260827_221500_123.json）。"""
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    return subject_dir_for(user_id, subject) / f"{stamp}.json"


def _ocr_output_stems(user_id: str, subject: str) -> list[str]:
    """Standard 会把原图 xx 存成 ocr/{subject}/xx.md，meta 则是 catalogs/xx_meta.json。"""
    from tools.memory.store import safe_id

    uid = (user_id or "").strip()
    if not uid:
        return []
    base = PROJECT_ROOT / "data" / safe_id(uid) / "ocr" / safe_id(subject)
    stems: list[str] = []
    seen: set[str] = set()
    folder = base
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
    """加载该 user+subject 下时间最近的 catalog（增量基线）；无则 None。"""
    path = latest_catalog_path(user_id, subject)
    return load_catalog_file(path) if path else None


def load_catalog_file(path: Path) -> dict[str, Any] | None:
    """按指定路径加载 catalog JSON（checklist 用 files 指定文件时调用）。"""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not (data.get("chapters") or []):
        return None
    return data


def save_catalog(user_id: str, subject: str, draft: dict[str, Any]) -> Path:
    """保存为新时间戳文件（历史版本保留；下次生成以时间最近者为基线）。"""
    path = new_catalog_path(user_id, subject)
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
