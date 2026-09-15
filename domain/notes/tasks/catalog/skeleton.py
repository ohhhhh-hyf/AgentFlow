"""原文 → 有序骨架：catalog 的权威结构输入（零 LLM，纯解析）。

为什么要它：目录的**顺序**与**覆盖**必须是结构保证，而不是若干启发式求和。
P1 之前这两件事全交给模型（输入只是一份"标题 + 分数"的扁平清单），于是
"某一节有没有进目录"取决于当初那页 LLM 用了几个 `#`。骨架把两件事收回程序：

- **顺序**：文件序 → 页块序（`<!-- ocr-pages: lo-hi -->`）→ 节序；
- **覆盖**：原文里每个**非细碎**标题都进骨架（细碎标题见下），程序最后按骨架补缺；
- **层级**：取**页块内相对层级**——OCR 合并稿逐页由 LLM 生成，`#` 数量跨页不可比，
  所以基准是"该页块内最浅标题"，只相信块内相对深度。

粒度映射（当前口径）：
    页块内最浅级 → **主题**；更深级 → **知识点**，按原文顺序挂在所属主题下。
    章不来自原文（原文层级不足以定章），由模型按语义分组，顺序/覆盖照样受校验。

细碎标题（例题/易错/注意/小结/步骤/题型…）**不建节点**：标题行丢掉，其正文并入
父节点正文，内容不会消失（仍可被归纳成 items）。
续页标题（`X（续）`）并入同名节点，不产生第二个节点。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from tools.knowledge.document_processor import PAGE_MARK_RE
from tools.knowledge.source_role import heading_level, is_ocr_notes_file

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).resolve().parents[4]  # 项目根

# 细碎标题：与 gather._ITEM_ONLY_KEYWORDS 同源语义——那边决定"候选标题只能当条目材料"，
# 这边决定"根本不建节点"。改词表时两处一起看。
# 辅助性内容词表集中一处（可配置，见 catalog/taxonomy.py），本模块不再自带副本
from .taxonomy import (
    is_item_heading as _taxonomy_is_item_heading,
    is_placeholder_name,
    item_marks,
)  # noqa: E402

_CONT_SUFFIX_RE = re.compile(r"[（(]\s*续\s*[）)]|续\s*$")
_HEADING_PREFIX_RE = re.compile(
    r"^(?:第[0-9一二三四五六七八九十百]+[章节部分讲课项点步阶段周单元][、.．:：\s]*"
    r"|[一二三四五六七八九十百]+[、.．:：]\s*"
    r"|\d+(?:\.\d+){0,3}[、.．:：]\s*)"
)
_TRAIL_PUNCT_RE = re.compile(r"[\s：:，,。；;、]+$")   # 名字尾部标点（`证明：` → `证明`）
_BODY_PROMPT_LIMIT = 120   # 每个节点进 prompt 的正文摘要长度
_MD_PROMPT_LIMIT = 14000   # 骨架段整体上限（超出则截断提示，覆盖仍由补缺保证）
_MAX_TIER = 3              # 目录只有三层（章/主题/KP）：更深的标题折进 KP 正文


def clean_title(text: object) -> str:
    """标题归一显示：去序号前缀（`一、`/`1.2`/`第3节`）+ 压缩空白。"""
    raw = " ".join(str(text or "").split()).strip()
    if not raw:
        return ""
    out = raw
    while True:
        m = _HEADING_PREFIX_RE.match(out)
        if m and out[m.end():].strip():
            out = out[m.end():].strip()
            continue
        break
    return out


_CIRCLED_RE = re.compile(r"^[①-⑳❶-❿⒈-⒛]+\s*")
_CORE_SPLIT_RE = re.compile(r"[、，,。：:；;（）()【】\[\]/·]")


_BARE_NUM_PREFIX_RE = re.compile(r"^[①-⑳❶-❿⒈-⒛]?\s*\d{1,2}\s*[.、．)）:：]?\s+(?=\S)")


def node_name(title: object) -> str:
    """节点显示名：去序号前缀（`一、`/`①②③`/`3 `）+ 去尾部标点。原文原名另存 raw_name。"""
    blob = _CIRCLED_RE.sub("", clean_title(title)).strip()
    blob = _HEADING_PREFIX_RE.sub("", blob).strip()
    # 裸数字前缀（`3 标题`、`2 标题`）：只在"数字 + 空格 + 还有内容"时剥掉
    bare = _BARE_NUM_PREFIX_RE.match(blob)
    if bare and blob[bare.end():].strip():
        blob = blob[bare.end():].strip()
    return _TRAIL_PUNCT_RE.sub("", blob).strip() or clean_title(title).strip()


def norm_key(text: object) -> str:
    """比对键：去空白 + 去圈号与序号前缀（骨架 ↔ 目录节点对齐用）。"""
    return "".join(_CIRCLED_RE.sub("", clean_title(text)).split())


def core_key(text: object) -> str:
    """核心键：再去首个标点后的尾巴（`① 甲，乙的并列说明` → `甲`）。

    同一个知识点在原文与目录里的写法常只差序号与后半截并列项（`甲、乙`），
    严格键会把这种"其实覆盖了"的情况误报成缺口，所以覆盖判定用核心键兜一层。
    """
    blob = _CIRCLED_RE.sub("", clean_title(text)).strip()
    return norm_key(_CORE_SPLIT_RE.split(blob, 1)[0])


def is_item_heading(title: str) -> bool:
    """辅助性内容标题（例题/易错/小结…）：不建节点。词表见 `taxonomy`（可配置）。"""
    return _taxonomy_is_item_heading(clean_title(title))


def _cont_name(title: str) -> tuple[str, bool]:
    """`X（续）` → ("X", True)；普通标题 → (原样, False)。"""
    cleaned = clean_title(title)
    if _CONT_SUFFIX_RE.search(cleaned):
        return clean_title(_CONT_SUFFIX_RE.sub("", cleaned)), True
    return cleaned, False


# ── 栈式标题树（P5：不再用"区域 + 相对层级"启发式）────────────────
#
# 原文的 Markdown 层级本身就是结构（实测这份合并稿 8/26/28 相当规整）：
#   `#` 数量 → 父子关系，用栈直接建树；跳级（`#` 后直接 `###`）由栈自动挂到最近的更浅祖先。
# 层级映射按"文件里出现的层级数"归一，用**树深度**而不是标题级别判定层级，
# 这样跳级处不会出现"有 KP 无主题"的空档：
#   三级文件 → depth1 章 / depth2 主题 / depth≥3 知识点
#   两级文件 → depth1 主题 / depth≥2 知识点
#   一级文件 → depth1 主题（KP 由模型从正文提炼）

def _collect_headings(text: str) -> tuple[list[dict[str, Any]], int]:
    """收集标题（含行号/级别/页块）并跳过细碎标题。"""
    heads: list[dict[str, Any]] = []
    dropped = 0
    span = ""
    for idx, raw_line in enumerate((text or "").splitlines()):
        line = raw_line.strip()
        mark = PAGE_MARK_RE.match(line)
        if mark:
            lo, hi = mark.group(1), mark.group(2)
            span = f"{lo}-{hi}" if hi and hi != lo else lo
            continue
        hit = heading_level(line)
        if not hit:
            continue
        level, raw_title = hit
        if is_item_heading(raw_title):
            dropped += 1  # 细碎标题不建节点，正文仍会并进当前节点
            continue
        name, is_cont = _cont_name(raw_title)
        if not name:
            continue
        heads.append(
            {
                "line": idx,
                "level": level,
                "raw_name": name,
                "name": node_name(name),
                "span": span,
                "is_cont": is_cont,
                "_children": [],
                "_body": [],
            }
        )
    return heads, dropped


def _build_tree(
    heads: list[dict[str, Any]], lines: list[str]
) -> tuple[list[dict[str, Any]], int]:
    """单趟构建标题树 + 归属正文：正文归给"包住它的最深标题"（Markdown 语义）。

    跳级（`#` 后直接 `###`）由栈自动挂到最近的更浅祖先，并计数（缺父归位）。
    """
    roots: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []
    jumps = 0
    cursor = 0
    for head in heads:
        # 把上一个标题到本标题之间的正文，归给"当前最深标题"
        if stack:
            for raw in lines[cursor : head["line"]]:
                if raw.strip():
                    stack[-1]["_body"].append(raw.strip())
        while stack and stack[-1]["level"] >= head["level"]:
            stack.pop()
        if stack:
            if head["level"] > stack[-1]["level"] + 1:
                jumps += 1
            stack[-1]["_children"].append(head)
        else:
            roots.append(head)
        stack.append(head)
        cursor = head["line"] + 1
    if stack:
        for raw in lines[cursor:]:
            if raw.strip():
                stack[-1]["_body"].append(raw.strip())
    return roots, jumps


def _merge_into(target: dict[str, Any], node: dict[str, Any]) -> None:
    """把 node 的内容并进 target（正文拼接；子节点按名字去重后并入）。"""
    if node.get("_body"):
        target["_body"].extend(node["_body"])
        node["_body"] = []
    existing = {norm_key(child["name"]) for child in target["_children"]}
    for child in node["_children"]:
        key = norm_key(child["name"])
        if key in existing:
            same = next(
                (c for c in target["_children"] if norm_key(c["name"]) == key), None
            )
            if same is not None:
                _merge_into(same, child)
                continue
        existing.add(key)
        target["_children"].append(child)
    node["_children"] = []


def _repair_tree(nodes: list[dict[str, Any]], stats: dict[str, int]) -> None:
    """确定性修补：`X（续）` 并入同名节点；同级同名节点合并（递归）。"""
    kept: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for node in nodes:
        key = norm_key(node["name"])
        same = by_key.get(key)
        if same is not None:
            # 续页 / 同名同级（如两处「最概然分布求算」）：并入已有节点
            if node.get("is_cont"):
                stats["merged_continued"] += 1
            else:
                stats["merged_same_name"] += 1
            _merge_into(same, node)
            continue
        by_key[key] = node
        kept.append(node)
    nodes[:] = kept
    for node in nodes:
        _repair_tree(node["_children"], stats)


def _map_tiers(
    roots: list[dict[str, Any]], span: int, stats: dict[str, int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """树深度 → 目录层级（章/主题/知识点）。

    - 三级文件（span ≥ 3）：depth1 章 / depth2 主题 / depth ≥ 3 知识点
    - 两级文件：depth1 主题 / depth ≥ 2 知识点（章留给模型分组）
    - 一级文件：depth1 主题（KP 由模型从正文提炼）
    用**树深度**而不是标题级别判定，跳级处就不会出现"有 KP 无主题"的空档。
    """
    has_chapters = span >= _MAX_TIER
    chapters: list[dict[str, Any]] = []
    flat_topics: list[dict[str, Any]] = []
    counter = {"n": 0}

    def base(node: dict[str, Any], prefix: str, chapter: str) -> dict[str, Any]:
        order = counter["n"]
        counter["n"] = order + 1
        return {
            "id": f"{prefix}{order:04d}",
            "name": node["name"],
            "raw_name": node.get("raw_name") or node["name"],
            "order": order,
            "page": (node.get("span") or "").split("-")[0],
            "page_span": node.get("span") or "",
            "chapter": chapter,
            "body": "\n".join(node.get("_body") or []).strip(),
        }

    def fold_deeper(node: dict[str, Any], target: dict[str, Any]) -> None:
        """第 4 层及更深：标题与正文一并折进当前 KP 的正文（内容不丢，语义归上一层）。"""
        extra = node["name"] + "\n" + "\n".join(node.get("_body") or [])
        target["body"] = (target["body"] + "\n" + extra).strip()
        stats["folded_deep"] += 1
        for child in node.get("_children") or []:
            fold_deeper(child, target)

    def visit(node: dict[str, Any], depth: int, chapter: str, topic: str) -> None:
        children = node.get("_children") or []
        if has_chapters and depth == 1:
            chapter_node = base(node, "sk_c", "")
            chapter_node["topics"] = []
            chapters.append(chapter_node)
            for child in children:
                visit(child, 2, chapter_node["name"], "")
            return
        if (has_chapters and depth == 2) or (not has_chapters and depth == 1):
            topic_node = base(node, "sk_t", chapter)
            topic_node["points"] = []
            flat_topics.append(topic_node)
            if chapters:
                chapters[-1]["topics"].append(topic_node)
            for child in children:
                visit(child, depth + 1, chapter, topic_node["name"])
            return
        # 知识点层
        holder = next((t for t in reversed(flat_topics) if t["name"] == topic), None)
        if holder is None:
            if not flat_topics:
                return  # 没有可挂的主题（异常输入）：跳过，避免产生游离节点
            holder = flat_topics[-1]
        point = base(node, "sk_p", holder.get("chapter", chapter))
        point["topic"] = holder["name"]
        holder["points"].append(point)
        for child in children:
            fold_deeper(child, point)

    for root in roots:
        visit(root, 1, "", "")
    return chapters, flat_topics


def parse_md_skeleton(text: str, *, source: str = "") -> dict[str, Any]:
    """md 文本 → 骨架（纯函数，可单测）。

    栈式标题树 + 确定性修补（续页合并 / 同名同级合并 / 跳级归位 / 名字去序号），
    层级映射按文件层级数归一。返回 ``{source, chapters, topics, stats}``；
    ``topics`` 是扁平视图（兼容既有消费方），带 ``chapter`` 字段。
    """
    lines = (text or "").splitlines()
    heads, dropped = _collect_headings(text)
    roots, jumps = _build_tree(heads, lines)
    stats = {
        "merged_continued": 0,
        "merged_same_name": 0,
        "level_jumps": jumps,
        "folded_deep": 0,
        "dropped_item_headings": dropped,
    }
    _repair_tree(roots, stats)
    levels = {head["level"] for head in heads}
    span = (max(levels) - min(levels) + 1) if levels else 1
    chapters, topics = _map_tiers(roots, span, stats)
    stats.update(
        {
            "levels": sorted(levels),
            "span": span,
            "chapters": len(chapters),
            "topics": len(topics),
            "points": sum(len(t["points"]) for t in topics),
            "max_kp_per_topic": max((len(t["points"]) for t in topics), default=0),
        }
    )
    logger.info(
        "skeleton parsed source=%s span=%d chapters=%d topics=%d points=%d (continued=%d same_name=%d jumps=%d)",
        source or "(inline)", span, stats["chapters"], stats["topics"], stats["points"],
        stats["merged_continued"], stats["merged_same_name"], stats["level_jumps"],
    )
    return {"source": source, "chapters": chapters, "topics": topics, "stats": stats}


def _ocr_md_paths(user_id: str, subject: str) -> list[Path]:
    """该用户/学科下的 OCR 合并稿（按修改时间从旧到新＝文件序）。"""
    from tools.memory.store import safe_id

    folder = _SOURCE / "data" / safe_id(user_id) / "ocr" / safe_id(subject)
    if not folder.is_dir():
        return []
    files = [p for p in folder.glob("ocr_*.md") if p.is_file()]
    return sorted(files, key=lambda p: (p.stat().st_mtime, p.name))


def build_catalog_skeleton(shared_context: str) -> dict[str, Any]:
    """按上下文定位并解析原文 → 合并成一份骨架（文件序 → 页序 → 节序）。

    来源优先取 OCR 合并稿（学生笔记）；KB 里另有资料时后续再接（PPT/PDF 各自有序）。
    解析不到（老数据/无文件）时返回空骨架，调用方回退旧路径（候选池照旧生效）。
    """
    from .gather import subject_from_context, user_id_from_context

    user_id = user_id_from_context(shared_context)
    subject = subject_from_context(shared_context)
    merged: dict[str, Any] = {
        "source": "", "sources": [], "chapters": [], "topics": [], "stats": {}
    }
    stats: dict[str, int] = {
        "dropped_item_headings": 0, "merged_continued": 0, "merged_same_name": 0,
        "level_jumps": 0, "folded_deep": 0,
    }
    kinds: list[str] = []
    level_set: set[int] = set()
    spans: list[int] = []
    for path in _ocr_md_paths(user_id, subject):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not text.strip():
            continue
        part = parse_md_skeleton(text, source=path.name)
        if not part["topics"]:
            continue
        for key in stats:
            stats[key] += int(part["stats"].get(key) or 0)
        # 页块/文件顺序：章、主题、知识点各自的 order 统一重排，保证全局单调可用
        base = len(merged["topics"])
        for topic in part["topics"]:
            topic["file"] = path.name
            topic["id"] = f"sk_t{base + len(merged['topics']) + 1:04d}"
            for point in topic["points"]:
                point["file"] = path.name
            merged["topics"].append(topic)
        for chapter in part.get("chapters") or []:
            chapter["file"] = path.name
            chapter["id"] = f"sk_c{len(merged['chapters']) + 1:04d}"
            chapter["topics"] = [
                t for t in chapter.get("topics") or [] if t in merged["topics"]
            ]
            merged["chapters"].append(chapter)
        kinds.append("md")
        level_set.update(part["stats"].get("levels") or [])
        spans.append(int(part["stats"].get("span") or 1))
        merged["sources"].append(path.name)
    merged["source"] = "、".join(merged["sources"])
    merged["kind"] = "md" if kinds else ""
    merged["stats"] = {
        **stats,
        "files": len(merged["sources"]),
        "levels": sorted(level_set),
        "span": max(spans) if spans else 0,
        "chapters": len(merged["chapters"]),
        "topics": len(merged["topics"]),
        "points": sum(len(t["points"]) for t in merged["topics"]),
        "max_kp_per_topic": max((len(t["points"]) for t in merged["topics"]), default=0),
    }
    return merged


def _position_tuple(meta: dict[str, Any]) -> tuple[str, int, int, int]:
    """Knowledge chunk 的稳定位置：source -> page -> chunk_index。"""
    source = str(meta.get("source") or "")
    nums = [int(x) for x in re.findall(r"\d+", str(meta.get("page") or ""))]
    page = nums[0] if nums else 10**9
    ci = [int(x) for x in re.findall(r"\d+", str(meta.get("chunk_index") or ""))]
    major = ci[0] if ci else 10**9
    minor = ci[1] if len(ci) > 1 else 0
    return source, page, major, minor


def _virtual_confidence(meta: dict[str, Any], title: str) -> str:
    """把入库 metadata 的标题质量转成骨架约束强度。"""
    try:
        score = int(str(meta.get("heading_score") or "0") or "0")
    except (TypeError, ValueError):
        score = 0
    kind = str(meta.get("heading_kind") or "")
    if score >= 6 or kind in {"chapter", "topic"}:
        return "high"
    if score >= 4 or kind == "knowledge_point":
        return "medium"
    if title and not is_item_heading(title):
        return "low"
    return "item_only"


def _merge_body(target: dict[str, Any], text: str, limit: int = 800) -> None:
    body = " ".join(str(text or "").split())
    if not body:
        return
    old = str(target.get("body") or "")
    if body in old:
        return
    joined = (old + "\n" + body).strip()
    target["body"] = joined[:limit]


def build_metadata_skeleton(shared_context: str) -> dict[str, Any]:
    """没有 OCR Md 时，从知识库 chunk metadata 构造一份虚拟骨架。

    这不是 Md 那种强骨架：只把 high / medium 结构信号纳入主题或 KP；
    低可信、例题、注意、小结等内容留作 evidence/body，不强行升节点。
    """
    from .gather import subject_from_context, user_id_from_context
    from tools.knowledge.cite import open_knowledge

    user_id = user_id_from_context(shared_context)
    subject = subject_from_context(shared_context)
    try:
        kb = open_knowledge(user_id=user_id)
        rows = list(kb.list_chunks(user_id=user_id, subject=subject) or []) if kb else []
    except Exception:  # noqa: BLE001 - 元数据骨架失败时回到空骨架
        logger.warning("metadata skeleton build failed", exc_info=True)
        rows = []
    chunks = [
        row for row in rows
        if isinstance(row, dict) and isinstance(row.get("metadata") or {}, dict)
    ]
    chunks.sort(key=lambda row: _position_tuple(row.get("metadata") or {}))
    topics: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    current_by_source: dict[str, dict[str, Any]] = {}
    order = 0
    dropped = 0
    sources: list[str] = []
    for row in chunks:
        meta = row.get("metadata") or {}
        source = str(meta.get("source") or "")
        if source and source not in sources:
            sources.append(source)
        path_text = str(meta.get("heading_path_text") or "")
        path = [clean_title(p) for p in path_text.split("/") if clean_title(p)]
        heading = clean_title(meta.get("heading") or "")
        chapter = clean_title(meta.get("chapter") or "")
        topic_name = clean_title(meta.get("topic") or "")
        if not path:
            path = [p for p in (chapter, topic_name, heading) if p]
        title = path[-1] if path else heading
        if not title or is_item_heading(title):
            dropped += 1
            target = current_by_source.get(source)
            if target is not None:
                _merge_body(target, row.get("text") or "")
            continue
        confidence = _virtual_confidence(meta, title)
        if confidence == "item_only":
            dropped += 1
            continue
        if confidence == "low":
            target = current_by_source.get(source)
            if target is not None:
                _merge_body(target, f"{title}\n{row.get('text') or ''}")
            continue
        kind = str(meta.get("heading_kind") or "")
        # high/topic/chapter 信号作为主题；medium/knowledge_point 信号作为最近主题下的 KP。
        as_topic = kind in {"chapter", "topic"} or confidence == "high" or len(path) <= 1
        if as_topic:
            key = (source, norm_key(title))
            topic = by_key.get(key)
            if topic is None:
                topic = {
                    "id": f"sk_t{len(topics) + 1:03d}",
                    "name": title,
                    "order": order,
                    "page": str(meta.get("page") or ""),
                    "page_span": str(meta.get("page_span") or meta.get("page") or ""),
                    "points": [],
                    "body": "",
                    "file": source,
                    "virtual": True,
                    "confidence": confidence,
                }
                order += 1
                topics.append(topic)
                by_key[key] = topic
            _merge_body(topic, row.get("text") or "")
            current_by_source[source] = topic
            continue
        parent_title = path[-2] if len(path) >= 2 else topic_name
        parent = current_by_source.get(source)
        if parent_title:
            parent_key = (source, norm_key(parent_title))
            parent = by_key.get(parent_key) or parent
        if parent is None:
            parent = {
                "id": f"sk_t{len(topics) + 1:03d}",
                "name": parent_title or source or "资料结构",
                "order": order,
                "page": str(meta.get("page") or ""),
                "page_span": str(meta.get("page_span") or meta.get("page") or ""),
                "points": [],
                "body": "",
                "file": source,
                "virtual": True,
                "confidence": "medium",
            }
            order += 1
            topics.append(parent)
            by_key[(source, norm_key(parent["name"]))] = parent
            current_by_source[source] = parent
        pkey = norm_key(title)
        point = next((p for p in parent["points"] if norm_key(p.get("name")) == pkey), None)
        if point is None:
            point = {
                "id": f"sk_p{len(parent['points']) + 1:03d}",
                "name": title,
                "order": order,
                "page": str(meta.get("page") or ""),
                "page_span": str(meta.get("page_span") or meta.get("page") or ""),
                "parent": parent["name"],
                "body": "",
                "file": source,
                "virtual": True,
                "confidence": confidence,
            }
            order += 1
            parent["points"].append(point)
        _merge_body(point, row.get("text") or "")
    return {
        "source": "、".join(sources),
        "sources": sources,
        "topics": topics,
        "kind": "metadata",
        "stats": {
            "topics": len(topics),
            "points": sum(len(t.get("points") or []) for t in topics),
            "files": len(sources),
            "dropped_item_headings": dropped,
            "merged_continued": 0,
            "virtual": True,
        },
    }


def build_source_skeleton(shared_context: str) -> dict[str, Any]:
    """统一骨架入口：真实 Md 优先；没有 Md 时回退知识库 metadata 虚拟骨架。"""
    skeleton = build_catalog_skeleton(shared_context)
    if skeleton.get("topics"):
        skeleton["kind"] = "md"
        return skeleton
    return build_metadata_skeleton(shared_context)


def _name_variants(name: object) -> list[str]:
    """名字的多种写法变体：调用方各自的归一化口径不同（有的只去空白），
    位置表把变体都登记上，任何口径都能查到。含"去掉全部标点"一档，
    因为模型改写时常把 `补充：坐标系变换` 写成 `补充坐标系变换`。"""
    raw = re.sub(r"\s+", "", str(name or ""))
    out = {raw, norm_key(raw), core_key(raw), _CORE_SPLIT_RE.sub("", norm_key(raw))}
    return [v for v in out if v]


def skeleton_position_map(skeleton: dict[str, Any]) -> dict[str, int]:
    """骨架 → 名字键 → 位置序号（供目录保序；比 KB 元数据更准）。含章名。"""
    out: dict[str, int] = {}
    entries: list[tuple[object, object]] = []
    for chapter in skeleton.get("chapters") or []:
        entries.append((chapter.get("name"), chapter.get("order")))
    for topic in skeleton.get("topics") or []:
        entries.append((topic.get("name"), topic.get("order")))
        entries.extend((p.get("name"), p.get("order")) for p in topic.get("points") or [])
    for name, order in entries:
        for variant in _name_variants(name):
            out[variant] = min(out.get(variant, 10 ** 9), int(order or 0))
    return out


def _clip(text: str, limit: int = _BODY_PROMPT_LIMIT) -> str:
    blob = " ".join((text or "").split())
    return blob if len(blob) <= limit else blob[: limit - 1] + "…"


def skeleton_prompt_block(skeleton: dict[str, Any]) -> str:
    """骨架 → prompt 段（含允许/禁止操作契约）。空骨架返回空串。

    有章时按「章 → 主题 → 知识点」三级呈现（章的来源是原文一级标题）；
    无章时按「主题 → 知识点」两级呈现，并说明章由模型分组。
    """
    topics = skeleton.get("topics") or []
    chapters = skeleton.get("chapters") or []
    if not topics:
        return ""
    is_virtual = str(skeleton.get("kind") or "") == "metadata" or bool(
        (skeleton.get("stats") or {}).get("virtual")
    )
    title = "【来源结构骨架】" if is_virtual else "【原文骨架（权威）】"
    stats = skeleton.get("stats") or {}
    if is_virtual:
        intro = (
            "下面是从 PPT/DOC/TXT/PDF 入库 metadata 还原出的结构骨架，"
            "**高/中可信标题用于约束覆盖和顺序**；章可由你按语义分组。"
        )
    elif chapters:
        intro = (
            "下面是原文（学生笔记）里**按标题层级逐节解析**出的三级骨架，"
            f"**章/主题/知识点的名字、顺序、覆盖全部以它为准**（原文 {stats.get('chapters', len(chapters))} 个一级标题）。"
        )
    else:
        intro = (
            "下面是原文（学生笔记）里**逐节解析**出的骨架，"
            "**主题与知识点的名字、顺序、覆盖以它为准**；原文只有两级，章由你按语义分组。"
        )
    lines = [
        title + intro,
        f"来源：{skeleton.get('source') or '（未知）'}"
        f"（{len(chapters)} 章 / {len(topics)} 主题 / {stats.get('points', 0)} 知识点）",
    ]

    def render_point(point: dict[str, Any], indent: str) -> None:
        pconf = f" confidence={point.get('confidence')}" if is_virtual and point.get("confidence") else ""
        lines.append(
            f"{indent}· [P kp order={point.get('order')} 页{point.get('page_span') or '-'}{pconf}] "
            f"{point.get('name')}"
        )
        if point.get("body"):
            lines.append(f"{indent}    正文：{_clip(point['body'])}")

    def render_topic(topic: dict[str, Any], indent: str) -> None:
        conf = f" confidence={topic.get('confidence')}" if is_virtual and topic.get("confidence") else ""
        lines.append(
            f"{indent}[T topic order={topic.get('order')} 页{topic.get('page_span') or '-'}{conf}] "
            f"{topic.get('name')}"
            + ("（原文标注续页，已与上文合并）" if topic.get("continued") else "")
        )
        if topic.get("body"):
            lines.append(f"{indent}    正文：{_clip(topic['body'])}")
        points = topic.get("points") or []
        if not points:
            lines.append(f"{indent}    （原文这一节没有子标题：请从上面的正文提炼 1 个 KP）")
        for point in points:
            render_point(point, indent + "  ")

    if chapters:
        for chapter in chapters:
            cconf = f" confidence={chapter.get('confidence')}" if is_virtual and chapter.get("confidence") else ""
            lines.append(
                f"[C chapter order={chapter.get('order')} 页{chapter.get('page_span') or '-'}{cconf}] "
                f"{chapter.get('name')}"
            )
            if chapter.get("body"):
                lines.append(f"    正文：{_clip(chapter['body'])}")
            chapter_topics = chapter.get("topics") or []
            if not chapter_topics:
                lines.append("    （原文这一章没有子标题：请从上面的正文提炼 1 个主题 + 1 个 KP）")
            for topic in chapter_topics:
                render_topic(topic, "  ")
    else:
        for topic in topics:
            render_topic(topic, "")
    rule_lines = [
        "【骨架契约（中强约束）】" if is_virtual else "【骨架契约（硬约束）】",
        "- 必须覆盖骨架里**每一个** C（章，若有）/ T（主题）/ P（知识点）：名字可规范化改写，但不许丢、"
        "不许合并掉（要合并只能把 P 降级为父主题的 knowledge_items，名字仍要出现在 items 里）；",
        "- 可以新增明显来自资料 metadata 的必要节点，但不要把低可信标题、页眉页脚、正文句子升成节点；"
        if is_virtual else (
            "- 章一律沿用骨架给出的章名与顺序（可把相邻的章合并成一个更概括的章，但不许新增骨架外主题/知识点）；"
            if chapters else
            "- 不许新增骨架里没有的主题/知识点（章可以新增，用来分组主题）；"
        ),
        "- 顺序必须跟骨架 order 走：章按「其下最早节点」排序，主题/知识点按 order 升序；",
        "- 骨架里没有子标题的主题/章（提示「请从正文提炼」）由你补 1 个 KP（章还要先补 1 个主题），"
        "名字从该节正文提炼；",
        f"- 辅助性内容（{'、'.join(item_marks()[:8])} 等类别）不进层级，收进所属节点的 knowledge_items。",
    ]
    lines.append("\n".join(rule_lines))
    block = "\n".join(lines)
    if len(block) > _MD_PROMPT_LIMIT:
        block = block[:_MD_PROMPT_LIMIT] + "\n…（骨架过长已截断：**未出现的节点仍必须建**，按上文顺序续排）"
    return block


# ── 骨架权威校验（LLM 输出之后，零 LLM）──────────────────────

def _draft_name_keys(draft: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            key = norm_key(topic.get("name"))
            if key:
                keys.add(key)
            for kp in topic.get("knowledge_points") or []:
                if not isinstance(kp, dict):
                    continue
                key = norm_key(kp.get("name"))
                if key:
                    keys.add(key)
    return keys


def _draft_item_blobs(draft: dict[str, Any]) -> list[str]:
    blobs: list[str] = []
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for kp in topic.get("knowledge_points") or []:
                if not isinstance(kp, dict):
                    continue
                for item in kp.get("knowledge_items") or []:
                    if isinstance(item, dict):
                        blob = " ".join(str(item.get(k) or "") for k in ("name", "text", "title"))
                    else:
                        blob = str(item or "")
                    if blob.strip():
                        blobs.append("".join(blob.split()))
    return blobs


def _covered(key: str, name_keys: set[str], item_blobs: list[str]) -> bool:
    """覆盖判定：名字出现在任意层级节点名，或出现在某个知识点的 items 里（= 降级）。

    严格键没命中时再看核心键（去圈号 + 取首个标点前的部分），避免"写法差异"被误判成缺口。
    """
    if not key:
        return True
    if key in name_keys:
        return True
    core = core_key(key)
    if len(core) >= 2 and core in name_keys:
        return True
    for blob in item_blobs:
        if key in blob or (len(core) >= 2 and core in blob):
            return True
    return False


def _skeleton_orders(skeleton: dict[str, Any]) -> dict[str, int]:
    return skeleton_position_map(skeleton)


def _host_chapter(draft: dict[str, Any], orders: dict[str, int], limit: int) -> dict[str, Any]:
    """缺失节点的章归属：取"其下已有节点的骨架位置最靠前且 < limit"的那个章。"""
    chapters = [c for c in (draft.get("chapters") or []) if isinstance(c, dict)]
    best: tuple[int, dict[str, Any]] | None = None
    for chapter in chapters:
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            names = [topic.get("name")] + [
                kp.get("name") for kp in topic.get("knowledge_points") or [] if isinstance(kp, dict)
            ]
            for name in names:
                pos = orders.get(norm_key(name))
                if pos is None or pos >= limit:
                    continue
                if best is None or pos > best[0]:
                    best = (pos, chapter)
    return best[1] if best else (chapters[0] if chapters else {})


def restore_from_skeleton(
    draft: dict[str, Any],
    skeleton: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """按骨架补齐 + 记录报告（零 LLM）。只增不减：不动模型已有节点，只补缺失。

    有章时先保证章存在（缺则建章），再把主题挂到**同名章**下（骨架给了明确的章归属，
    不再靠"最近位置"猜）；无章时沿用"按位置找宿主章"的旧逻辑。

    报告字段：``restored_chapters`` / ``restored_topics`` / ``restored_points`` /
    ``merged_topics`` / ``demoted_kept`` / ``llm_added``。
    """
    report: dict[str, Any] = {
        "restored_chapters": [],
        "restored_topics": [],
        "restored_points": [],
        "merged_topics": [],
        "demoted_kept": [],
        "llm_added": 0,
    }
    topics = skeleton.get("topics") or []
    if not topics or not draft.get("chapters"):
        return draft, report
    orders = _skeleton_orders(skeleton)
    name_keys = _draft_name_keys(draft)
    item_blobs = _draft_item_blobs(draft)
    skeleton_keys = set(orders)
    report["llm_added"] = len([k for k in name_keys if k not in skeleton_keys])
    next_tp = _next_no(draft, "tp")
    next_kp = _next_no(draft, "kp")
    next_ch = _next_no(draft, "ch")
    chapters = [c for c in draft.get("chapters") or [] if isinstance(c, dict)]

    def chapter_by_name(name: str) -> dict[str, Any] | None:
        key = norm_key(name)
        return next(
            (c for c in chapters if key and norm_key(c.get("name")) == key), None
        )

    def ensure_chapter(
        name: str, topic_for_host: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """骨架给了章名 → 缺则建章；返回该章（没有可用宿主时返回 None）。"""
        nonlocal next_ch
        existing = chapter_by_name(name) if name else None
        if existing is not None:
            return existing
        if not name:
            return None
        created = {
            "id": f"ch_{next_ch:03d}",
            "name": name,
            "change_type": "added",
            "node_status": "program_restore",
            "topics": [],
        }
        next_ch += 1
        chapters.append(created)
        draft["chapters"] = chapters
        name_keys.add(norm_key(name))
        report["restored_chapters"].append(name)
        return created

    for chapter in skeleton.get("chapters") or []:
        # 章：骨架给了章名就必须存在（没有子标题的章也要建，否则整章内容无处安放）
        ensure_chapter(str(chapter.get("name") or ""))

    for topic in topics:
        tkey = norm_key(topic.get("name"))
        points = list(topic.get("points") or [])
        missing_points = [
            p for p in points
            if not _covered(norm_key(p.get("name")), name_keys, item_blobs)
        ]
        report["demoted_kept"].extend(
            norm_key(p.get("name"))
            for p in points
            if norm_key(p.get("name")) not in name_keys
            and _covered(norm_key(p.get("name")), name_keys, item_blobs)
        )
        topic_covered = _covered(tkey, name_keys, item_blobs)
        if topic_covered and not missing_points:
            continue
        if not topic_covered and points and not missing_points:
            # 模型把这个主题拆散/并入别处（其下知识点都还在）→ 认作"合并"，
            # 不重建空壳主题（覆盖判定同样把这种情况算覆盖）
            report["merged_topics"].append(topic["name"])
            continue
        host = None
        if skeleton.get("chapters"):
            host = ensure_chapter(str(topic.get("chapter") or ""))
        if host is None:
            host = _host_chapter(draft, orders, int(topic.get("order") or 0))
        if not host:
            continue
        target_topic = next(
            (
                t
                for t in host.get("topics") or []
                if isinstance(t, dict) and norm_key(t.get("name")) == tkey
            ),
            None,
        )
        if target_topic is None:
            target_topic = {
                "id": f"tp_{next_tp:03d}",
                "name": topic["name"],
                "change_type": "added",
                "node_status": "program_restore",
                "knowledge_points": [],
            }
            next_tp += 1
            host.setdefault("topics", []).append(target_topic)
            name_keys.add(tkey)
            report["restored_topics"].append(topic["name"])
        # 骨架里"只有正文、没有子标题"的主题：**不造占位名**（曾经写 `核心知识点`）。
        # 结构修复器紧跟其后（catalog_agent 里 restore → _repair_catalog_structure），
        # 会用主题真名回退补点，名字全部来自原文。
        for point in missing_points:
            target_topic.setdefault("knowledge_points", []).append(
                {
                    "id": f"kp_{next_kp:03d}",
                    "name": point["name"],
                    "aliases": [],
                    "knowledge_type": "concept",
                    "knowledge_items": [],
                    "importance": "2",
                    "difficulty": "3",
                    "teacher_emphasis": 0,
                    "change_type": "added",
                    "node_status": "program_restore",
                    "sources": [],
                    "prerequisites": [],
                    "related_points": [],
                    "risk_tags": [],
                    "completion_criteria": [],
                    "exam_signal": "none",
                    "topic": str(target_topic.get("name") or ""),
                    "chapter": str(host.get("name") or ""),
                }
            )
            name_keys.add(norm_key(point.get("name")))
            next_kp += 1
            report["restored_points"].append(point["name"])
    if report["restored_chapters"] or report["restored_topics"] or report["restored_points"]:
        logger.info(
            "catalog restore from skeleton chapters=%d topics=%d points=%d",
            len(report["restored_chapters"]),
            len(report["restored_topics"]),
            len(report["restored_points"]),
        )
    if report["llm_added"]:
        logger.info("catalog nodes not in skeleton (kept) n=%d", report["llm_added"])
    return draft, report


def _next_no(draft: dict[str, Any], prefix: str) -> int:
    pattern = re.compile(rf"{prefix}_(\d+)")
    max_no = 0
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for node in [chapter] + [t for t in chapter.get("topics") or [] if isinstance(t, dict)]:
            m = pattern.search(str(node.get("id") or ""))
            if m:
                max_no = max(max_no, int(m.group(1)))
            for kp in node.get("knowledge_points") or [] if isinstance(node, dict) else []:
                if isinstance(kp, dict):
                    m = pattern.search(str(kp.get("id") or ""))
                    if m:
                        max_no = max(max_no, int(m.group(1)))
    return max_no + 1


# ── 第三道校验：知识点的内容是否来自它自己那一节（零 LLM）──────────

_WS_RE = re.compile(r"\s+")
_LATEX_NOISE_RE = re.compile(r"[\\${}\[\]()（）{}^_|,，.。:：;；!！?？'\"“”‘’·、\-+=*/<>~`]+")
_QUOTE_MIN = 12      # 长条目（引用型）门槛：短标签无法逐字核对，不判对错
_ITEM_RUN = 8        # 逐字命中长度（引用型条目）
_ITEM_NGRAM = 3      # 概述型条目的片段长度
_ITEM_NGRAM_HIT = 3  # 至少多少个片段命中才算"有依据"


def _compact_match(text: object) -> str:
    return _WS_RE.sub("", str(text or ""))


def _match_core(text: object) -> str:
    """公式友好的比对核：去掉 LaTeX 定界符与标点，只留字母数字与汉字。"""
    return _LATEX_NOISE_RE.sub("", _compact_match(text))


def _has_run(item: str, window: str, run: int) -> bool:
    """item 是否在 window 里有一段 ≥run 的连续命中（短 item 要求整条命中）。"""
    if not item or not window:
        return False
    if len(item) <= run:
        return item in window
    return any(item[i:i + run] in window for i in range(len(item) - run + 1))


def _ngram_hits(item: str, window: str, n: int = _ITEM_NGRAM) -> int:
    """片段命中数：概述型条目（"守恒量定义"）逐字比不上，看三字片段重合度。"""
    if not item or not window:
        return 0
    if len(item) <= n:
        return 1 if item in window else 0
    return sum(1 for i in range(len(item) - n + 1) if item[i:i + n] in window)


def _need_hits(item_len: int, n: int = _ITEM_NGRAM) -> int:
    """片段命中阈值随条目长度自适应：短条目本来就没几个片段，阈值不能一刀切 3。"""
    grams = max(1, item_len - n + 1)
    return max(1, min(_ITEM_NGRAM_HIT, (grams + 1) // 2))


def _item_level(item: str, window: str) -> str:
    """条目依据强度：``strong``（逐字命中正文）/ ``weak``（概述型，片段重合）/ ``miss``。"""
    if not item or not window:
        return "miss"
    if _has_run(item, window, _ITEM_RUN):
        return "strong"
    core = _match_core(item)
    if core and _has_run(core, _match_core(window), _ITEM_RUN // 2):
        return "strong"
    if _ngram_hits(item, window) >= _need_hits(len(item)):
        return "weak"
    if core and _ngram_hits(core, _match_core(window)) >= _need_hits(len(core)):
        return "weak"
    return "miss"


_CONT_TAIL_RE = re.compile(r"[（(]?\s*续\s*[）)]?$")


def _index_lookup(index: dict[str, str], name: object) -> str:
    """在正文索引里查节点窗口：兼容"（续）"后缀与序号/标点写法差异。

    目录里可能还挂着 `X（续）`，而骨架已把它并入 `X`——
    不做这层兼容会把整节的条目误判成串门。
    """
    raw = clean_title(name)
    for candidate in (
        raw,
        _CONT_TAIL_RE.sub("", raw).strip(),
        _CIRCLED_RE.sub("", raw).strip(),
    ):
        for key in (norm_key(candidate), core_key(candidate)):
            if key and key in index:
                return index[key]
    return ""


def _compete_index(skeleton: dict[str, Any]) -> dict[str, str]:
    """竞争用索引：只放**具体小节**的正文（主题只算它自己的正文，不带子树）。

    否则"主题子树"（含其下全部知识点）窗口最大，任何条目都会"更像那个主题"，
    串门结论既不准也没法读。用具体小节竞争，结论才能落到"更像哪一节"。
    """
    index: dict[str, str] = {}
    for topic in skeleton.get("topics") or []:
        topic_body = _compact_match(topic.get("body"))
        topic_key = norm_key(topic.get("name"))
        if topic_key and topic_body:
            index[topic_key] = topic_body
        for point in topic.get("points") or []:
            key = norm_key(point.get("name"))
            if not key:
                continue
            own = _compact_match(point.get("body"))
            if own or topic_body:
                index[key] = own + topic_body
    return index


def _content_index(skeleton: dict[str, Any]) -> dict[str, str]:
    """名字键 → 可核对正文窗口。

    - 主题：本节正文 + 其下所有知识点正文（主题正文常为空，材料都在子节点里）；
    - 知识点：自己的正文 + 所属主题正文；自己正文为空时退到主题子树，
      否则"主题下并列的 KP"会被误判成串门。
    """
    index: dict[str, str] = {}
    for chapter in skeleton.get("chapters") or []:
        # 章级窗口 = 整章子树（KP 若直接挂在"同名章"下，也应有依据可核）
        chapter_body = _compact_match(chapter.get("body"))
        chapter_key = norm_key(chapter.get("name"))
        if chapter_key:
            index.setdefault(chapter_key, chapter_body)
    for topic in skeleton.get("topics") or []:
        topic_body = _compact_match(topic.get("body"))
        points = topic.get("points") or []
        subtree = topic_body + "".join(_compact_match(p.get("body")) for p in points)
        topic_key = norm_key(topic.get("name"))
        if topic_key:
            index[topic_key] = subtree
        for point in points:
            key = norm_key(point.get("name"))
            if not key:
                continue
            own = _compact_match(point.get("body"))
            index[key] = (own + topic_body) if own else subtree
    return index


def _all_bodies(skeleton: dict[str, Any]) -> str:
    parts = [str(t.get("body") or "") for t in skeleton.get("topics") or []]
    for topic in skeleton.get("topics") or []:
        parts.extend(str(p.get("body") or "") for p in topic.get("points") or [])
    return _compact_match("\n".join(parts))


def _score_item(item: str, window: str) -> int:
    """条目对某节正文的匹配分：3=逐字命中、2=概述型、0=无。"""
    return {"strong": 3, "weak": 2, "miss": 0}[_item_level(item, window)]


def verify_catalog_content(draft: dict[str, Any], skeleton: dict[str, Any]) -> dict[str, Any]:
    """核对 items 与原文的关系（第三道校验，零 LLM）。

    粒度选择（中文里 4 字片段遍地都是，逐条判"串门"信噪比极差）：

    - **条目级**只判"有没有依据"：``strong``（逐字命中本节）/ ``weak``（概述型，片段重合）
      / ``unverified``（全篇找不到痕迹 = 疑似编造）；
    - **节点级**才判"串门"：某个 KP 的多数条目最佳匹配落在**别节**（≥2 条且 ≥60%）
      → 记 ``misplaced_nodes``，这才是"整节内容挂错地方"（某节的内容整批挂在另一节下）。

    只标记不删除：概述型条目逐字比不上是常态，硬删会误伤；计数进 monitor 供你决定是否重跑。
    """
    report: dict[str, Any] = {
        "checked": 0,
        "strong": 0,
        "weak": 0,
        "labels": 0,
        "unverified": [],
        "misplaced_nodes": [],
    }
    topics = skeleton.get("topics") or []
    if not topics:
        return report
    index = _content_index(skeleton)
    compete = _compete_index(skeleton)
    whole = _all_bodies(skeleton)
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for kp in topic.get("knowledge_points") or []:
                if not isinstance(kp, dict):
                    continue
                point_key = norm_key(kp.get("name"))
                topic_key = norm_key(topic.get("name"))
                own_window = _index_lookup(index, kp.get("name")) or _index_lookup(
                    index, topic.get("name")
                )
                own_name = (
                    point_key if _index_lookup(index, kp.get("name")) == own_window and own_window
                    else (topic_key if own_window else "")
                )
                best: dict[str, int] = {}
                for item in kp.get("knowledge_items") or []:
                    text = item if isinstance(item, str) else " ".join(
                        str(item.get(k) or "") for k in ("name", "text", "title")
                    )
                    text = _compact_match(text)
                    if not text:
                        continue
                    report["checked"] += 1
                    level = _item_level(text, own_window)
                    if level != "miss":
                        report[level] += 1
                        continue
                    winner, score = "", 0
                    for name, body in compete.items():
                        s = _score_item(text, body)
                        if s > score:
                            winner, score = name, s
                    if score >= 2:
                        # 本节没有依据，但别节有 → 累计到节点级"串门"判定
                        best[winner] = best.get(winner, 0) + 1
                    elif _item_level(text, whole) != "miss":
                        report["weak"] += 1  # 全篇有痕迹，只是定位不到具体节
                    elif len(text) >= _QUOTE_MIN:
                        # 长条目像引用却全篇找不到 → 可执行的存疑信号
                        report["unverified"].append(
                            {
                                "chapter": str(chapter.get("name") or ""),
                                "topic": str(topic.get("name") or ""),
                                "point": str(kp.get("name") or ""),
                                "item": text[:60],
                            }
                        )
                    else:
                        report["labels"] += 1  # 短标签（模型的命名），文本上无法核对
                if best:
                    winner, hits = max(best.items(), key=lambda kv: kv[1])
                    matched = sum(best.values())
                    if winner and winner != own_name and hits >= 2 and hits / matched >= 0.6:
                        report["misplaced_nodes"].append(
                            {
                                "point": str(kp.get("name") or ""),
                                "belongs_to": winner,
                                "items": hits,
                                "matched": matched,
                            }
                        )
    return report


def catalog_quality_report(skeleton: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    """目录体检（覆盖 + 同级顺序 + 内容可核）——CLI 与接口 monitor 共用同一实现。

    参数顺序与工具链一致：``(骨架, 目录)``。
    返回结构化明细 + ``metrics``（一行式摘要，进响应体的 monitor.catalog）。
    """
    topics = skeleton.get("topics") or []
    nodes: list[dict[str, Any]] = []
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        nodes.append({"level": "章", "name": str(chapter.get("name") or "")})
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            nodes.append({"level": "主题", "name": str(topic.get("name") or "")})
            for kp in topic.get("knowledge_points") or []:
                if not isinstance(kp, dict):
                    continue
                items = []
                for item in kp.get("knowledge_items") or []:
                    items.append(
                        " ".join(str(item.get(k) or "") for k in ("name", "text"))
                        if isinstance(item, dict) else str(item or "")
                    )
                nodes.append(
                    {
                        "level": "KP",
                        "name": str(kp.get("name") or ""),
                        "status": str(kp.get("node_status") or ""),
                        "items": _compact_match(" ".join(items)),
                    }
                )
    name_keys = {norm_key(n["name"]) for n in nodes if norm_key(n["name"])}
    core_keys = {core_key(n["name"]) for n in nodes if len(core_key(n["name"])) >= 2}
    item_blobs = [n.get("items") or "" for n in nodes]

    def covered(name: str) -> bool:
        key = norm_key(name)
        if not key:
            return True
        if key in name_keys:
            return True
        core = core_key(name)
        if len(core) >= 2 and core in core_keys:
            return True
        return any(key in blob or (len(core) >= 2 and core in blob) for blob in item_blobs)

    uncovered_topics: list[str] = []
    uncovered_points: list[str] = []
    uncovered_chapters: list[str] = []
    demoted: list[str] = []
    merged_topics: list[str] = []
    # 章：骨架给了章名就必须出现（P5 起章来自原文一级标题）
    for chapter in skeleton.get("chapters") or []:
        if not covered(str(chapter.get("name") or "")):
            uncovered_chapters.append(str(chapter.get("name") or ""))
    for topic in topics:
        points = topic.get("points") or []
        missing = [p for p in points if not covered(p["name"])]
        demoted.extend(
            p["name"] for p in points
            if norm_key(p["name"]) not in name_keys and covered(p["name"])
        )
        if not covered(topic["name"]):
            if points and not missing:
                merged_topics.append(topic["name"])
            else:
                uncovered_topics.append(topic["name"])
        uncovered_points.extend(p["name"] for p in missing)

    order: dict[str, int] = {}
    dup_names: set[str] = set()
    # 章名先入表（P5 起章来自原文，是位置轴的第一段）
    for chapter in skeleton.get("chapters") or []:
        key = norm_key(chapter.get("name"))
        if key:
            order[key] = int(chapter.get("order") or 0)
    for topic in topics:
        for name, value in [(topic["name"], topic.get("order"))] + [
            (p["name"], p.get("order")) for p in topic.get("points") or []
        ]:
            key = norm_key(name)
            if not key:
                continue
            value = int(value or 0)
            if key in order:
                # 同名出现在多处（如章与同名主题、两处「证明」）：取最早位置，
                # 记进 dup_names 只为让全局遍历判定忽略歧义（同级判定仍用最小值）
                dup_names.add(key)
                order[key] = min(order[key], value)
                continue
            order[key] = value

    def pos_of(name: str) -> int | None:
        return order.get(norm_key(name))

    level_violations: list[str] = []
    chapter_positions: list[tuple[int, str]] = []
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        topic_pos = [
            p for p in (
                [pos_of(t.get("name")) for t in chapter.get("topics") or [] if isinstance(t, dict)]
            )
            if p is not None
        ]
        # 章的位置：优先其下最早节点；没有可判定子节点时退回章名自身位置
        # （P5 起章来自原文一级标题，"没有子标题的章"是正常形态，不能给 10**9）
        own = pos_of(str(chapter.get("name") or ""))
        chapter_positions.append(
            (
                min(topic_pos) if topic_pos else (own if own is not None else 10 ** 9),
                str(chapter.get("name")),
            )
        )
        if topic_pos != sorted(topic_pos):
            level_violations.append(f"章「{chapter.get('name')}」内主题顺序乱：{topic_pos}")
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            kp_pos = [
                p for p in (
                    [pos_of(kp.get("name")) for kp in topic.get("knowledge_points") or []
                     if isinstance(kp, dict)]
                )
                if p is not None
            ]
            if kp_pos != sorted(kp_pos):
                level_violations.append(f"主题「{topic.get('name')}」内 KP 顺序乱：{kp_pos}")
    chapter_seq = [p for p, _n in chapter_positions]
    if chapter_seq != sorted(chapter_seq):
        level_violations.append(f"章顺序乱：{[n for _p, n in chapter_positions]}")

    aligned = [
        (norm_key(n["name"]), n["name"]) for n in nodes if pos_of(n["name"]) is not None
    ]
    cross_jumps = [
        (order[aligned[i][0]], order[aligned[i + 1][0]], aligned[i + 1][1])
        for i in range(len(aligned) - 1)
        if order[aligned[i + 1][0]] < order[aligned[i][0]]
    ]
    content = verify_catalog_content(draft, skeleton)
    total = (
        len(skeleton.get("chapters") or [])
        + len(topics)
        + sum(len(t.get("points") or []) for t in topics)
    )
    missed = len(uncovered_chapters) + len(uncovered_topics) + len(uncovered_points)
    skeleton_keys = set(order) | {norm_key(c.get("name")) for c in skeleton.get("chapters") or []}
    llm_added = len([k for k in name_keys if k not in skeleton_keys])
    restored = sum(1 for n in nodes if n.get("status") == "program_restore")
    complemented = sum(1 for n in nodes if n.get("status") == "program_complement")
    kp_counts = [len(t.get("points") or []) for t in topics]
    # 占位名计数：按**形态**判定（taxonomy.is_placeholder_name，可配置），不枚举具体名字；
    # 结构侧的"凑层级"形状由 merge/_repair 各自的形状判定负责（父子同名、唯一子节点同名）
    generic_nodes = sum(
        1
        for chapter in draft.get("chapters") or []
        if isinstance(chapter, dict)
        for topic in chapter.get("topics") or []
        if isinstance(topic, dict)
        for name in [topic.get("name")] + [
            k.get("name") for k in topic.get("knowledge_points") or [] if isinstance(k, dict)
        ]
        if is_placeholder_name(name)
    )
    # 关系/重要性分布指标（P6）：关系空 → 图谱无边、importance 塌陷 → 分档退化，
    # 这两个数字就是那条因果链的哨兵
    kps_all = [
        kp
        for chapter in draft.get("chapters") or []
        if isinstance(chapter, dict)
        for topic in chapter.get("topics") or []
        if isinstance(topic, dict)
        for kp in topic.get("knowledge_points") or []
        if isinstance(kp, dict)
    ]
    relation_ready = sum(
        1 for kp in kps_all if kp.get("related_points") or kp.get("prerequisites")
    )
    importance_counts: dict[str, int] = {}
    for kp in kps_all:
        value = str(kp.get("importance") or "")
        importance_counts[value] = importance_counts.get(value, 0) + 1
    importance_single = (
        max(importance_counts.values()) / len(kps_all) if kps_all else 0.0
    )

    ok = not (uncovered_chapters or uncovered_topics or uncovered_points or level_violations)
    return {
        "nodes": nodes,
        "total": total,
        "missed": missed,
        "coverage": (total - missed) / max(1, total),
        "uncovered_chapters": uncovered_chapters,
        "uncovered_topics": uncovered_topics,
        "uncovered_points": uncovered_points,
        "demoted": demoted,
        "merged_topics": merged_topics,
        "dup_names": sorted(dup_names),
        "aligned": len(aligned),
        "level_violations": level_violations,
        "cross_jumps": cross_jumps,
        "content": content,
        "ok": ok,
        "metrics": {
            "coverage": f"{total - missed}/{total}",
            "order_violations": len(level_violations),
            "restored": restored,
            "complemented": complemented,
            "demoted": len(demoted),
            "merged": len(merged_topics),
            "llm_added": llm_added,
            "max_kp_per_topic": max(kp_counts, default=0),
            "relations_ratio": f"{relation_ready}/{len(kps_all)}",   # 有关系（前置或相关）的 KP 占比
            "importance_single_ratio": round(importance_single, 2),   # importance 单值占比（>0.6 说明结构信号塌陷）
            "verified_items": f"{content['strong'] + content['weak']}/{content['checked']}",
            "label_items": content["labels"],
            "misplaced_nodes": len(content["misplaced_nodes"]),
            "unverified_items": len(content["unverified"]),
            "generic_nodes": generic_nodes,
        },
    }


__all__ = [
    "build_catalog_skeleton",
    "build_metadata_skeleton",
    "build_source_skeleton",
    "parse_md_skeleton",
    "skeleton_prompt_block",
    "skeleton_position_map",
    "restore_from_skeleton",
    "verify_catalog_content",
    "catalog_quality_report",
    "clean_title",
    "norm_key",
    "core_key",
    "is_item_heading",
]
