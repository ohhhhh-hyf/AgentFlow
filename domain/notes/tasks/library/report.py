"""资料入库：多文件写入指定知识库，并给出知识增量。"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path
from typing import Any

from tools.knowledge.document_processor import SUPPORTED_EXTS
from tools.knowledge.tool import KnowledgeTool

_FILE_MARK = "【入库文件】"
_UNIT_CAP = 12
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
_SENT_SPLIT = re.compile(r"(?<=[。！？；!\?\n])")
_ITEM_ONLY_TAGS = {"example", "mistake"}
_ITEM_ONLY_HEAD_RE = re.compile(r"(例题|易错|注意|步骤|题型|技巧|提醒|小结|总结)")
_CHROME_RE = re.compile(
    r"(https?://|www\.|\.com\b|模板网|ppt\s*模板|版权所有|请勿转载|内部资料)",
    re.I,
)
_CHROME_EXACT = {
    "谢谢",
    "谢谢观看",
    "本课结束",
    "下课",
    "提问",
    "思考",
    "目录",
    "contents",
}


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
    allowed = SUPPORTED_EXTS | IMAGE_EXTS
    for raw in raw_paths:
        path = Path(raw)
        if not path.exists():
            raise FileNotFoundError(f"入库路径不存在：{path}")
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in allowed:
                    files.append(child)
            continue
        if path.suffix.lower() not in allowed:
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


def _split_library_inputs(paths: list[Path]) -> tuple[list[Path], list[Path]]:
    docs: list[Path] = []
    images: list[Path] = []
    for path in paths:
        if path.suffix.lower() in IMAGE_EXTS:
            images.append(path)
        else:
            docs.append(path)
    return docs, images


def _ocr_images_to_library_markdown(
    images: list[Path],
    *,
    user_id: str,
    subject: str,
) -> Path | None:
    if not images:
        return None
    from tools.ocr.levels.light import (
        iter_ocr_review_pipeline,
        next_batch_version_stem,
        save_light_ocr_outputs,
    )

    project_root = Path(__file__).resolve().parents[4]
    entries = [(path, path.name) for path in images]
    reviewed_blocks: list[str] = []
    raw_blocks: list[str] = []
    total = len(entries)
    print(f"[资料入库] 图片 OCR 开始：共 {total} 张。", flush=True)
    for event in iter_ocr_review_pipeline(entries):
        kind = event.get("type")
        lo = event.get("lo")
        hi = event.get("hi")
        if kind == "ocr_start":
            print(
                f"[资料入库] 正在识别第 {lo}-{hi} 张（共 {total} 张）…",
                flush=True,
            )
        elif kind == "ocr_fail":
            print(
                f"[资料入库] {event.get('name')} 识别失败（{event.get('error')}），已跳过。",
                flush=True,
            )
        elif kind == "review_start":
            print(
                f"[资料入库] 正在审校整理第 {lo}-{hi} 张 Markdown…",
                flush=True,
            )
        elif kind == "batch_done":
            reviewed = str(event.get("reviewed") or "").strip()
            raw = str(event.get("raw") or "").strip()
            if reviewed:
                reviewed_blocks.append(reviewed)
            if raw:
                raw_blocks.append(raw)
            print(
                f"[资料入库] 第 {lo}-{hi} 张整理完成。",
                flush=True,
            )
    stem = next_batch_version_stem(user_id, subject, project_root)
    saved = save_light_ocr_outputs(
        Path(stem),
        raw_text="\n\n".join(raw_blocks),
        reviewed_markdown="\n\n".join(reviewed_blocks) or "（OCR 未识别到文字）",
        user_id=user_id,
        subject=subject,
        project_root=project_root,
    )
    print(f"[资料入库] 图片 OCR 处理完成，已合并为 Markdown：{saved.reviewed_path}", flush=True)
    return saved.reviewed_path


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lstrip("\ufeff"))


def _ngrams(text: str, size: int) -> set[str]:
    """按字取 n-gram（去空白后），用于相似度判断。"""
    blob = _compact(text)
    if not blob:
        return set()
    return {blob[i : i + size] for i in range(len(blob) - size + 1)}


_NUM_PREFIX_RE = re.compile(r"^\s*(?:第?[0-9一二三四五六七八九十百]+[节章部分讲课]?[.、．]\s*|\d+\s*[.、．]\s*)")


def _title_key(text: str) -> str:
    """标题归一化键：去空白/编号前缀/常见后缀，用于「同名标题不同内容 → 判更新」的匹配。"""
    blob = _compact(text)
    blob = _NUM_PREFIX_RE.sub("", blob)
    for suffix in ("的定义", "的概念", "的性质", "详解", "总结", "小结"):
        if blob.endswith(suffix) and len(blob) > len(suffix):
            blob = blob[: -len(suffix)]
    return blob


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


def _knowledge_units_from_chunk(chunk: dict[str, Any]) -> list[str]:
    """入库报告按知识块计数，不再按句子/换行膨胀计数。"""
    meta = chunk.get("metadata") or {}
    text = str(chunk.get("text") or "")
    heading = " ".join(str(meta.get("heading") or "").split()).strip()
    topic = " ".join(str(meta.get("topic") or "").split()).strip()
    chapter = " ".join(str(meta.get("chapter") or "").split()).strip()
    kind = str(meta.get("heading_kind") or "").strip()
    tags = {
        item.strip()
        for item in str(meta.get("content_tags") or "").split(",")
        if item.strip()
    }
    label = heading or topic or chapter
    if kind == "chapter":
        return []
    if kind == "evidence":
        return []
    if label and (_ITEM_ONLY_HEAD_RE.search(label) or tags & _ITEM_ONLY_TAGS):
        return []
    if kind in {"topic", "knowledge_point"} and label:
        return [label]
    if label and len(_compact(label)) >= 4:
        return [label]
    units = [
        unit
        for unit in _units(text)
        if not _is_chrome(unit) and len(_compact(unit)) >= 18
    ]
    if not units:
        return []
    return [" ".join("".join(units[:3]).split())[:120]]


def _is_independent(text: str, old_texts: list[str]) -> bool:
    blob = _compact(text)
    if len(blob) < 8:
        return False
    norm_key = _title_key(text)
    for old in old_texts:
        other = _compact(old)
        if not other:
            continue
        if blob in other or other in blob:
            return False
        # 双键：标题归一化键相同 → 判为同一知识点（不同措辞/编号也算重复）
        if norm_key and len(norm_key) >= 4 and norm_key == _title_key(old):
            return False
        grams = _ngrams(blob, 6)
        shared = grams & _ngrams(other, 6)
        if grams and len(shared) / len(grams) >= 0.55:
            return False
    return True


def _is_chrome(text: str) -> bool:
    """过滤页眉页脚、网址、模板水印，不按学科词表丢内容。"""
    raw = text or ""
    blob = _compact(raw)
    if len(blob) < 4:
        return True
    if blob.lower() in _CHROME_EXACT:
        return True
    return bool(_CHROME_RE.search(raw))






def _safe_chunks(
    kb: KnowledgeTool, user_id: str = "", subject: str = ""
) -> list[dict[str, Any]]:
    try:
        return list(kb.list_chunks(user_id=user_id, subject=subject) or [])
    except Exception:
        return []


def ingest_library(
    kb: KnowledgeTool,
    paths: list[Path],
    user_id: str = "",
    subject: str = "",
) -> dict[str, Any]:
    doc_paths, image_paths = _split_library_inputs(paths)
    before = _safe_chunks(kb, user_id, subject)
    old_texts = [str(item.get("text") or "") for item in before]
    files: list[dict[str, str]] = []

    def add_one(path: Path) -> None:
        print(f"[资料入库] 非图片/Markdown 入库：{path.name}", flush=True)
        stat = kb.add_file(str(path), user_id=user_id, subject=subject)
        files.append(
            {
                "name": path.name,
                "added": str(stat.get("added") or 0),
                "removed": str(stat.get("removed") or 0),
                "unchanged": str(stat.get("unchanged") or 0),
            }
        )

    ocr_path: Path | None = None
    ocr_error = ""
    with ThreadPoolExecutor(max_workers=1) as pool:
        if doc_paths and image_paths:
            print(
                f"[资料入库] 并行处理：{len(doc_paths)} 份非图片资料直接入库，"
                f"{len(image_paths)} 张图片先 OCR 成 Markdown 后入库。",
                flush=True,
            )
        ocr_future = (
            pool.submit(
                _ocr_images_to_library_markdown,
                image_paths,
                user_id=user_id,
                subject=subject,
            )
            if image_paths
            else None
        )
        for path in doc_paths:
            add_one(path)
        if ocr_future is not None:
            try:
                ocr_path = ocr_future.result()
            except Exception as exc:  # noqa: BLE001 - 图片失败不影响非图片入库
                ocr_error = str(exc).strip() or repr(exc)

    if ocr_path is not None:
        add_one(ocr_path)
    incoming_names = {item["name"] for item in files}
    after = _safe_chunks(kb, user_id, subject)
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
        for unit in _knowledge_units_from_chunk(chunk):
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
        "message": (
            f"图片 OCR 失败，非图片资料已继续入库：{ocr_error}"
            if ocr_error
            else (
                f"{len(image_paths)} 张图片已 OCR 合并为《{ocr_path.name}》后入库。"
                if image_paths and ocr_path is not None
                else ""
            )
        ),
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
        f"**本次新增可编目知识单元 {increment} 个。**",
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
        '<p class="library-caption">本次新增可编目知识单元</p>',
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
    """对照页进 rendered。"""
    from tools.domain_engine import line

    sub = line(state, "library")
    draft = dict(sub.get("draft") or {})
    sub["rendered"] = build_library_markdown(draft)
    sub["draft"] = draft


def kb_from_env(user_id: str = "") -> KnowledgeTool:
    fake = os.getenv("KNOWLEDGE_FAKE", "").strip().lower() in {"1", "true", "yes"}
    persist = os.getenv("KNOWLEDGE_PERSIST_DIR") or None
    return KnowledgeTool(fake=fake, persist_dir=persist, user_id=user_id)
