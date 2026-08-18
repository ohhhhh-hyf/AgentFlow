"""从知识库抽出资料骨架 / 笔记标题，拼给 catalog agent。"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from tools.knowledge.cite import open_knowledge
from tools.knowledge.source_role import ROLE_MATERIAL, ROLE_NOTES, ROLE_TEACHER, classify_source_role
from tools.knowledge.tool import collection_for
from .store import load_catalog


def subject_from_context(text: str) -> str:
    m = re.search(r"【学科/课程】\s*([^【】\n]+)", text or "")
    return m.group(1).strip() if m else ""


def user_id_from_context(text: str) -> str:
    m = re.search(r"【用户ID】\s*([^【】\n]+)", text or "")
    return m.group(1).strip() if m else ""


def resolve_collection(user_id: str = "", subject: str = "") -> str:
    preferred = collection_for(user_id=user_id, subject=subject)
    kb = open_knowledge()
    if kb is None:
        return preferred
    try:
        if kb.list_files(preferred):
            return preferred
    except Exception:
        pass
    if subject:
        try:
            cols = kb.list_collections() or []
        except Exception:
            cols = []
        names = [c.get("name") if isinstance(c, dict) else str(c) for c in cols]
        for name in names:
            if name == subject or str(name).endswith("__" + subject):
                return str(name)
    return preferred


def _chunk_role(meta: dict[str, Any], source: str) -> str:
    role = str(meta.get("role") or "").strip()
    if role in {ROLE_MATERIAL, ROLE_NOTES, ROLE_TEACHER}:
        return role
    return classify_source_role(source)


def _brief_chunks(kb: Any, collection: str) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {
        ROLE_MATERIAL: [],
        ROLE_NOTES: [],
        ROLE_TEACHER: [],
    }
    try:
        chunks = kb.list_chunks(collection) or []
    except Exception:
        return grouped
    seen: set[tuple[str, str, str]] = set()
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        meta = chunk.get("metadata") or {}
        source = str(meta.get("source") or "")
        role = _chunk_role(meta, source)
        chapter = str(meta.get("chapter") or "")
        topic = str(meta.get("topic") or "")
        heading = str(meta.get("heading") or "")
        key = (source, chapter, heading or topic)
        if key in seen:
            continue
        seen.add(key)
        grouped.setdefault(role, []).append(
            {
                "source": source,
                "chapter": chapter,
                "topic": topic,
                "heading": heading,
            }
        )
    return grouped


def _compact_existing(catalog: dict[str, Any]) -> str:
    lines = [
        f"课程：{catalog.get('course') or ''}",
        f"版本：{catalog.get('version') or '1'}",
    ]
    for chapter in catalog.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        lines.append(f"- [{chapter.get('id') or ''}] 章 {chapter.get('name') or ''}")
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            lines.append(f"  - [{topic.get('id') or ''}] 主题 {topic.get('name') or ''}")
            for point in topic.get("knowledge_points") or []:
                if not isinstance(point, dict):
                    continue
                items = "、".join(
                    str(x) for x in (point.get("knowledge_items") or []) if str(x).strip()
                )
                aliases = "、".join(str(x) for x in (point.get("aliases") or []) if str(x).strip())
                extra = f" 别名={aliases}" if aliases else ""
                role = str(point.get("learning_role") or "").strip() or "缺"
                practice = "、".join(str(x) for x in (point.get("practice_type") or []) if str(x).strip()) or "缺"
                criteria = "、".join(str(x) for x in (point.get("completion_criteria") or []) if str(x).strip()) or "缺"
                risks = "、".join(str(x) for x in (point.get("risk_tags") or []) if str(x).strip()) or "缺"
                lines.append(
                    f"    - [{point.get('id') or ''}] {point.get('name') or ''} "
                    f"items=[{items}]{extra} role={role} practice=[{practice}] "
                    f"criteria=[{criteria}] risk=[{risks}]"
                )
    return "\n".join(lines)


def known_source_documents(catalog: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for chapter in catalog.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for name in chapter.get("source_documents") or []:
            if str(name).strip():
                found.add(str(name).strip())
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for point in topic.get("knowledge_points") or []:
                if not isinstance(point, dict):
                    continue
                for name in point.get("source_documents") or []:
                    if str(name).strip():
                        found.add(str(name).strip())
    return found


def build_catalog_briefing(shared_context: str) -> str:
    """给 LLM 的压缩输入：历史目录 + 骨架标题 + 老师原文。"""
    user_id = user_id_from_context(shared_context)
    subject = subject_from_context(shared_context)
    collection = resolve_collection(user_id=user_id, subject=subject)
    existing = load_catalog(collection)
    mode = "incremental_update" if existing else "build"
    kb = open_knowledge()
    parts = [
        "【任务】生成或增量更新课程知识目录，不要写复习建议。",
        f"【学科/课程】{subject or '未标注'}",
        f"【知识库集合】{collection}",
        f"【mode】{mode}",
    ]
    if existing:
        parts.append("【已有目录】必须复用下列 ID，禁止重建旧章。缺 role/practice/criteria/risk 的 KP 只补这四个字段。")
        parts.append(_compact_existing(existing))
        known = known_source_documents(existing)
        if known:
            parts.append("【已入库并已编目的文件】" + "、".join(sorted(known)))
    else:
        parts.append("【已有目录】无，按首次 build 生成完整树。")
    if kb is None:
        parts.append("【知识库】当前不可用，只根据下面老师文本建目录。")
    else:
        grouped = _brief_chunks(kb, collection)
        materials = grouped.get(ROLE_MATERIAL) or []
        notes = grouped.get(ROLE_NOTES) or []
        if materials:
            parts.append("【资料骨架】（课程资料，优先用这些标题建树）")
            by_file: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in materials:
                by_file[row["source"]].append(row)
            known = known_source_documents(existing) if existing else set()
            for fname, rows in list(by_file.items())[:20]:
                tag = "（已在目录中）" if fname in known else "（新资料/待匹配）"
                parts.append(f"- 文件 {fname} {tag}")
                for row in rows[:40]:
                    path = " / ".join(
                        x for x in (row.get("chapter"), row.get("topic"), row.get("heading")) if x
                    )
                    if path:
                        parts.append(f"  · {path}")
        else:
            parts.append("【资料骨架】库中还没有课件/讲义标题，请尽量从笔记和老师文本归纳，但不要编章名。")
        if notes:
            parts.append("【学生笔记标题】（只用来标覆盖、补知识项）")
            by_file = defaultdict(list)
            for row in notes:
                by_file[row["source"]].append(row)
            for fname, rows in list(by_file.items())[:8]:
                heads = [row.get("heading") or row.get("topic") or row.get("chapter") for row in rows[:30]]
                heads = [h for h in heads if h]
                parts.append(f"- {fname}：{'；'.join(heads[:20])}")
        else:
            parts.append("【学生笔记标题】未识别到笔记角色文件，note_coverage 多为 none。")

    teacher = _teacher_text(shared_context)
    if teacher:
        parts.append("【老师划重点原文】")
        parts.append(teacher[:6000])
    else:
        parts.append("【老师划重点原文】无。teacher_emphasis 全部填 0，不要假装老师点过。")
    return "\n".join(parts)


def _teacher_text(shared_context: str) -> str:
    raw = shared_context or ""
    for marker in ("原文（最高事实来源）：", "原文："):
        if marker in raw:
            body = raw.split(marker, 1)[1]
            for stop in ("\n\n用户画像：", "\n\n已审核", "\n\n【"):
                if stop in body:
                    body = body.split(stop, 1)[0]
            return body.strip()
    # 共享上下文里若只是任务说明 + 老师文本，去掉标记行
    lines = []
    for line in raw.splitlines():
        if line.startswith("【") and line.endswith("】"):
            continue
        if line.startswith("【用户ID】") or line.startswith("【学科/课程】"):
            continue
        lines.append(line)
    text = "\n".join(lines).strip()
    if text.startswith("根据已入库资料生成知识目录"):
        return ""
    return text
