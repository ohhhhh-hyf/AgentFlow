from __future__ import annotations

import logging
import os
import re
import tempfile
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

from tools.memory.store import safe_id
from tools.ocr.reconstruct import (
    deterministic_reconstruct_markdown,
    ensure_markdown_complete,
    reconstruct_markdown,
    review_markdown,
)

logger = logging.getLogger("agentflow")


def _ocr_parallel() -> int:
    from tools.ocr.engines import ocr_concurrency

    return ocr_concurrency()


OCR_PARALLEL = 4  # 默认值；实际 OCR 路数以 ocr_concurrency() 为准
LIGHT_OCR_BATCH = int(os.getenv("LIGHT_OCR_BATCH", "8") or "8")
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
        page = event.get("page")
        page_abs = int(page) if page else int(lo or 1) + int(done or 0) - 1
        chunk = event.get("chunk")
        batch_note = f"（本组 {done}/{chunk}）" if done and chunk else ""
        ocr_log(f"{tag} 第 {page_abs}/{total} 张完成 {name}{batch_note}")
    elif kind == "ocr_fail":
        err = str(event.get("error") or "失败").split(":")[0]
        page = event.get("page")
        page_abs = int(page) if page else int(lo or 1) + int(done or 0) - 1
        chunk = event.get("chunk")
        batch_note = f"（本组 {done}/{chunk}）" if done and chunk else ""
        ocr_log(f"{tag} 第 {page_abs}/{total} 张失败 {name}（{err}）{batch_note}")
    elif kind == "review_start":
        ocr_log(f"{tag} 第 {lo}-{hi} 张按原顺序整理中")
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
    """只做 OCR（含页内版面推断），不调用整理/审校 LLM。

    paddle 引擎可选的识别前放大预处理：OCR_UPSCALE=1 时把图片长边放大到
    OCR_UPSCALE_LONG（默认 2400px，上限 OCR_UPSCALE_MAX_PIXELS=8000）再送识别，
    用于小字/低分辨率拍摄内容；默认关闭，开关只对 paddleocr 生效。
    """
    from tools.ocr.adapter import raw_text_from_lines
    from tools.ocr.layout import ocr_image_lines

    src = Path(image_path)
    prepared, applied = _prepare_ocr_image(src)
    try:
        lines = ocr_image_lines(str(prepared))
    finally:
        if applied:
            try:
                prepared.unlink(missing_ok=True)
            except OSError:
                pass
    if applied:
        ocr_log(f"[OCR] 识别前放大预处理：{src.name}")
    raw_text = raw_text_from_lines(lines) or "（OCR 未识别到文字）"
    return raw_text, lines


def _prepare_ocr_image(path: Path) -> tuple[Path, bool]:
    """paddle 识别前放大（默认关）：OCR_UPSCALE=1 且引擎为 paddleocr 时生效。

    按长边等比放大到 OCR_UPSCALE_LONG（默认 2400），任一边不超过
    OCR_UPSCALE_MAX_PIXELS（默认 8000）；返回临时 PNG 路径供识别，
    由调用方负责清理。任何失败都回退原图（不阻断 OCR）。
    """
    upscale = os.getenv("OCR_UPSCALE", "0").strip().lower() in {"1", "true", "yes", "on"}
    if not upscale:
        return path, False
    try:
        from tools.ocr.engines import ocr_engine_label

        if ocr_engine_label() != "paddleocr":
            return path, False
        raw_target = os.getenv("OCR_UPSCALE_LONG", "2400").strip() or "2400"
        raw_cap = os.getenv("OCR_UPSCALE_MAX_PIXELS", "8000").strip() or "8000"
        target = max(1000, min(8000, int(float(raw_target))))
        cap = max(2000, min(12000, int(float(raw_cap))))
    except Exception:  # noqa: BLE001
        return path, False
    try:
        from PIL import Image

        with Image.open(path) as img:
            width, height = img.size
            long_edge = max(width, height)
            if long_edge >= target:
                return path, False
            scale = target / long_edge
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            if max(new_size) > cap:
                shrink = cap / max(new_size)
                new_size = (max(1, int(new_size[0] * shrink)), max(1, int(new_size[1] * shrink)))
            tmp = Path(tempfile.gettempdir()) / f"agentflow_ocrprep_{uuid.uuid4().hex}.png"
            img = img.convert("RGB")
            img = img.resize(new_size, Image.LANCZOS)
            img.save(tmp, format="PNG")
            return tmp, True
    except Exception:  # noqa: BLE001
        return path, False


