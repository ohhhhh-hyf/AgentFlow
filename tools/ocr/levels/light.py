from __future__ import annotations

import os
import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from tools.memory.store import safe_id
from tools.ocr import server_ocr_image_recognize
from tools.ocr.reconstruct import reconstruct_markdown, review_markdown

OCR_PARALLEL = 4
LIGHT_OCR_BATCH = OCR_PARALLEL
OCR_ITEM_TIMEOUT = float(os.getenv("OCR_ITEM_TIMEOUT", "180"))

_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


@dataclass(frozen=True)
class LightOcrResult:
    """Light OCR result saved for later knowledge ingestion."""

    raw_text: str
    reviewed_markdown: str
    reviewed_path: Path | None = None
    lines: list | None = None

    @property
    def files(self) -> list[str]:
        return [str(self.reviewed_path)] if self.reviewed_path else []


def _safe_stem(image_path: Path | str) -> str:
    raw = image_path.stem if isinstance(image_path, Path) else Path(str(image_path)).stem
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw).strip(" .") or "image"
    if stem.upper() in _WINDOWS_RESERVED:
        stem = f"{stem}_"
    return stem


_VERSION_STEM_RE = re.compile(r"^v(\d+)$", re.I)


def next_batch_version_stem(
    user_id: str,
    subject: str,
    project_root: str | Path,
) -> str:
    """同一 user+subject 下，多图合并稿按 v1、v2… 递增。"""
    root = Path(project_root)
    uid = safe_id(user_id)
    subj = safe_id(subject)
    folders = [
        root / "data" / uid / "ocr" / subj / "md",
        root / "data" / uid / "ocr" / subj / "txt",
        root / "data" / uid / "knowledge" / "catalogs",
    ]
    highest = 0
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file():
                continue
            stem = path.stem
            if stem.endswith("_meta"):
                stem = stem[: -len("_meta")]
            match = _VERSION_STEM_RE.match(stem)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"v{highest + 1}"


_PAGE_COMMENT_RE = re.compile(r"^<!--\s*第\s*\d+\s*页[:：].*?-->\s*", re.M)


def _strip_page_comments(text: str) -> str:
    return _PAGE_COMMENT_RE.sub("", text or "").strip()


def combine_ocr_pages(pages: list[dict[str, str]], *, key: str) -> str:
    blocks: list[str] = []
    for page in pages:
        body = _strip_page_comments(str(page.get(key) or ""))
        if body:
            blocks.append(body)
    return "\n\n".join(blocks)


def save_combined_ocr_outputs(
    pages: list[dict[str, str]],
    *,
    user_id: str,
    subject: str,
    project_root: str | Path,
    output_stem: str | None = None,
) -> LightOcrResult:
    """把并行识别的多页按上传顺序拼成一份 md，便于一次入库。"""
    stem = output_stem or next_batch_version_stem(user_id, subject, project_root)
    return save_light_ocr_outputs(
        Path(stem),
        raw_text=combine_ocr_pages(pages, key="raw_text"),
        reviewed_markdown=combine_ocr_pages(pages, key="reviewed_markdown"),
        user_id=user_id,
        subject=subject,
        project_root=project_root,
    )


def run_light_ocr(
    image_path: str | Path,
    *,
    user_id: str,
    subject: str,
    project_root: str | Path,
    output_stem: str | None = None,
    persist: bool = True,
    review: bool = True,
) -> LightOcrResult:
    """Run the current Light pipeline: OCR -> LLM 整理；默认再审校。"""
    path = Path(image_path)
    if not path.is_file():
        raise ValueError(f"图片不存在：{path}")

    payload = server_ocr_image_recognize(str(path), review=review)
    raw_txt, _no_llm_md, _llm_md, reviewed_md, _review_notes = payload[:5]
    lines = list(payload[5]) if len(payload) > 5 else []
    if not persist:
        return LightOcrResult(
            raw_text=raw_txt,
            reviewed_markdown=reviewed_md,
            lines=lines,
        )
    saved = save_light_ocr_outputs(
        Path(output_stem) if output_stem else path,
        raw_text=raw_txt,
        reviewed_markdown=reviewed_md,
        user_id=user_id,
        subject=subject,
        project_root=project_root,
    )
    return LightOcrResult(
        raw_text=saved.raw_text,
        reviewed_markdown=saved.reviewed_markdown,
        reviewed_path=saved.reviewed_path,
        lines=lines,
    )


def save_light_ocr_outputs(
    image_path: str | Path,
    *,
    raw_text: str,
    reviewed_markdown: str,
    user_id: str,
    subject: str,
    project_root: str | Path,
) -> LightOcrResult:
    """Save Light-compatible OCR outputs."""
    path = Path(image_path)

    base_dir = (
        Path(project_root)
        / "data"
        / safe_id(user_id)
        / "ocr"
        / safe_id(subject)
    )
    md_dir = base_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)

    from tools.ocr.mathmd import normalize_markdown_math

    stem = _safe_stem(path)
    reviewed_path = md_dir / f"{stem}.md"
    reviewed_markdown = normalize_markdown_math(reviewed_markdown)
    reviewed_path.write_text(reviewed_markdown, encoding="utf-8")

    return LightOcrResult(
        raw_text=raw_text,
        reviewed_markdown=reviewed_markdown,
        reviewed_path=reviewed_path,
    )


def ocr_image_to_lines(image_path: str | Path) -> tuple[str, list[dict]]:
    """只做 OCR，不调用整理/审校 LLM。"""
    from tools.ocr.adapter import raw_text_from_lines, recognize_image

    payload = recognize_image(str(image_path))
    lines = list(payload.get("lines") or [])
    raw_text = raw_text_from_lines(lines) or "（OCR 未识别到文字）"
    return raw_text, lines


