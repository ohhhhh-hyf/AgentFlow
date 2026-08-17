"""资料入库：多文件写入指定知识库，并给出知识增量。"""
from __future__ import annotations

import os
import re
from html import escape
from pathlib import Path
from typing import Any

from tools.knowledge.document_processor import SUPPORTED_EXTS
from tools.knowledge.tool import KnowledgeTool

_FILE_MARK = "【入库文件】"
_UNIT_CAP = 12
_SENT_SPLIT = re.compile(r"(?<=[。！？；!\?\n])")
_STOP = set("的了在是和与及或对把被从到为以会可能进行相关问题情况这个我们没有可以一个")
_PUNCT = set("：:，,。；;！!？?、·()[]【】（）")
_TAIL = set("上占为了是的与和在把被从到以会")
_GENERIC_TOPIC = {
    "答案",
    "解析",
    "函数",
    "课前篇",
    "课前篇自",
    "课堂篇",
    "课标阐释",
    "内容索引",
    "当堂检测",
    "本课结束",
    "微判断",
    "微练习",
    "微思考",
    "探究学习",
    "自主预习",
    "f(x)",
    "奇函数",
    "偶函数",
    "函数答案",
    "函数c",
    "偶函数c",
    "偶函数d",
    "数学抽象",
    "数学运算",
    "逻辑推理",
    "思维脉络",
    "探究一",
    "探究二",
    "探究三",
    "给角求值",
    "给值求值",
    "给值求角",
    "公式解决",
    "式解决给",
    "式推导出",
    "推导出",
    "利用两角",
    "三利用两",
    "素养形成",
    "方法点睛",
    "反思感悟",
    "规范答题",
}
_HEADING_FRAG = (
    "探究",
    "课标",
    "脉络",
    "阐释",
    "给角",
    "给值",
    "素养",
    "当堂",
    "课堂篇",
    "内容索",
    "究一",
    "究二",
    "究三",
    "知识点",
)
_STRUCTURE_BLOBS = (
    "课前篇自主预习课堂篇探究学习内容索引",
    "课标阐释思维脉络",
    "当堂检测本课结束",
    "微判断微练习微思考",
    "反思感悟方法点睛素养形成规范答题",
    "知识点拨名师点析要点笔记",
    "高中同步学案优化设计第一PPT模板网",
    "当堂检测答案",
    "课前篇自主预习",
)


def source_paths_from_context(text: str) -> list[str]:
    raw = text or ""
    if _FILE_MARK not in raw:
        return []
    tail = raw.split(_FILE_MARK, 1)[1]
    paths: list[str] = []
    for line in tail.splitlines():
        item = line.strip().strip('"')
        if not item:
            if paths:
                break
            continue
        if item.startswith("【"):
            break
        paths.append(item)
    return paths


def expand_inputs(raw_paths: list[str | Path]) -> list[Path]:
    files: list[Path] = []
    for raw in raw_paths:
        path = Path(raw)
        if not path.exists():
            raise FileNotFoundError(f"入库路径不存在：{path}")
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTS:
                    files.append(child)
            continue
        if path.suffix.lower() not in SUPPORTED_EXTS:
            raise ValueError(f"不支持的文件格式：{path}")
        files.append(path)
    # 去重并保持顺序
    seen: set[str] = set()
    out: list[Path] = []
    for item in files:
        key = str(item.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lstrip("\ufeff"))


def _ngrams(text: str, size: int) -> set[str]:
    """按字取 n-gram（去空白后），用于相似度判断。"""
    blob = _compact(text)
    if not blob:
        return set()
    return {blob[i : i + size] for i in range(len(blob) - size + 1)}


def _units(text: str) -> list[str]:
    parts = [
        item.strip().lstrip("\ufeff")
        for item in _SENT_SPLIT.split(text or "")
        if item.strip()
    ]
    if not parts:
        blob = " ".join((text or "").split()).strip()
        return [blob] if blob else []
    return parts[:_UNIT_CAP]




def _is_independent(text: str, old_texts: list[str]) -> bool:
    blob = _compact(text)
    if len(blob) < 8:
        return False
    for old in old_texts:
        other = _compact(old)
        if not other:
            continue
        if blob in other or other in blob:
            return False
        grams = _ngrams(blob, 6)
        shared = grams & _ngrams(other, 6)
        if grams and len(shared) / len(grams) >= 0.55:
            return False
    return True


def _topic_score(label: str) -> tuple[int, int, int, int]:
    tail = 1 if label and label[-1] in _TAIL else 0
    digit = 1 if any(ch.isdigit() for ch in label) else 0
    weak = 1 if any(token in (label or "") for token in ("只谈", "本段", "以下", "本题")) else 0
    lead = 1 if label and label[0] in "谈看用把被从对将" else 0
    return (weak, lead, tail, digit, abs(len(label) - 4))




_OUTLINE_HEAD = re.compile(
    r"^(课标阐释|思维脉络|内容索引|探究[一二三123]|课前篇|课堂篇|"
    r"自主预习|探究学习|当堂检测|素养形成|方法点睛)"
)


def _is_chrome(text: str) -> bool:
    blob = _compact(text)
    if blob.startswith("高中同步") or blob.startswith("不可以在以下"):
        return True
    return "PPT模板" in (text or "") or "www." in (text or "").lower()