def _mark_cross_page_boilerplate(lines: list[dict]) -> None:
    """跨页重复检测：同一短行文本出现在 ≥2 页 → 页眉页脚特征，标 boilerplate。

    页眉页脚/页码行在每页重复；正文内容很少整行逐字重复（引用除外，长度限制降低误伤）。
    """
    from collections import Counter

    page_of: dict[int, str] = {}
    texts: list[tuple[str, int]] = []
    for idx, item in enumerate(lines):
        text = str(item.get("text") or "").strip()
        if not text or len(text) > 60:
            continue
        page_of[idx] = str(item.get("_page") or "")
        texts.append((text, idx))
    counter = Counter(t for t, _ in texts)
    repeated_pages: dict[str, set] = {}
    for text, idx in texts:
        if counter[text] < 2:
            continue
        repeated_pages.setdefault(text, set()).add(page_of[idx])
    for text, pages in repeated_pages.items():
        if len(pages) >= 2 and str(item_role(lines, text)) != "formula":
            for idx in (i for t, i in texts if t == text):
                lines[idx]["role_hint"] = "boilerplate"


def item_role(lines: list[dict], text: str) -> str:
    for item in lines:
        if str(item.get("text") or "").strip() == text:
            return str(item.get("role_hint") or "")
    return ""


def concat_page_lines(pages: list[dict]) -> list[dict]:
    """按上传顺序拼接各页 OCR 行，并把 y 错开，避免后页顶坐标看起来像页首。"""
    combined: list[dict] = []
    y_offset = 0.0
    for page_index, page in enumerate(pages):
        page_bottom = y_offset
        for item in page.get("lines") or []:
            if not isinstance(item, dict):
                continue
            line = dict(item)
            line["_page"] = str(page_index)
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
    _mark_cross_page_boilerplate(combined)
    return combined


def _line_conf(item: dict) -> float | None:
    conf = item.get("conf")
    if conf is None:
        return None
    try:
        return float(conf)
    except (TypeError, ValueError):
        return None


def _line_text(item: dict) -> str:
    return str(item.get("formula") or item.get("text") or "").strip()


def _is_formula_line(item: dict) -> bool:
    return bool(str(item.get("formula") or "").strip()) or str(item.get("role_hint") or "") == "formula"


def _formula_needs_llm(item: dict) -> bool:
    """Simple formulas can be normalized locally; only broken/uncertain formulas need LLM."""
    text = _line_text(item)
    if not text:
        return False
    conf = _line_conf(item)
    if conf is not None and conf < 0.78:
        return True
    pairs = (("(", ")"), ("（", "）"), ("[", "]"), ("{", "}"))
    if any(text.count(left) != text.count(right) for left, right in pairs):
        return True
    if text.count("=") > 2 or re.search(r"[$]{3,}|[$].*[$][$]|[$][$].*[$](?![$])", text):
        return True
    return False


def _line_quality_stats(lines: list[dict]) -> dict[str, int | float | bool]:
    total = max(len(lines), 1)
    low_conf = 0
    very_low_conf = 0
    bad_conf = 0
    conf_count = 0
    conf_total = 0.0
    formula = 0
    formula_needs_llm = 0
    ambiguous = 0
    for item in lines:
        if item.get("conf") is not None:
            value = _line_conf(item)
            if value is None:
                bad_conf += 1
            else:
                conf_count += 1
                conf_total += value
                if value < 0.75:
                    low_conf += 1
                if value < 0.55:
                    very_low_conf += 1
        if _is_formula_line(item):
            formula += 1
            if _formula_needs_llm(item):
                formula_needs_llm += 1
        if str(item.get("title_decision") or "ambiguous") == "ambiguous":
            ambiguous += 1
    avg_conf = conf_total / conf_count if conf_count else 0.0
    return {
        "total": total,
        "low_conf": low_conf,
        "very_low_conf": very_low_conf,
        "bad_conf": bad_conf,
        "conf_count": conf_count,
        "has_conf": conf_count > 0,
        "avg_conf": avg_conf,
        "formula": formula,
        "formula_needs_llm": formula_needs_llm,
        "ambiguous": ambiguous,
        "low_conf_ratio": low_conf / total,
        "ambiguous_ratio": ambiguous / total,
    }


