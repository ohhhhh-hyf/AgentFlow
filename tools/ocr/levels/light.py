from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

from tools.memory.store import safe_id
from tools.ocr.reconstruct import (
    deterministic_reconstruct_markdown,
    reconstruct_markdown,
    review_markdown,
)

logger = logging.getLogger("agentflow")


def _ocr_parallel() -> int:
    from tools.ocr.engines import ocr_concurrency

    return ocr_concurrency()


OCR_PARALLEL = 4  # 默认值；实际路数以 ocr_concurrency() 为准
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


def _safe_stem(image_path: Path | str) -> str:
    raw = image_path.stem if isinstance(image_path, Path) else Path(str(image_path)).stem
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw).strip(" .") or "image"
    if stem.upper() in _WINDOWS_RESERVED:
        stem = f"{stem}_"
    return stem


def next_batch_version_stem(
    user_id: str,
    subject: str,
    project_root: str | Path,
) -> str:
    """同一 user+subject 下，多图合并稿按 ``ocr_datetime`` 命名。"""
    root = Path(project_root)
    uid = safe_id(user_id)
    subj = safe_id(subject)
    folder = root / "data" / uid / "ocr" / subj
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"ocr_{stamp}"
    if not (folder / f"{stem}.md").exists():
        return stem
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    stem = f"ocr_{stamp}"
    if not (folder / f"{stem}.md").exists():
        return stem
    index = 1
    while (folder / f"{stem}_{index}.md").exists():
        index += 1
    return f"{stem}_{index}"


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
    base_dir.mkdir(parents=True, exist_ok=True)

    from tools.ocr.mathmd import normalize_markdown_math

    stem = _safe_stem(path)
    reviewed_path = base_dir / f"{stem}.md"
    reviewed_markdown = normalize_markdown_math(reviewed_markdown)
    reviewed_path.write_text(reviewed_markdown, encoding="utf-8")

    return LightOcrResult(
        raw_text=raw_text,
        reviewed_markdown=reviewed_markdown,
        reviewed_path=reviewed_path,
    )


def ocr_log(msg: str) -> None:
    """OCR 进度：终端 + 调试台日志缓冲各写一份。"""
    print(msg, flush=True)
    logger.info("%s", msg)


def log_ocr_pipeline_event(event: dict, *, total: int, engine: str) -> None:
    """把流水线事件打成可读进度（含当前引擎名）。"""
    kind = event.get("type")
    lo = event.get("lo")
    hi = event.get("hi")
    done = event.get("done")
    name = event.get("name") or ""
    tag = f"[OCR/{engine}]"
    if kind == "ocr_start":
        workers = event.get("workers") or (int(hi or 0) - int(lo or 0) + 1)
        ocr_log(f"{tag} 开始第 {lo}-{hi} 张（{workers} 路）")
    elif kind == "ocr_item":
        done_abs = int(lo or 1) + int(done or 0) - 1
        ocr_log(f"{tag} {done_abs}/{total} 完成 {name}")
    elif kind == "ocr_fail":
        err = str(event.get("error") or "失败").split(":")[0]
        done_abs = int(lo or 1) + int(done or 0) - 1
        ocr_log(f"{tag} {done_abs}/{total} 失败 {name}（{err}）")
    elif kind == "review_start":
        ocr_log(f"{tag} 第 {lo}-{hi} 张整理中")
    elif kind == "batch_done":
        ocr_log(f"{tag} 第 {lo}-{hi} 张整理完成")


def iter_logged_ocr_pipeline(
    image_entries: list[tuple],
    **kwargs,
) -> Iterator[dict]:
    """iter_ocr_review_pipeline 的带进度日志包装。"""
    from tools.ocr.engines import ocr_engine_label

    total = len(image_entries)
    if not total:
        return
    engine = ocr_engine_label()
    workers = min(_ocr_parallel(), total)
    batch_size = int(kwargs.get("batch_size") or LIGHT_OCR_BATCH)
    batch_size = max(1, min(batch_size, total))
    ocr_log(
        f"[OCR] 使用引擎 {engine}，共 {total} 张，{workers} 路并行，"
        f"{batch_size} 张一组整理"
    )
    for event in iter_ocr_review_pipeline(image_entries, **kwargs):
        log_ocr_pipeline_event(event, total=total, engine=engine)
        yield event


def images_to_reviewed_markdown(
    images: list[Path | str],
    *,
    persist_dir: Path | str | None = None,
) -> str:
    """多张图片 → OCR → LLM 整理审校 → 合并 Markdown 文本（纯文本返回，不入库）。

    供 graph 等直接消费 md 的任务使用；与 library 的批处理同一条
    OCR + 整理 + 审校流水线（每批 4 路并行，批内一次整理 + 一次审校）。
    传 ``persist_dir`` 时额外把合并稿落盘留档（同 ocr 目录命名规则）。
    """
    entries = [(Path(p), Path(p).name) for p in images]
    reviewed_blocks: list[str] = []
    raw_blocks: list[str] = []
    for event in iter_logged_ocr_pipeline(entries):
        if event.get("type") == "batch_done":
            reviewed = str(event.get("reviewed") or "").strip()
            raw = str(event.get("raw") or "").strip()
            if reviewed:
                reviewed_blocks.append(reviewed)
            if raw:
                raw_blocks.append(raw)
    merged = "\n\n".join(reviewed_blocks)
    if persist_dir is not None and merged:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = Path(persist_dir)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"ocr_{stamp}.md").write_text(merged, encoding="utf-8")
    return merged or "（OCR 未识别到文字）"


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