def concat_page_lines(pages: list[dict]) -> list[dict]:
    """按上传顺序拼接各页 OCR 行，并把 y 错开，避免后页顶坐标看起来像页首。"""
    combined: list[dict] = []
    y_offset = 0.0
    for page in pages:
        page_bottom = y_offset
        for item in page.get("lines") or []:
            if not isinstance(item, dict):
                continue
            line = dict(item)
            bbox = line.get("bbox")
            if bbox:
                shifted = []
                for point in bbox:
                    x = float(point[0])
                    y = float(point[1]) + y_offset
                    shifted.append([x, y])
                    page_bottom = max(page_bottom, y)
                line["bbox"] = shifted
            layout = dict(line.get("layout") or {})
            if layout.get("top") is not None:
                try:
                    layout["top"] = float(layout["top"]) + y_offset
                    line["layout"] = layout
                except (TypeError, ValueError):
                    pass
            combined.append(line)
        y_offset = max(y_offset + 80.0, page_bottom + 80.0)
    return combined


def reconstruct_and_review_pages(pages: list[dict]) -> str:
    """一批（最多 4 页）OCR 行：一次整理 + 一次审校。"""
    lines = concat_page_lines(pages)
    if not lines:
        return "（OCR 未识别到文字）"
    draft = reconstruct_markdown(lines, max_tokens=12000)
    reviewed, _notes = review_markdown(draft, lines, max_tokens=2000)
    return reviewed or draft


def _fmt_ocr_exc(exc: BaseException) -> str:
    text = str(exc).strip() or repr(exc)
    return f"{type(exc).__name__}: {text}"


def _empty_ocr_page(name: str) -> dict:
    return {"name": name, "raw_text": "（OCR 未识别到文字）", "lines": []}


def _submit_ocr_chunk(pool: ThreadPoolExecutor, chunk: list[tuple], ocr_fn: Callable):
    return {
        pool.submit(ocr_fn, path): (idx, name)
        for idx, (path, name) in enumerate(chunk)
    }


def _drain_ocr_futures(
    futures: dict,
    *,
    lo: int,
    hi: int,
    total: int,
    item_timeout: float,
) -> Iterator[dict]:
    """收齐一批 OCR。单张失败/超时记空页并继续，不把整批打死。"""
    pages: list[dict | None] = [None] * len(futures)
    done = 0
    pending = set(futures)
    started = {future: time.monotonic() for future in futures}
    while pending:
        finished, pending = wait(pending, timeout=0.4, return_when=FIRST_COMPLETED)
        now = time.monotonic()
        for future in [item for item in pending if now - started[item] >= item_timeout]:
            pending.discard(future)
            idx, name = futures[future]
            pages[idx] = _empty_ocr_page(name)
            done += 1
            yield {
                "type": "ocr_fail",
                "lo": lo,
                "hi": hi,
                "done": done,
                "chunk": len(futures),
                "name": name,
                "total": total,
                "error": f"识别超时（{int(item_timeout)}秒）",
            }
        if not finished:
            yield {
                "type": "ocr_wait",
                "lo": lo,
                "hi": hi,
                "done": done,
                "chunk": len(futures),
                "total": total,
            }
            continue
        for future in finished:
            idx, name = futures[future]
            try:
                raw_text, lines = future.result()
            except Exception as exc:  # noqa: BLE001
                pages[idx] = _empty_ocr_page(name)
                done += 1
                yield {
                    "type": "ocr_fail",
                    "lo": lo,
                    "hi": hi,
                    "done": done,
                    "chunk": len(futures),
                    "name": name,
                    "total": total,
                    "error": _fmt_ocr_exc(exc),
                }
                continue
            pages[idx] = {
                "name": name,
                "raw_text": raw_text,
                "lines": lines,
            }
            done += 1
            yield {
                "type": "ocr_item",
                "lo": lo,
                "hi": hi,
                "done": done,
                "chunk": len(futures),
                "name": name,
                "total": total,
            }
    return [item for item in pages if item]


def iter_ocr_review_pipeline(
    image_entries: list[tuple],
    *,
    ocr_fn: Callable | None = None,
    review_fn: Callable | None = None,
    batch_size: int = LIGHT_OCR_BATCH,
    item_timeout: float | None = None,
) -> Iterator[dict]:
    """每批最多 4 路 OCR，整理审校完成后再处理下一批。"""
    if not image_entries:
        return
    ocr_fn = ocr_fn or ocr_image_to_lines
    review_fn = review_fn or reconstruct_and_review_pages
    timeout = float(OCR_ITEM_TIMEOUT if item_timeout is None else item_timeout)
    chunks: list[tuple[int, int, list]] = []
    for start in range(0, len(image_entries), batch_size):
        chunk = image_entries[start : start + batch_size]
        chunks.append((start + 1, start + len(chunk), chunk))
    total = len(image_entries)
    ocr_pool = ThreadPoolExecutor(max_workers=max(1, min(batch_size, total)))
    try:
        for lo, hi, chunk in chunks:
            yield {
                "type": "ocr_start",
                "lo": lo,
                "hi": hi,
                "workers": len(chunk),
                "total": total,
            }
            pages = yield from _drain_ocr_futures(
                _submit_ocr_chunk(ocr_pool, chunk, ocr_fn),
                lo=lo,
                hi=hi,
                total=total,
                item_timeout=timeout,
            )
            yield {
                "type": "review_start",
                "lo": lo,
                "hi": hi,
                "total": total,
            }
            reviewed = review_fn(pages)
            yield {
                "type": "batch_done",
                "lo": lo,
                "hi": hi,
                "reviewed": reviewed,
                "raw": combine_ocr_pages(pages, key="raw_text"),
            }
    finally:
        ocr_pool.shutdown(wait=False, cancel_futures=True)