def _needs_reconstruct_llm(lines: list[dict]) -> bool:
    """Only use LLM reconstruction when layout or OCR quality needs judgment."""
    stats = _line_quality_stats(lines)
    if (
        bool(stats["has_conf"])
        and float(stats["avg_conf"]) >= 0.9
        and int(stats["very_low_conf"]) == 0
        and float(stats["low_conf_ratio"]) <= 0.05
        and int(stats["formula_needs_llm"]) == 0
        and float(stats["ambiguous_ratio"]) <= 0.18
    ):
        return False
    if int(stats["bad_conf"]) or int(stats["very_low_conf"]):
        return True
    if int(stats["formula_needs_llm"]):
        return True
    if int(stats["low_conf"]) >= 3 and float(stats["low_conf_ratio"]) >= 0.10:
        return True
    if int(stats["ambiguous"]) >= 5 and float(stats["ambiguous_ratio"]) >= 0.20:
        return True
    return False


def _needs_review(lines: list[dict]) -> bool:
    """Review only when local OCR evidence can justify a targeted patch call."""
    stats = _line_quality_stats(lines)
    if int(stats["bad_conf"]) or int(stats["very_low_conf"]):
        return True
    if int(stats["formula_needs_llm"]):
        return True
    if bool(stats["has_conf"]) and int(stats["low_conf"]):
        return True
    return False


def _estimate_reconstruct_tokens(lines: list[dict]) -> int:
    """按本批 OCR 行内容量估算重构输出上限，避免长批被静默截断。

    实测（2026-09 笔记语料基线）：整理稿 md 字符 ≈ 输入的 1.9~3.3 倍、
    约 2.0~2.4 字符/token。旧公式 输入/1.2 会把 5~8 页批的真实需求
    （6~8k token）低估到 5k 附近，导致多数批次输出顶满 max_tokens 被截断、
    每批末页尾部内容丢失。max_tokens 只是保护上限：调大不会让短输出变贵
    （模型自然 EOS 即停），所以按 输入×1.15 再留安全边际、下限提到 9000。
    """
    total = sum(
        len(str(item.get("text") or "")) + len(str(item.get("formula") or ""))
        for item in lines
    )
    needed = int(total * 1.15)
    return max(9000, min(50000, needed))


def _page_mode_enabled() -> bool:
    """页级整理开关（默认开；OCR_PAGE_RECONSTRUCT=0 回退整批一次重写，做 A/B）。"""
    return os.getenv("OCR_PAGE_RECONSTRUCT", "1").strip().lower() in {"1", "true", "yes", "on"}


def _page_workers() -> int:
    """页级整理并发路数（OCR_RECONSTRUCT_WORKERS，默认 4，上限 8）。"""
    raw = os.getenv("OCR_RECONSTRUCT_WORKERS", "4").strip() or "4"
    try:
        return max(1, min(8, int(raw)))
    except ValueError:
        return 4


def _page_heading_hint(lines: list[dict]) -> str:
    """本页最后一个标题候选（版面 locked/heading），作为下一页的跨页上下文。"""
    for item in reversed(lines or []):
        role = str(item.get("role_hint") or "")
        decision = str(item.get("title_decision") or "")
        text = str(item.get("text") or "").strip()
        if text and role != "formula" and (role == "heading" or decision == "locked_heading"):
            return text[:60]
    return ""