def _safe_chunks(kb: KnowledgeTool, collection: str = "default") -> list[dict[str, Any]]:
    try:
        return list(kb.list_chunks(collection=collection) or [])
    except Exception:
        return []


def ingest_library(kb: KnowledgeTool, paths: list[Path],
                   collection: str = "default") -> dict[str, Any]:
    before = _safe_chunks(kb, collection)
    old_texts = [str(item.get("text") or "") for item in before]
    files: list[dict[str, str]] = []
    for path in paths:
        stat = kb.add_file(str(path), collection=collection)
        files.append(
            {
                "name": path.name,
                "added": str(stat.get("added") or 0),
                "removed": str(stat.get("removed") or 0),
                "unchanged": str(stat.get("unchanged") or 0),
            }
        )
    incoming_names = {item["name"] for item in files}
    after = _safe_chunks(kb, collection)
    new_chunks = [
        item
        for item in after
        if str((item.get("metadata") or {}).get("source") or "") in incoming_names
    ]
    increment_items: list[dict[str, str]] = []
    by_file: dict[str, int] = {}
    seen_texts = list(old_texts)
    for chunk in new_chunks:
        meta = chunk.get("metadata") or {}
        source = str(meta.get("source") or "")
        for unit in _units(str(chunk.get("text") or "")):
            if _is_chrome(unit):
                continue
            if not _is_independent(unit, seen_texts):
                continue
            seen_texts.append(unit)
            by_file[source] = by_file.get(source, 0) + 1
            excerpt = " ".join(unit.split())
            if len(excerpt) > 80:
                excerpt = excerpt[:79] + "…"
            increment_items.append({"text": excerpt, "source": source})

    conflicts: list[dict[str, Any]] = []
    return {
        "message": "",
        "increment": str(len(increment_items)),
        "files": files,
        "increment_by_file": [
            {"name": name, "count": str(count)} for name, count in by_file.items()
        ],
        "conflicts": conflicts,
        "items": increment_items[:24],
    }






def build_library_markdown(draft: dict[str, Any]) -> str:
    increment = int(str(draft.get("increment") or "0") or 0)
    files = [item for item in (draft.get("files") or []) if isinstance(item, dict)]
    by_file = [
        item for item in (draft.get("increment_by_file") or []) if isinstance(item, dict)
    ]
    items = [item for item in (draft.get("items") or []) if isinstance(item, dict)]
    names = "、".join(f"《{item.get('name')}》" for item in files if item.get("name"))
    lines = [
        "# 知识库变化",
        "",
        "这次不是把文件塞进去就结束。下面是这批资料对知识库的**实际改变**。",
        "",
        "## 知识增量",
        "",
        f"**本次新增独立知识点 {increment} 个。**",
        "",
    ]
    if names:
        lines.append(f"来自 {names}。")
        lines.append("")
    if by_file:
        for item in by_file:
            lines.append(f"- 《{item.get('name')}》+{item.get('count')}")
        lines.append("")
    note = str(draft.get("message") or "").strip()
    if note:
        lines.append(note)
        lines.append("")
    if increment == 0 and not note:
        lines.append("库里已经有这些说法，知识边界没有被推开。")
        lines.append("")
    elif items:
        for item in items[:8]:
            src = item.get("source") or ""
            tag = f"（{src}）" if src else ""
            lines.append(f"- {item.get('text') or ''}{tag}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_library_html(draft: dict[str, Any]) -> str:
    increment = int(str(draft.get("increment") or "0") or 0)
    files = [item for item in (draft.get("files") or []) if isinstance(item, dict)]
    items = [item for item in (draft.get("items") or []) if isinstance(item, dict)]
    rows = [
        '<div class="library-report memory-review">',
        '<div class="review-heading">知识库变化'
        '<div class="quiz-hint">看增量，不看进度条</div></div>',
        '<div class="library-hero">',
        '<p class="library-caption">本次新增独立知识点</p>',
        f"<p class=\"library-count\"><strong>{increment}</strong> 个</p>",
        "</div>",
    ]
    if files:
        rows.append('<div class="library-files"><ul>')
        for item in files:
            rows.append(
                "<li>"
                f"《{escape(str(item.get('name') or ''), quote=False)}》"
                f" · 新块 {escape(str(item.get('added') or '0'), quote=False)}"
                "</li>"
            )
        rows.append("</ul></div>")
    if increment and items:
        rows.append('<div class="library-items"><ul>')
        for item in items[:8]:
            src = escape(str(item.get("source") or ""), quote=False)
            text = escape(str(item.get("text") or ""), quote=False)
            tag = f"<span>{src}</span>" if src else ""
            rows.append(f"<li>{text}{tag}</li>")
        rows.append("</ul></div>")
    rows.append("</div>")
    return "\n".join(rows)


def attach_library_artifacts(state: dict[str, Any]) -> None:
    """对照页进 rendered；裁决按钮进 library_html。"""
    from tools.domain_engine import line

    sub = line(state, "library")
    draft = dict(sub.get("draft") or {})
    draft["library_html"] = build_library_html(draft)
    sub["rendered"] = build_library_markdown(draft)
    sub["draft"] = draft


def kb_from_env() -> KnowledgeTool:
    fake = os.getenv("KNOWLEDGE_FAKE", "").strip().lower() in {"1", "true", "yes"}
    persist = os.getenv("KNOWLEDGE_PERSIST_DIR") or None
    return KnowledgeTool(fake=fake, persist_dir=persist)
