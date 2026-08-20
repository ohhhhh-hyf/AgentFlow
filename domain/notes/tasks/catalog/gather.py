"""从知识库抽出资料骨架 / 笔记标题，拼给 catalog agent。"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from tools.knowledge.cite import open_knowledge
from tools.knowledge.source_role import ROLE_MATERIAL, ROLE_NOTES, ROLE_TEACHER, classify_source_role
from .store import load_catalog

# briefing 中知识块/笔记标题的总量上限：骨架已够建树，超出截断避免输入过大拖慢 LLM
_MAX_BRIEF_TITLES = 400


def subject_from_context(text: str) -> str:
    m = re.search(r"【学科/课程】\s*([^【】\n]+)", text or "")
    return m.group(1).strip() if m else ""


def user_id_from_context(text: str) -> str:
    m = re.search(r"【用户ID】\s*([^【】\n]+)", text or "")
    return m.group(1).strip() if m else ""


def _understanding_from_context(text: str) -> dict[str, Any]:
    """从共享上下文提取「notes理解」JSON（缺失/损坏时返回空）。

    笔记理解是 catalog 建树的结构化锚点：让目录基于一次稳定的理解
    生成，而不是每次直接从原始知识块自由组织。
    """
    marker = "notes理解："
    if marker not in (text or ""):
        return {}
    tail = (text or "").split(marker, 1)[1]
    start = tail.find("{")
    if start < 0:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(tail[start:])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _chunk_role(meta: dict[str, Any], source: str) -> str:
    role = str(meta.get("role") or "").strip()
    if role in {ROLE_MATERIAL, ROLE_NOTES, ROLE_TEACHER}:
        return role
    return classify_source_role(source)


def _brief_chunks(
    kb: Any, user_id: str = "", subject: str = ""
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {
        ROLE_MATERIAL: [],
        ROLE_NOTES: [],
        ROLE_TEACHER: [],
    }
    try:
        chunks = kb.list_chunks(user_id=user_id, subject=subject) or []
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
    # 确定性排序：知识块在 briefing 中的顺序必须恒定，
    # 否则 LLM 每次读到的文本排列不同，目录输出会随库顺序波动
    for role in grouped:
        grouped[role].sort(
            key=lambda r: (
                str(r.get("source") or ""),
                str(r.get("chapter") or ""),
                str(r.get("heading") or r.get("topic") or ""),
            )
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
                missing = [
                    f
                    for f in ("practice_type", "completion_criteria", "learning_role", "risk_tags")
                    if not (point.get(f) or [])
                ]
                mark = f"（缺字段：{'、'.join(missing)}）" if missing else ""
                lines.append(
                    f"      - [{point.get('id') or ''}] {point.get('name') or ''}{mark}"
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
    existing = load_catalog(user_id=user_id, subject=subject)
    mode = "incremental_update" if existing else "build"
    kb = open_knowledge(user_id=user_id)
    parts = [
        "【任务】生成或增量更新课程知识目录，不要写复习建议。",
        f"【学科/课程】{subject or '未标注'}",
        f"【知识库集合】{user_id or ''}__{subject or ''}",
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
    understanding = _understanding_from_context(shared_context)
    if understanding:
        parts.append(
            "【笔记理解】（只用于锚定章节/主题的顺序与命名，避免结构漂移；"
            "每个主题下的知识要点 KP 必须依据【资料骨架】与知识块细分，"
            "一个主题下 2-6 个 KP，禁止把理解的单个 section 标题直接当整章/整主题而不拆分）\n"
            + json.dumps(understanding, ensure_ascii=False)
        )
    if kb is None:
        parts.append("【知识库】当前不可用，只根据下面老师文本建目录。")
    else:
        grouped = _brief_chunks(kb, user_id, subject)
        materials = grouped.get(ROLE_MATERIAL) or []
        notes = grouped.get(ROLE_NOTES) or []

        def _titled(rows: list[dict]) -> list[dict]:
            return [
                r for r in rows
                if r.get("heading") or r.get("topic") or r.get("chapter")
            ]

        material_titled = _titled(materials)
        if material_titled:
            # ① 课件/讲义有标题 → 主骨架
            parts.append("【资料骨架】（课程资料，优先用这些标题建树）")
            by_file: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in material_titled:
                by_file[row["source"]].append(row)
            known = known_source_documents(existing) if existing else set()
            emitted = 0
            for fname, rows in list(by_file.items())[:20]:
                if emitted >= _MAX_BRIEF_TITLES:
                    break
                tag = "（已在目录中）" if fname in known else "（新资料/待匹配）"
                parts.append(f"- 文件 {fname} {tag}")
                seen_paths: set[str] = set()
                for row in rows[:40]:
                    path = " / ".join(
                        x for x in (row.get("chapter"), row.get("topic"), row.get("heading")) if x
                    )
                    if path and path not in seen_paths:
                        seen_paths.add(path)
                        parts.append(f"  · {path}")
                        emitted += 1
            if emitted >= _MAX_BRIEF_TITLES:
                parts.append("  · …（骨架标题过多，已截断到 400 条）")
            # 课件有骨架时，笔记仍只标覆盖、补知识项
            if notes:
                parts.append("【学生笔记标题】（只用来标覆盖、补知识项）")
                by_file = defaultdict(list)
                for row in notes:
                    by_file[row["source"]].append(row)
                for fname, rows in list(by_file.items())[:8]:
                    if emitted >= _MAX_BRIEF_TITLES:
                        break
                    heads = [row.get("heading") or row.get("topic") or row.get("chapter") for row in rows[:30]]
                    heads = [h for h in heads if h]
                    parts.append(f"- {fname}：{'；'.join(heads[:20])}")
                    emitted += len(heads)
            else:
                parts.append("【学生笔记标题】未识别到笔记角色文件，note_coverage 多为 none。")
        elif notes:
            # ② 课件无标题但笔记有 → 笔记骨架（第二来源）
            parts.append("【资料骨架】库中课件/讲义没有可用标题，以下用学生笔记标题作为建树依据：")
            parts.append("【学生笔记骨架】（来自学生笔记；可据此归纳章节树，但不要编造课件没有的章名）")
            by_file = defaultdict(list)
            for row in notes:
                by_file[row["source"]].append(row)
            emitted = 0
            for fname, rows in list(by_file.items())[:8]:
                if emitted >= _MAX_BRIEF_TITLES:
                    break
                seen_paths = set()
                paths: list[str] = []
                for row in rows[:40]:
                    path = " / ".join(
                        x for x in (row.get("chapter"), row.get("topic"), row.get("heading")) if x
                    )
                    if path and path not in seen_paths:
                        seen_paths.add(path)
                        paths.append(path)
                if paths:
                    parts.append(f"- {fname}（学生笔记）")
                    for p in paths[:20]:
                        parts.append(f"  · {p}")
                        emitted += 1
            if emitted >= _MAX_BRIEF_TITLES:
                parts.append("  · …（骨架标题过多，已截断到 400 条）")
        else:
            # ③ 都缺 → 不编章名兜底
            parts.append("【资料骨架】库中还没有课件/讲义/笔记标题，请尽量从老师文本归纳，但不要编章名。")

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