def _dedupe_page_boundary_blocks(drafts: list[str], min_chars: int = 20) -> tuple[list[str], int, int]:
    """页界整段重复的确定性去重（零 token）。

    页级整理时，下一页常把上一页结尾的段落/公式原样再输出一遍（断点续写的
    常见形态）。规则只作用于**相邻两页的交界处**：
    - 上一页稿的末尾块与下一页稿的首块，空白折叠后**整块相等**且长度 ≥ min_chars
      → 丢弃下一页的首块（保留上一页的尾块），可连续剥除多层重复；
    - 不触碰文档内部任何重复（同一段落在文中多处出现是合法内容，不在交界处
      不受影响）；短块（≤ min_chars）不去重，避免误伤"（续）"类微块。
    """
    def _norm(text: str) -> str:
        return "".join((text or "").split())

    if len(drafts) <= 1:
        return list(drafts), 0, 0
    blocks_per_page = [
        [b.strip() for b in re.split(r"\n[ \t]*\n", d or "") if b.strip()]
        for d in drafts
    ]
    removed_pages = 0
    removed_chars = 0
    for idx in range(len(blocks_per_page) - 1):
        prev_blocks = blocks_per_page[idx]
        next_blocks = blocks_per_page[idx + 1]
        while prev_blocks and next_blocks:
            tail = _norm(prev_blocks[-1])
            head = _norm(next_blocks[0])
            if len(tail) < min_chars or tail != head:
                break
            removed_chars += len(next_blocks[0])
            next_blocks.pop(0)
            removed_pages += 1
    cleaned = ["\n\n".join(blocks) for blocks in blocks_per_page]
    return cleaned, removed_pages, removed_chars


def _draft_pagewise(pages: list[dict], all_lines: list[dict]) -> str:
    """页级整理（Step 2）：每页独立门控，需要 LLM 的页并行短整理，
    高置信页走确定性重构（零 token）；跨页只传上一页末尾标题防层级漂移；
    合并前对页界整段重复做确定性去重。

    返回按页序合并的草稿；完整性闭环与审校仍按批次在合并稿上执行。
    """
    n = len(pages)
    if n <= 1:
        lines = all_lines
        if _needs_reconstruct_llm(lines):
            return reconstruct_markdown(lines, max_tokens=_estimate_reconstruct_tokens(lines))
        ocr_log("[OCR] 高置信纯文本页，跳过 LLM 整理")
        return deterministic_reconstruct_markdown(lines)

    by_page: dict[str, list[dict]] = {}
    for item in all_lines:
        by_page.setdefault(str(item.get("_page") or ""), []).append(item)

    hints: list[str] = []
    prev = ""
    for idx in range(n):
        hints.append(prev)
        plines = by_page.get(str(idx)) or []
        if plines:
            heading = _page_heading_hint(plines)
            if heading:
                prev = heading

    workers = min(_page_workers(), n)
    deterministic_pages = 0

    def _one(idx: int):
        plines = by_page.get(str(idx)) or []
        if not plines:
            return "", False
        if _needs_reconstruct_llm(plines):
            return (
                reconstruct_markdown(
                    plines,
                    max_tokens=_estimate_reconstruct_tokens(plines),
                    context=hints[idx],
                ),
                True,
            )
        return deterministic_reconstruct_markdown(plines), False

    drafts: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, idx) for idx in range(n)]
        for future in futures:
            md, used_llm = future.result()
            if not used_llm and md.strip():
                deterministic_pages += 1
            if md and md.strip():
                drafts.append(md)
    drafts, deduped_blocks, deduped_chars = _dedupe_page_boundary_blocks(drafts)
    note = f"，页界去重 {deduped_blocks} 段/{deduped_chars} 字符" if deduped_blocks else ""
    ocr_log(f"[OCR] 页级整理：{n} 页，并发 {workers}，确定性 {deterministic_pages} 页（零 LLM）{note}")
    return "\n\n".join(drafts)


_REVIEW_EVENTS: list[dict] = []


def take_review_events() -> list[dict]:
    """取走并清空审校留痕（与 review_fn/批次调用次序 1:1，供基线归并）。"""
    events = list(_REVIEW_EVENTS)
    _REVIEW_EVENTS.clear()
    return events


