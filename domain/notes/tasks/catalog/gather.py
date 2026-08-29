"""从知识库抽出候选目录标题与重点上下文，拼给 catalog agent。"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from tools.knowledge.cite import open_knowledge
from tools.knowledge.config import PROJECT_ROOT
from tools.knowledge.source_role import (
    ROLE_MATERIAL,
    ROLE_NOTES,
    ROLE_TEACHER,
    ROLE_UNKNOWN,
    classify_source_role,
)
from .store import load_catalog, load_catalog_metas

# briefing 中标题候选采用动态预算：资料越短越收紧，避免 OCR 短标题诱导过度建 KP。
_MIN_BRIEF_TITLES = 60
_MAX_BRIEF_TITLES = 220
_TITLES_PER_PAGE = 6
_TITLES_PER_FILE = 30
_MIDDLE_TITLES_PER_FILE = 24
_MIDDLE_TITLES_PER_PAGE = 5
_DETAIL_POOL_LIMIT = 80
_DETAIL_POOL_PER_FILE = 24
_DETAIL_POOL_PER_PAGE = 6
_TITLE_KEYWORDS = ("定义", "性质", "定理", "规则", "方法", "公式", "例题", "易错", "注意", "总结", "步骤")
_ITEM_ONLY_KEYWORDS = ("例题", "易错", "注意", "总结", "步骤", "题型", "技巧", "提醒", "小结")
_BODY_LIKE_ENDINGS = ("。", "；", ";", ".", "！", "？", "!", "?")
_NUMBERED_TITLE_RE = re.compile(
    r"^(?:第[一二三四五六七八九十百零0-9]+[章节]|[一二三四五六七八九十]+、|\d+(?:\.\d+){0,3})"
)


def subject_from_context(text: str) -> str:
    m = re.search(r"【学科/课程】\s*([^【】\n]+)", text or "")
    return m.group(1).strip() if m else ""


def user_id_from_context(text: str) -> str:
    m = re.search(r"【用户ID】\s*([^【】\n]+)", text or "")
    return m.group(1).strip() if m else ""


def _is_ocr_note_source(source: str, user_id: str = "", subject: str = "") -> bool:
    stem = Path(source or "").stem
    if not stem or not (user_id or "").strip() or not (subject or "").strip():
        return False
    from tools.memory.store import safe_id

    path = (
        PROJECT_ROOT
        / "data"
        / safe_id(user_id)
        / "ocr"
        / safe_id(subject)
        / f"{stem}.md"
    )
    return path.is_file()


def _chunk_role(meta: dict[str, Any], source: str, user_id: str = "", subject: str = "") -> str:
    if _is_ocr_note_source(source, user_id, subject):
        return ROLE_NOTES
    role = str(meta.get("role") or "").strip()
    if role in {ROLE_MATERIAL, ROLE_NOTES, ROLE_TEACHER, ROLE_UNKNOWN}:
        return role
    return classify_source_role(source)


def _brief_chunks(
    kb: Any, user_id: str = "", subject: str = ""
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {
        ROLE_MATERIAL: [],
        ROLE_NOTES: [],
        ROLE_TEACHER: [],
        ROLE_UNKNOWN: [],
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
        role = _chunk_role(meta, source, user_id, subject)
        chapter = str(meta.get("chapter") or "")
        topic = str(meta.get("topic") or "")
        heading = str(meta.get("heading") or "")
        page = str(meta.get("page") or "")
        key = (source, chapter, heading or topic, page)
        if key in seen:
            continue
        seen.add(key)
        grouped.setdefault(role, []).append(
            {
                "source": source,
                "role": role,
                "chapter": chapter,
                "topic": topic,
                "heading": heading,
                "heading_path_text": str(meta.get("heading_path_text") or ""),
                "heading_score": str(meta.get("heading_score") or ""),
                "heading_kind": str(meta.get("heading_kind") or ""),
                "page": page,
                "content_tags": str(meta.get("content_tags") or ""),
                "contains_formula": str(meta.get("contains_formula") or ""),
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


_HEADING_PREFIX_RE = re.compile(
    r"^(?:"
    r"[一二三四五六七八九十百]+[、.．:：\s]\s*"
    r"|[（(][一二三四五六七八九十百\d]+[）)][、.．:：\s]*"
    r"|\d+(?:\.\d+)*[、.．:：\s]\s*"
    r"|[IVXLCDMivxlcdm]+[、.．:：\s]\s*"
    r"|第[0-9一二三四五六七八九十百]+[章节部分讲课项点步阶段周单元][、.．:：\s]*"
    r")"
)


def strip_heading_prefix(text: object) -> str:
    """剔除章节/主题/知识点名称中的序号前缀（如：'四、xxxxx'、'（五）xxxx'、'1. xxxx'、'第3节 xxxx'）。"""
    raw = " ".join(str(text or "").split()).strip()
    if not raw:
        return ""
    cleaned = raw
    while True:
        m = _HEADING_PREFIX_RE.match(cleaned)
        if m:
            remainder = cleaned[m.end():].strip()
            if remainder:
                cleaned = remainder
                continue
        break
    return cleaned or raw


def _clean_title(text: str) -> str:
    return strip_heading_prefix(text)


def _title_path(row: dict[str, str]) -> list[str]:
    path_text = _clean_title(row.get("heading_path_text") or "")
    if path_text:
        return _dedupe_path([p.strip() for p in path_text.split("/") if p.strip()])
    parts: list[str] = []
    for key in ("chapter", "topic", "heading"):
        title = _clean_title(row.get(key) or "")
        if title and title not in parts:
            parts.append(title)
    return _dedupe_path(parts)


def _dedupe_path(parts: list[str]) -> list[str]:
    out: list[str] = []
    for part in parts:
        if out and _compact_title(out[-1]) == _compact_title(part):
            continue
        out.append(part)
    return out


def _compact_title(text: str) -> str:
    return re.sub(r"[\s:：,，。；;、（）()\[\]【】《》“”\"'·\-—_]+", "", str(text or "").lower())


def _score_title_candidate(row: dict[str, str]) -> tuple[int, list[str]]:
    """标题候选评分：来源角色只作证据标签，主要看结构清晰度和学习价值。"""
    path = _title_path(row)
    title = path[-1] if path else ""
    raw_score = str(row.get("heading_score") or "").strip()
    if raw_score.isdigit():
        score = int(raw_score)
        reasons = ["入库标题评分"]
        kind = str(row.get("heading_kind") or "").strip()
        tags = str(row.get("content_tags") or "").strip()
        if _item_only_title(title, row):
            score = min(score, 4)
            reasons.append("细碎标题仅作item/evidence")
        if kind:
            reasons.append(f"kind={kind}")
        if tags:
            reasons.append(f"tags={tags}")
        return score, reasons
    score = 0
    reasons: list[str] = []
    if not title:
        return score, reasons
    if row.get("chapter"):
        score += 4
        reasons.append("有章级标题")
    if row.get("topic"):
        score += 3
        reasons.append("有主题层级")
    if row.get("heading"):
        score += 2
        reasons.append("有标题")
    if _NUMBERED_TITLE_RE.match(title):
        score += 2
        reasons.append("编号/章节格式")
    if any(word in title for word in _TITLE_KEYWORDS):
        score += 2
        reasons.append("知识点关键词")
    if _item_only_title(title, row):
        score = min(score, 4)
        reasons.append("细碎标题仅作item/evidence")
    if 2 <= len(title) <= 28:
        score += 1
        reasons.append("短标题")
    if len(title) > 45:
        score -= 3
        reasons.append("过长像正文")
    if title.endswith(_BODY_LIKE_ENDINGS):
        score -= 3
        reasons.append("句子结尾")
    return score, reasons


def _item_only_title(title: str, row: dict[str, str]) -> bool:
    text = _clean_title(title)
    if any(word in text for word in _ITEM_ONLY_KEYWORDS):
        return True
    tags = str(row.get("content_tags") or "")
    kind = str(row.get("heading_kind") or "")
    return kind == "knowledge_point" and any(tag in tags for tag in ("example", "mistake"))


def _candidate_budget(candidates: list[dict[str, Any]]) -> int:
    sources = {
        str(row.get("source") or "").strip()
        for row in candidates
        if str(row.get("source") or "").strip()
    }
    pages = {
        (str(row.get("source") or ""), str(row.get("page") or ""))
        for row in candidates
        if str(row.get("page") or "").strip()
    }
    if pages:
        raw = len(pages) * _TITLES_PER_PAGE
    else:
        raw = len(sources or {"_"}) * _TITLES_PER_FILE
    return max(_MIN_BRIEF_TITLES, min(_MAX_BRIEF_TITLES, raw))


def _title_candidates(grouped: dict[str, list[dict[str, str]]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seq = 0
    for role in (ROLE_MATERIAL, ROLE_NOTES, ROLE_UNKNOWN):
        for row in grouped.get(role) or []:
            path = _title_path(row)
            if not path:
                continue
            score, reasons = _score_title_candidate(row)
            if score <= 0:
                continue
            item = dict(row)
            item["path"] = path
            item["score"] = score
            item["reasons"] = reasons
            item["seq"] = seq
            candidates.append(item)
            seq += 1
    candidates.sort(
        key=lambda r: (
            -int(r.get("score") or 0),
            str(r.get("source") or ""),
            int(r.get("seq") or 0),
        )
    )
    return candidates


def _limited_middle_candidates(
    rows: list[dict[str, Any]],
    *,
    total_limit: int,
) -> list[dict[str, Any]]:
    """中可信标题只按文件/页抽样，避免 OCR 密集短标题挤占 prompt。"""
    if total_limit <= 0:
        return []
    selected: list[dict[str, Any]] = []
    file_counts: dict[str, int] = defaultdict(int)
    page_counts: dict[tuple[str, str], int] = defaultdict(int)
    seen_paths: set[tuple[str, str]] = set()
    for row in rows:
        source = str(row.get("source") or "")
        page = str(row.get("page") or "")
        path = " / ".join(row.get("path") or [])
        if not path:
            continue
        key = (source, path)
        if key in seen_paths:
            continue
        if file_counts[source] >= _MIDDLE_TITLES_PER_FILE:
            continue
        page_key = (source, page)
        if page and page_counts[page_key] >= _MIDDLE_TITLES_PER_PAGE:
            continue
        selected.append(row)
        seen_paths.add(key)
        file_counts[source] += 1
        if page:
            page_counts[page_key] += 1
        if len(selected) >= total_limit:
            break
    return selected


def _detail_pool_candidates(
    rows: list[dict[str, Any]],
    *,
    total_limit: int = _DETAIL_POOL_LIMIT,
) -> list[dict[str, Any]]:
    if total_limit <= 0:
        return []
    selected: list[dict[str, Any]] = []
    file_counts: dict[str, int] = defaultdict(int)
    page_counts: dict[tuple[str, str], int] = defaultdict(int)
    seen: set[tuple[str, str]] = set()
    for row in rows:
        source = str(row.get("source") or "")
        page = str(row.get("page") or "")
        path = " / ".join(row.get("path") or [])
        if not path:
            continue
        key = (source, path)
        if key in seen:
            continue
        if file_counts[source] >= _DETAIL_POOL_PER_FILE:
            continue
        page_key = (source, page)
        if page and page_counts[page_key] >= _DETAIL_POOL_PER_PAGE:
            continue
        selected.append(row)
        seen.add(key)
        file_counts[source] += 1
        if page:
            page_counts[page_key] += 1
        if len(selected) >= total_limit:
            break
    return selected


def _point_sources(point: dict[str, Any]) -> set[str]:
    return {
        str(name).strip()
        for name in point.get("source_documents") or []
        if str(name).strip()
    }


def _point_missing_required_fields(point: dict[str, Any]) -> list[str]:
    return [
        field
        for field in ("practice_type", "completion_criteria", "learning_role", "risk_tags")
        if not (point.get(field) or [])
    ]


def _compact_existing(
    catalog: dict[str, Any],
    *,
    detailed_sources: set[str] | None = None,
) -> str:
    detailed_sources = detailed_sources or set()
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
            points = [
                point
                for point in topic.get("knowledge_points") or []
                if isinstance(point, dict)
            ]
            compact_names: list[str] = []
            expanded = 0
            for point in points:
                if not isinstance(point, dict):
                    continue
                missing = _point_missing_required_fields(point)
                relevant = bool(_point_sources(point) & detailed_sources)
                if missing or relevant:
                    mark = f"（缺字段：{'、'.join(missing)}）" if missing else "（与新资料相关）"
                    lines.append(
                        f"      - [{point.get('id') or ''}] {point.get('name') or ''}{mark}"
                    )
                    expanded += 1
                else:
                    compact_names.append(f"[{point.get('id') or ''}] {point.get('name') or ''}")
            if compact_names:
                shown = "、".join(compact_names[:8])
                rest = len(compact_names) - 8
                tail = f" 等剩余 {rest} 个" if rest > 0 else ""
                lines.append(f"      - 已有KP摘要：{shown}{tail}")
            if expanded and compact_names:
                lines.append("      - 其余已有 KP 只按摘要匹配；不要重写。")
    return "\n".join(lines)


def _sources_from_grouped(grouped: dict[str, list[dict[str, str]]] | None) -> set[str]:
    if not grouped:
        return set()
    return {
        str(row.get("source") or "").strip()
        for rows in grouped.values()
        for row in rows
        if str(row.get("source") or "").strip()
    }


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


def _compact_standard_metas(metas: list[dict[str, Any]]) -> str:
    if not metas:
        return ""
    allowed = {"catalog_hints", "knowledge_points"}
    compacted: list[dict[str, Any]] = []
    for meta in metas:
        if not isinstance(meta, dict):
            continue
        item = {key: meta.get(key) or [] for key in allowed}
        source = str(meta.get("source") or "").strip()
        if source:
            item["source"] = source
        compacted.append(item)
    return json.dumps(compacted, ensure_ascii=False)[:10000]


def _existing_kp_count(catalog: dict[str, Any] | None) -> int:
    """统计已有目录的 KP 总数(空壳检测用)。"""
    if not isinstance(catalog, dict):
        return 0
    count = 0
    for chapter in catalog.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            count += len(topic.get("knowledge_points") or [])
    return count


def _candidates_count(grouped: dict[str, list[dict[str, Any]]] | None) -> int:
    """候选标题总数(空壳检测用：候选充足才强制重建)。"""
    if not grouped:
        return 0
    return len(_title_candidates(grouped))


def build_catalog_briefing(shared_context: str) -> str:
    """给 LLM 的压缩输入：历史目录 + 骨架标题 + 老师原文。"""
    user_id = user_id_from_context(shared_context)
    subject = subject_from_context(shared_context)
    existing = load_catalog(user_id=user_id, subject=subject)
    mode = "incremental_update" if existing else "build"
    kb = open_knowledge(user_id=user_id)
    grouped = _brief_chunks(kb, user_id, subject) if kb is not None else None
    incoming_sources = _sources_from_grouped(grouped)
    parts = [
        "【任务】生成或增量更新课程知识目录，不要写复习建议。",
        f"【学科/课程】{subject or '未标注'}",
        f"【知识库集合】{user_id or ''}__{subject or ''}",
        f"【mode】{mode}",
    ]
    if existing:
        # 空壳检测：已有目录近乎为空且候选充足 → 强制重建，避免空壳增量固化
        if _existing_kp_count(existing) <= 3 and _candidates_count(grouped) >= 5:
            parts.append(
                "【空壳目录】检测到已有目录近乎为空（不足 3 个知识点），"
                "请基于下方候选标题**完整重建**知识树："
                "按候选的 score 与层级组织章节/主题/知识点，"
                "不要保留空壳节点（course 可沿用）；每个主题至少 2 个知识点。"
            )
        else:
            parts.append("【已有目录】必须复用下列 ID，禁止重建旧章。缺 role/practice/criteria/risk 的 KP 只补这四个字段。")
            parts.append(_compact_existing(existing, detailed_sources=incoming_sources))
        known = known_source_documents(existing)
        if known:
            parts.append("【已入库并已编目的文件】" + "、".join(sorted(known)))
    else:
        parts.append("【已有目录】无，按首次 build 生成完整树。")
    standard_metas = load_catalog_metas(user_id=user_id, subject=subject)
    meta_text = _compact_standard_metas(standard_metas)
    if meta_text:
        parts.append(
            "【OCR Standard Meta 增强信号】\n"
            "以下 meta 只说明怎么切目录：章节顺序、可学的 KP、公式 items、重要性。"
            "source 对应同名审校 Markdown，来源是学生笔记。"
            "不要用小节标题当该节唯一 KP；公式进 knowledge_items；笔记没有的不要编。"
            "每个主题都要有 KP，名额按主题分配，不要切丢后面的节。"
            "例题/旁注/页眉页脚不要升成章或 KP。强调只提高已有点的 importance。"
            "不要让 meta 发明关系网或练习题。\n"
            + meta_text
        )
    if kb is None:
        parts.append("【知识库】当前不可用，只根据下面老师文本建目录。")
    else:
        grouped = grouped or {}
        ocr_notes = sorted(
            {
                str(row.get("source") or "").strip()
                for rows in grouped.values()
                for row in rows
                if row.get("role") == ROLE_NOTES and str(row.get("source") or "").strip()
            }
        )
        if ocr_notes:
            parts.append(
                "【OCR 学生笔记文件】"
                + "、".join(ocr_notes)
                + "。这些文件来自 OCR 入库，sources 写「学生笔记」，"
                "evidence 用「学生笔记：短片段」，覆盖到的 KP 用 detailed/mentioned，不要标 none。"
            )
        candidates = _title_candidates(grouped)
        if candidates:
            parts.append(
                "【候选目录标题】以下标题来自 material/notes/unknown 的统一候选池；"
                "role 只表示来源类型，不决定优先级。请优先使用 score 高、层级连续、路径稳定的标题建树；"
                "notes 与 material 同等重要，OCR 笔记结构清晰时可以作为主骨架。"
                "heading_kind=knowledge_point 只表示候选知识点，不等于必须新建 KP；"
                "例题/易错/注意/步骤/题型/小结类标题只能并入父 KP 的 knowledge_items 或 evidence。"
            )
            budget = _candidate_budget(candidates)
            high = [row for row in candidates if int(row.get("score") or 0) >= 6]
            middle = [row for row in candidates if 4 <= int(row.get("score") or 0) < 6]
            low = [row for row in candidates if int(row.get("score") or 0) < 5]
            limited_middle = _limited_middle_candidates(middle, total_limit=min(90, budget))
            detail_pool = _detail_pool_candidates(middle + low)
            if high:
                parts.append("【高可信骨架】（优先形成章/主题；若多来源重复，合并为同一节点）")
            else:
                parts.append("【高可信骨架】未发现高分标题，请从下面的知识点标题中保守归纳章节。")
            by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in high or limited_middle:
                by_file[str(row.get("source") or "")].append(row)
            known = known_source_documents(existing) if existing else set()
            emitted = 0
            emitted_paths: set[tuple[str, str]] = set()
            for fname, rows in list(by_file.items())[:20]:
                if emitted >= budget:
                    break
                tag = "（已在目录中）" if fname in known else "（新资料/待匹配）"
                parts.append(f"- 文件 {fname} {tag}")
                seen_paths: set[str] = set()
                for row in rows[:40]:
                    if emitted >= budget:
                        break
                    path = " / ".join(row.get("path") or [])
                    if path and path not in seen_paths:
                        seen_paths.add(path)
                        emitted_paths.add((fname, path))
                        reason = "、".join(row.get("reasons") or [])
                        parts.append(
                            f"  · [score={row.get('score')}; role={row.get('role')}; {reason}] {path}"
                        )
                        emitted += 1
            if emitted >= budget:
                parts.append(f"  · …（候选标题过多，已按资料规模截断到 {budget} 条）")
            remaining_middle = [
                row
                for row in limited_middle
                if (str(row.get("source") or ""), " / ".join(row.get("path") or []))
                not in emitted_paths
            ]
            if high and remaining_middle:
                parts.append("【知识点标题】（仅为候选：定义/公式/方法可考虑作 KP；例题/易错/注意/步骤/题型/小结只能作 item/evidence）")
                remaining = max(0, budget - emitted)
                middle_budget = min(60, remaining)
                for row in remaining_middle[:middle_budget]:
                    parts.append(
                        f"- [score={row.get('score')}; role={row.get('role')}; source={row.get('source')}] "
                        + " / ".join(row.get("path") or [])
                    )
            if low:
                parts.append(
                    f"【低可信标题】共 {len(low)} 条，已从主 prompt 省略；"
                    "只作为知识库 evidence，不要据此新建章/主题/KP。"
                )
            if detail_pool:
                parts.append(
                    "【细节池】以下内容只能用于补充已有/新建 KP 的 knowledge_items、"
                    "prerequisites、risk_tags、completion_criteria、evidence；"
                    "禁止把这里的条目升成 chapter/topic/KP。"
                )
                for row in detail_pool:
                    reason = "、".join(row.get("reasons") or [])
                    tags = str(row.get("content_tags") or "").strip()
                    meta = f"score={row.get('score')}; role={row.get('role')}"
                    if tags:
                        meta += f"; tags={tags}"
                    if reason:
                        meta += f"; {reason}"
                    parts.append(
                        f"- [{meta}; source={row.get('source')}; page={row.get('page')}] "
                        + " / ".join(row.get("path") or [])
                    )
        else:
            parts.append("【候选目录标题】知识库里还没有可用标题，请尽量从老师文本归纳，但不要编资料里没有的章名。")

    teacher = _teacher_text(shared_context)
    if teacher:
        parts.append("【老师划重点原文】")
        parts.append(teacher[:6000])
    else:
        parts.append("【老师划重点原文】无。teacher_emphasis 全部填 0，不要假装老师点过。")
    return "\n".join(parts)


def _teacher_text(shared_context: str) -> str:
    raw = shared_context or ""
    # 老师重点文件（docs 传入的 .txt）注入的专用块优先
    if "【老师重点】" in raw:
        body = raw.split("【老师重点】", 1)[1]
        for stop in ("\n\n【", "\n\n用户画像：", "\n\n已审核", "\n\n原文"):
            if stop in body:
                body = body.split(stop, 1)[0]
        return body.strip()
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


# ── 输出侧覆盖度补缺(零 LLM)────────────────────────────────────

def _title_key(text: str) -> str:
    """标题归一化键(覆盖度比对用):去空白/编号前缀/常见后缀。"""
    blob = re.sub(r"\s+", "", (text or ""))
    blob = re.sub(
        r"^(?:第?[0-9一二三四五六七八九十百]+[节章部分讲课]?[.、．]?\s*|\d+\s*[.、．]\s*)",
        "", blob,
    )
    for suffix in ("的定义", "的概念", "的性质", "详解", "总结", "小结"):
        if blob.endswith(suffix) and len(blob) > len(suffix):
            blob = blob[: -len(suffix)]
    return blob


def _catalog_kp_names(draft: dict[str, Any]) -> list[str]:
    """目录中已有的 KP 名列表(归一化比对用)。"""
    names: list[str] = []
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for kp in topic.get("knowledge_points") or []:
                if isinstance(kp, dict) and _clean_title(str(kp.get("name") or "")):
                    names.append(str(kp.get("name") or ""))
    return names


def _next_kp_id(draft: dict[str, Any]) -> int:
    max_no = 0
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for kp in topic.get("knowledge_points") or []:
                if not isinstance(kp, dict):
                    continue
                m = re.search(r"kp_(\d+)", str(kp.get("id") or ""))
                if m:
                    max_no = max(max_no, int(m.group(1)))
    return max_no + 1


def complement_catalog_coverage(
    draft: dict[str, Any],
    shared_context: str,
) -> dict[str, Any]:
    """输出侧覆盖度校验：候选池高可信标题未进目录 → 程序补缺（零 LLM）。

    补缺 KP 标记 ``node_status=program_complement``、``change_type=added``；
    归属：候选有 chapter/topic 层级则匹配目录对应 topic，否则挂首个 chapter 的末 topic。
    """
    import logging

    logger = logging.getLogger(__name__)
    out = dict(draft)
    user_id = user_id_from_context(shared_context)
    subject = subject_from_context(shared_context)
    kb = open_knowledge(user_id=user_id)
    grouped = _brief_chunks(kb, user_id, subject) if kb is not None else None
    candidates = _title_candidates(grouped) if grouped else []
    strong = [
        c
        for c in candidates
        if int(c.get("score") or 0) >= 5
        and str(c.get("heading_kind") or "") != "evidence"
        and not _item_only_title(str((c.get("path") or [""])[-1]), c)
    ]
    chapters = out.get("chapters") or []
    if not strong or not chapters:
        return out
    existing = _catalog_kp_names(out)
    next_no = _next_kp_id(out)
    added = 0
    for cand in strong:
        path = list(cand.get("path") or [])
        title = path[-1] if path else ""
        key = _title_key(title)
        if not key or any(key == _title_key(n) for n in existing):
            continue
        cand_chapter = _clean_title(path[0]) if path else ""
        cand_topic = _clean_title(path[1]) if len(path) > 1 else ""
        # 归属：候选层级优先匹配；否则挂第一个 chapter 的末 topic
        target_chapter = next(
            (
                chapter
                for chapter in chapters
                if isinstance(chapter, dict)
                and cand_chapter
                and _title_key(cand_chapter) == _title_key(str(chapter.get("name") or ""))
            ),
            None,
        )
        if target_chapter is None:
            target_chapter = chapters[0]
        topics = [t for t in (target_chapter.get("topics") or []) if isinstance(t, dict)]
        target_topic = None
        if cand_topic:
            target_topic = next(
                (
                    t
                    for t in topics
                    if _title_key(cand_topic) == _title_key(str(t.get("name") or ""))
                ),
                None,
            )
        if target_topic is None:
            target_topic = topics[-1] if topics else None
        if target_topic is None:
            tp_no = len(
                [
                    t
                    for ch in chapters
                    if isinstance(ch, dict)
                    for t in (ch.get("topics") or [])
                    if isinstance(t, dict) and re.search(r"tp_\d+", str(t.get("id") or ""))
                ]
            ) + 1
            target_topic = {
                "id": f"tp_{tp_no:03d}",
                "name": "补充知识点",
                "change_type": "added",
                "knowledge_points": [],
            }
            target_chapter.setdefault("topics", []).append(target_topic)
        kp_list = target_topic.setdefault("knowledge_points", [])
        kp = {
            "id": f"kp_{next_no:03d}",
            "name": title,
            "aliases": [],
            "knowledge_type": "concept",
            "knowledge_items": [],
            "importance": 3,
            "difficulty": 3,
            "teacher_emphasis": 0,
            "change_type": "added",
            "node_status": "program_complement",
            "sources": [str(cand.get("source") or "")],
            "prerequisites": [],
            "related_points": [],
            "risk_tags": [],
            "completion_criteria": [],
            "exam_signal": "none",
            "topic": str(target_topic.get("name") or ""),
            "chapter": str(target_chapter.get("name") or ""),
            "confidence": "low",
        }
        kp_list.append(kp)
        existing.append(title)
        next_no += 1
        added += 1
    if added:
        logger.info("目录覆盖度补缺 %d 个候选 KP", added)
    return out


def _max_kp_budget(shared_context: str) -> int:
    """目录规模上限：页数×1.2（无页数时文件数×3），下限 6、上限 40。

    依据 NOTES_OPTIMIZATION_GUIDE.md 2.3：教材型资料每页约 0.8~1.2 个 KP。
    """
    user_id = user_id_from_context(shared_context)
    subject = subject_from_context(shared_context)
    kb = open_knowledge(user_id=user_id)
    grouped = _brief_chunks(kb, user_id, subject) if kb is not None else None
    pages = {
        (str(row.get("source") or ""), str(row.get("page") or ""))
        for rows in (grouped or {}).values()
        for row in rows
        if str(row.get("page") or "").strip()
    }
    no_page_sources = {
        str(row.get("source") or "")
        for rows in (grouped or {}).values()
        for row in rows
        if str(row.get("source") or "").strip()
        and not str(row.get("page") or "").strip()
    }
    raw = len(pages) * 1.2 + len(no_page_sources) * 3
    return max(6, min(40, int(round(raw))))


def trim_catalog_scale(
    draft: dict[str, Any],
    shared_context: str,
) -> dict[str, Any]:
    """规模上限校验：KP 数 > max → 程序合并最弱 KP 进父 topic 的 items（零 LLM）。

    合并顺序：importance 低优先 → program_complement 优先 → 名称长优先；
    每个 topic 至少保留 1 个 KP。
    """
    out = dict(draft)
    max_kp = _max_kp_budget(shared_context)
    rows: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for chapter in out.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for kp in topic.get("knowledge_points") or []:
                if isinstance(kp, dict) and _clean_title(str(kp.get("name") or "")):
                    rows.append((chapter, topic, kp))
    if len(rows) <= max_kp:
        return out

    def _weakness(kp: dict[str, Any]) -> tuple[int, int, int]:
        try:
            imp = int(str(kp.get("importance") or 3) or 3)
        except (TypeError, ValueError):
            imp = 3
        comp = 1 if str(kp.get("node_status") or "") == "program_complement" else 0
        return (imp, comp, -len(str(kp.get("name") or "")))

    # 每个 topic 至少留 1 个 KP
    topic_counts: dict[int, int] = {}
    for _ch, topic, _kp in rows:
        topic_counts[id(topic)] = topic_counts.get(id(topic), 0) + 1
    rows.sort(key=lambda x: _weakness(x[2]))
    overflow = rows[max_kp:]
    merged = 0
    for chapter, topic, kp in overflow:
        if topic_counts.get(id(topic), 0) <= 1:
            continue
        name = str(kp.get("name") or "").strip()
        items = topic.setdefault("knowledge_items", [])
        if name and name not in items:
            items.append(name)
        kp_list = topic.get("knowledge_points") or []
        if kp in kp_list:
            kp_list.remove(kp)
        topic_counts[id(topic)] = topic_counts.get(id(topic), 0) - 1
        chapter["change_type"] = "updated"
        topic["change_type"] = "updated"
        merged += 1
    if merged:
        import logging

        logging.getLogger(__name__).info(
            "目录规模上限校验：合并 %d 个最弱 KP 进父 topic items（上限 %d）",
            merged,
            max_kp,
        )
    return out


# ── 重要性 / 复习权重程序计算(零 LLM)───────────────────────────

def _catalog_kp_index(draft: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """目录 KP 索引 + 被引用计数（prerequisites/related_points 中出现次数）。"""
    kps: list[dict[str, Any]] = []
    ref_count: dict[str, int] = {}
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for kp in topic.get("knowledge_points") or []:
                if not isinstance(kp, dict):
                    continue
                kps.append(kp)
                for ref in list(kp.get("prerequisites") or []) + list(kp.get("related_points") or []):
                    if isinstance(ref, str):
                        ref_name = _clean_title(ref)
                    elif isinstance(ref, dict):
                        ref_name = _clean_title(str(ref.get("name") or ""))
                    else:
                        ref_name = ""
                    if ref_name:
                        ref_count[ref_name] = ref_count.get(ref_name, 0) + 1
    return kps, ref_count


def _knowledge_type_weight(ktype: str) -> int:
    return {"theorem": 5, "formula": 5, "concept": 4, "method": 3, "application": 2}.get(
        str(ktype or ""), 3
    )


def compute_kp_importance(
    kp: dict[str, Any],
    ref_count: dict[str, int],
) -> int:
    """程序计算 importance = 0.4×结构 + 0.3×内容 + 0.3×老师，clamp 1-5。

    边界修正：老师明确强调（teacher_emphasis≥2）且与程序分差 ≥2 → 保留 LLM 值。
    """
    name = _clean_title(str(kp.get("name") or ""))
    refs = ref_count.get(name, 0)
    structure = 1 if refs == 0 else 3 if refs <= 2 else 5
    ktype = _knowledge_type_weight(str(kp.get("knowledge_type") or ""))
    items = len(kp.get("knowledge_items") or [])
    content = min(ktype + (0 if items == 0 else 1 if items <= 2 else 2), 5)
    try:
        emph = int(str(kp.get("teacher_emphasis") or 0) or 0)
    except (TypeError, ValueError):
        emph = 0
    teacher = min(emph * 2, 5) if emph else 0
    computed = round(0.4 * structure + 0.3 * content + 0.3 * teacher)
    computed = max(1, min(5, computed))
    try:
        llm_imp = int(str(kp.get("importance") or 0) or 0)
    except (TypeError, ValueError):
        llm_imp = 0
    if emph >= 2 and llm_imp and abs(llm_imp - computed) >= 2:
        return max(1, min(5, llm_imp))
    return computed


def compute_review_weight(
    kp: dict[str, Any],
    ref_count: dict[str, int],
) -> float:
    """复习权重(0-1) = 0.5×importance + 0.2×difficulty + 0.2×考试信号 + 0.1×前置依赖。"""
    try:
        importance = int(str(kp.get("importance") or 3) or 3)
    except (TypeError, ValueError):
        importance = 3
    try:
        difficulty = int(str(kp.get("difficulty") or 3) or 3)
    except (TypeError, ValueError):
        difficulty = 3
    exam = 0.2 if str(kp.get("exam_signal") or "none").strip() not in ("", "none") else 0.0
    refs = ref_count.get(_clean_title(str(kp.get("name") or "")), 0)
    prereq = min(refs, 3) / 3 * 0.1
    w = 0.5 * importance / 5 + 0.2 * difficulty / 5 + 0.2 * exam + prereq
    return round(max(0.0, min(1.0, w)), 3)


def compute_catalog_signals(draft: dict[str, Any]) -> dict[str, Any]:
    """对目录每个 KP 计算 importance / review_weight 并写回（零 LLM）。"""
    kps, ref_count = _catalog_kp_index(draft)
    for kp in kps:
        kp["importance"] = compute_kp_importance(kp, ref_count)
        kp["review_weight"] = compute_review_weight(kp, ref_count)
    return draft


# ── 溯源 / 老师重点程序回填(零 LLM)────────────────────────────

def _teacher_emphasis_level(hit_sentences: list[str]) -> int:
    """老师重点分级:0 未提及 / 1 提及 / 2 明确强调 / 3 反复强调(多句+强词)。"""
    strong = ("必考", "重点", "掌握", "一定", "反复", "务必", "重要")
    blob = "".join(hit_sentences)
    n = len(hit_sentences)
    has_strong = any(w in blob for w in strong)
    if n >= 2 and has_strong:
        return 3
    if n >= 1 and has_strong:
        return 2
    if n >= 1:
        return 1
    return 0


def _teacher_match(kp: dict[str, Any], teacher: str) -> list[str]:
    """老师文本命中该 KP 的句子：键 = name + aliases + knowledge_items（归一化匹配）。"""
    keys = [str(kp.get("name") or "")]
    keys.extend(str(a) for a in (kp.get("aliases") or []) if isinstance(a, str))
    keys.extend(str(i) for i in (kp.get("knowledge_items") or []) if isinstance(i, str))
    norm_keys = [_compact_title(k) for k in keys if _compact_title(k)]
    hits: list[str] = []
    for sent in re.split(r"[。！？；\n]+", teacher or ""):
        s = sent.strip()
        if not s:
            continue
        blob = _compact_title(s)
        if any(nk and (nk in blob or blob in nk) for nk in norm_keys):
            hits.append(s)
            if len(hits) >= 3:
                break
    return hits


def backfill_catalog_trace(
    draft: dict[str, Any],
    shared_context: str,
) -> dict[str, Any]:
    """溯源 / 老师重点程序回填（零 LLM）。

    溯源（两类通用）：sources / source_chunk_ids / evidence 从知识库 chunk
    按名称/内容匹配回填（chunk 标识 = source#heading）。

    老师重点：
    - 不传老师文本：teacher_emphasis 保持 0，不生成 teacher_focus_items / teacher_evidence；
    - 传老师文本：程序按 KP 名/items 匹配老师句子 → teacher_emphasis 分级（0-3，取较大值）
      + teacher_focus_items / teacher_evidence（依据句）。
    """
    user_id = user_id_from_context(shared_context)
    subject = subject_from_context(shared_context)
    kb = open_knowledge(user_id=user_id)
    chunks = (
        list(kb.list_chunks(user_id=user_id, subject=subject) or [])
        if kb is not None
        else []
    )
    teacher = _teacher_text(shared_context) or ""
    out = dict(draft)
    for chapter in out.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for kp in topic.get("knowledge_points") or []:
                if not isinstance(kp, dict):
                    continue
                name = _clean_title(str(kp.get("name") or ""))
                key = _compact_title(name)
                # ── 溯源回填（重建：程序匹配优先，覆盖历史/LLM 编造值）──
                hits: list[dict[str, Any]] = []
                for c in chunks:
                    meta = c.get("metadata") or {}
                    heading = _clean_title(str(meta.get("heading") or ""))
                    if heading and key and _compact_title(heading) == key:
                        hits.append(c)
                        continue
                    text = _compact_title(str(c.get("text") or ""))
                    if key and len(key) >= 4 and key in text:
                        hits.append(c)
                if hits:
                    sources: list[str] = []
                    cids: list[str] = []
                    evs: list[str] = []
                    for h in hits[:3]:
                        meta = h.get("metadata") or {}
                        src = str(meta.get("source") or "")
                        heading = str(meta.get("heading") or "")
                        cid = f"{src}#{heading}" if src and heading else src
                        if src and src not in sources:
                            sources.append(src)
                        if cid and cid not in cids:
                            cids.append(cid)
                        ev = " ".join(str(h.get("text") or "").split())[:120]
                        if ev and ev not in evs:
                            evs.append(ev)
                    kp["sources"] = sources
                    kp["source_chunk_ids"] = cids
                    kp["evidence"] = evs
                    # 内容指纹随溯源回填（checklist 卡片 briefing 用，不重读全文）
                    fp = str((hits[0].get("metadata") or {}).get("content_fingerprint") or "")
                    if fp:
                        kp["content_fingerprint"] = fp
                # ── 老师重点回填（重建：依据句 = 本轮老师文本命中，覆盖历史）──
                if teacher.strip():
                    hit_sents = _teacher_match(kp, teacher)
                    if hit_sents:
                        kp["teacher_emphasis"] = _teacher_emphasis_level(hit_sents)
                        kp["teacher_focus_items"] = hit_sents[:3]
                        kp["teacher_evidence"] = hit_sents[:3]
    return out