def _line_quality_stats(lines: list[dict]) -> dict[str, int | float]:
    total = max(len(lines), 1)
    low_conf = 0
    very_low_conf = 0
    bad_conf = 0
    formula = 0
    ambiguous = 0
    for item in lines:
        conf = item.get("conf")
        if conf is not None:
            try:
                value = float(conf)
                if value < 0.8:
                    low_conf += 1
                if value < 0.65:
                    very_low_conf += 1
            except (TypeError, ValueError):
                bad_conf += 1
        if str(item.get("formula") or "").strip():
            formula += 1
        if str(item.get("role_hint") or "") == "formula":
            formula += 1
        if str(item.get("title_decision") or "ambiguous") == "ambiguous":
            ambiguous += 1
    return {
        "total": total,
        "low_conf": low_conf,
        "very_low_conf": very_low_conf,
        "bad_conf": bad_conf,
        "formula": formula,
        "ambiguous": ambiguous,
        "low_conf_ratio": low_conf / total,
        "ambiguous_ratio": ambiguous / total,
    }


def _needs_reconstruct_llm(lines: list[dict]) -> bool:
    """Only use LLM reconstruction when layout or OCR quality needs judgment."""
    stats = _line_quality_stats(lines)
    if int(stats["bad_conf"]) or int(stats["very_low_conf"]):
        return True
    if int(stats["formula"]):
        return True
    if int(stats["low_conf"]) >= 2 and float(stats["low_conf_ratio"]) >= 0.06:
        return True
    if int(stats["ambiguous"]) >= 3 and float(stats["ambiguous_ratio"]) >= 0.12:
        return True
    return False


def _needs_review(lines: list[dict]) -> bool:
    """Review only when errors are likely enough to justify a second LLM call."""
    stats = _line_quality_stats(lines)
    if int(stats["bad_conf"]) or int(stats["very_low_conf"]):
        return True
    if int(stats["formula"]) >= 2:
        return True
    if int(stats["low_conf"]) >= 3 and float(stats["low_conf_ratio"]) >= 0.08:
        return True
    return False


def _estimate_reconstruct_tokens(lines: list[dict]) -> int:
    """按本批 OCR 行内容量估算重构输出上限，避免 max_tokens 下调后长批被静默截断。

    估算：整理后输出字数约为输入的 40%（去噪音/去重），中文 1 token ≈ 1.2 字（保守取大）；
    短批落 5000，内容越多上限越高，最高 9000。
    """
    total = sum(
        len(str(item.get("text") or "")) + len(str(item.get("formula") or ""))
        for item in lines
    )
    needed = int(total * 0.4 / 1.2)
    return max(5000, min(9000, needed))


def reconstruct_and_review_pages(pages: list[dict]) -> str:
    """一批（最多 4 页）OCR 行：必要时 LLM 整理；高置信文本走程序重构。"""
    lines = concat_page_lines(pages)
    if not lines:
        return "（OCR 未识别到文字）"
    if _needs_reconstruct_llm(lines):
        draft = reconstruct_markdown(lines, max_tokens=_estimate_reconstruct_tokens(lines))
    else:
        ocr_log("[OCR] 高置信纯文本批次，跳过 LLM 整理")
        draft = deterministic_reconstruct_markdown(lines)
    if not _needs_review(lines):
        return draft
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
    """按 batch_size 分组整理；组内 OCR 并发数由引擎能力决定。"""
    if not image_entries:
        return
    ocr_fn = ocr_fn or ocr_image_to_lines
    review_fn = review_fn or reconstruct_and_review_pages
    timeout = float(OCR_ITEM_TIMEOUT if item_timeout is None else item_timeout)
    review_batch = max(1, min(int(batch_size), len(image_entries)))
    ocr_workers = max(1, min(_ocr_parallel(), review_batch, len(image_entries)))
    chunks: list[tuple[int, int, list]] = []
    for start in range(0, len(image_entries), review_batch):
        chunk = image_entries[start : start + review_batch]
        chunks.append((start + 1, start + len(chunk), chunk))
    total = len(image_entries)
    ocr_pool = ThreadPoolExecutor(max_workers=ocr_workers)
    try:
        from tools.ocr.engines import ocr_engine_label as _ocr_label

        if _ocr_label() == "paddleocr" and ocr_fn is ocr_image_to_lines:
            from tools.ocr.paddle_ocr import warmup_engines

            ocr_log(f"[OCR/paddleocr] 预热 {ocr_workers} 路引擎（线程绑定）")
            warmup_engines()
        for lo, hi, chunk in chunks:
            yield {
                "type": "ocr_start",
                "lo": lo,
                "hi": hi,
                "workers": ocr_workers,
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