def _review_enabled() -> bool:
    """审校轮开关（默认开；OCR_REVIEW=0 关闭做 A/B，检查审校是否值回 token）。"""
    return os.getenv("OCR_REVIEW", "1").strip().lower() in {"1", "true", "yes", "on"}


def reconstruct_and_review_pages(pages: list[dict]) -> str:
    """一批 OCR 行：页级（默认）或整批 LLM 整理；高置信文本走程序重构。

    页级模式（OCR_PAGE_RECONSTRUCT=1，默认）：每页短整理并发执行，单页远离
    输出上限（截断不再发生），页级门控让干净页零 token；随后按批做完整性
    闭环与审校。OCR_PAGE_RECONSTRUCT=0 回退为整批一次长文重写（A/B 对照）；
    OCR_REVIEW=0 关闭审校轮（A/B：观察 kept80/公式 avg/入库增量是否受影响）。
    每次调用产出一条审校留痕（take_review_events），用于跨语料判定审校价值。
    """
    lines = concat_page_lines(pages)
    if not lines:
        _REVIEW_EVENTS.append({"ran": False, "reason": "no_lines"})
        return "（OCR 未识别到文字）"
    if _page_mode_enabled():
        draft = _draft_pagewise(pages, lines)
    else:
        if _needs_reconstruct_llm(lines):
            draft = reconstruct_markdown(lines, max_tokens=_estimate_reconstruct_tokens(lines))
        else:
            ocr_log("[OCR] 高置信纯文本批次，跳过 LLM 整理")
            draft = deterministic_reconstruct_markdown(lines)
    # 完整性闭环：零成本行级自检，检出截断/漏行时用一次小续写补回（review 补不了丢失行）。
    # 可用环境变量 OCR_COMPLETENESS_FIX=0 关闭做 A/B 对照。
    draft = ensure_markdown_complete(draft, lines)
    event: dict = {"review_enabled": _review_enabled(), "needs_review": bool(_needs_review(lines))}
    if not event["review_enabled"] or not event["needs_review"]:
        event.update({"ran": False, "draft_changed": False, "applied_patches": 0})
        _REVIEW_EVENTS.append(event)
        return draft
    t0 = time.monotonic()
    reviewed, notes = review_markdown(draft, lines)
    final = reviewed or draft
    event.update({
        "ran": True,
        "seconds": round(time.monotonic() - t0, 3),
        "draft_changed": final != draft,
        "applied_patches": (notes or "").count("已替换"),
    })
    _REVIEW_EVENTS.append(event)
    return final


def _fmt_ocr_exc(exc: BaseException) -> str:
    text = str(exc).strip() or repr(exc)
    return f"{type(exc).__name__}: {text}"


def _empty_ocr_page(name: str) -> dict:
    return {"name": name, "raw_text": "（OCR 未识别到文字）", "lines": []}


def _submit_ocr_chunk(
    pool: ThreadPoolExecutor,
    chunk: list[tuple],
    ocr_fn: Callable,
    *,
    first_page: int = 1,
):
    return {
        pool.submit(ocr_fn, path): (idx, first_page + idx, name)
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
            idx, page_no, name = futures[future]
            pages[idx] = _empty_ocr_page(name)
            done += 1
            yield {
                "type": "ocr_fail",
                "lo": lo,
                "hi": hi,
                "page": page_no,
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
            idx, page_no, name = futures[future]
            try:
                raw_text, lines = future.result()
            except Exception as exc:  # noqa: BLE001
                pages[idx] = _empty_ocr_page(name)
                done += 1
                yield {
                    "type": "ocr_fail",
                    "lo": lo,
                    "hi": hi,
                    "page": page_no,
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
                "page": page_no,
                "done": done,
                "chunk": len(futures),
                "name": name,
                "total": total,
            }
    # OCR futures can finish out of order; this list restores the original page order for review.
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
            chunk_workers = min(ocr_workers, len(chunk))
            yield {
                "type": "ocr_start",
                "lo": lo,
                "hi": hi,
                "workers": chunk_workers,
                "total": total,
            }
            pages = yield from _drain_ocr_futures(
                _submit_ocr_chunk(ocr_pool, chunk, ocr_fn, first_page=lo),
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
