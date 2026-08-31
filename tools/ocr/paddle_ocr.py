"""PaddleOCR 3.x / PP-OCRv5：按 test_paddleOCR.py 的方式调用，并解析 res JSON。

与 serverocr / rapidocr 分开：本模块只处理 Paddle 的 ``predict()`` 结果
（``[{res: {...}}]`` 或带 ``.json`` 的结果对象）。
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

# 必须在 import paddle 之前限制 OpenMP，否则 4 路推理会互相抢满 CPU，看起来像串行。
_cpu_threads = os.getenv("PADDLE_OCR_CPU_THREADS", "1").strip() or "1"
for _key in (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "FLAGS_omp_num_threads",
):
    os.environ.setdefault(_key, _cpu_threads)

_CREATE_LOCK = threading.Lock()
_TLS = threading.local()
_CREATED = 0
_POOL: ThreadPoolExecutor | None = None


def _device() -> str:
    return os.getenv("PADDLE_OCR_DEVICE", "cpu").strip() or "cpu"


def paddle_concurrency() -> int:
    """PaddleOCR worker count. Each worker owns one thread-bound OCR instance."""
    device = _device().lower()
    raw = os.getenv("PADDLE_OCR_POOL_SIZE", "4").strip() or "4"
    cap = 4 if device.startswith(("gpu", "cuda")) else 8
    try:
        return max(1, min(cap, int(raw)))
    except ValueError:
        return 4

_HEADER_RE = re.compile(
    r"(UNIVERSITY|Wuhan|Hubei|HUAZHONG|SCIENCEAND|Tel[:：]|华中科技|中国·武汉)",
    re.I,
)
_FOOTER_RE = re.compile(r"(印刷厂|第\s*页|^页$|附属印刷)")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_MIN_CONF = 0.25
_HEADER_Y = 0.08
_FOOTER_Y = 0.92


def _to_list(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def _as_pages(raw: Any) -> list[dict]:
    if raw is None:
        return []
    if hasattr(raw, "json") and not isinstance(raw, dict):
        raw = raw.json
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    items = raw if isinstance(raw, list) else [raw]
    pages: list[dict] = []
    for item in items:
        if hasattr(item, "json") and not isinstance(item, dict):
            item = item.json
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except json.JSONDecodeError:
                continue
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("res"), dict):
            pages.append(item["res"])
        elif "rec_texts" in item or "dt_polys" in item:
            pages.append(item)
    return pages


def _poly_to_bbox(poly: Any) -> list[list[float]] | None:
    points = _to_list(poly)
    if not points:
        return None
    parsed: list[list[float]] = []
    if isinstance(points, (list, tuple)) and points and isinstance(points[0], (int, float)):
        if len(points) >= 4:
            left, top, right, bottom = [float(v) for v in points[:4]]
            return [
                [left, top],
                [right, top],
                [right, bottom],
                [left, bottom],
            ]
        return None
    for point in points:
        point = _to_list(point)
        if isinstance(point, dict):
            x, y = point.get("x"), point.get("y")
            if x is None or y is None:
                continue
            parsed.append([float(x), float(y)])
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            parsed.append([float(point[0]), float(point[1])])
    if len(parsed) < 4:
        return None
    return parsed[:4]


def _bbox_rect(bbox: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [float(point[0]) for point in bbox]
    ys = [float(point[1]) for point in bbox]
    return min(xs), min(ys), max(xs), max(ys)


def _map_point(
    x: float,
    y: float,
    angle: int,
    image_size: tuple[int, int],
) -> tuple[float, float]:
    width, height = image_size
    if angle == 90:
        return y, height - x
    if angle == 270:
        return width - y, x
    if angle == 180:
        return width - x, height - y
    return x, y


def _maybe_remap_bboxes(
    lines: list[dict],
    angle: int,
    image_size: tuple[int, int] | None,
) -> list[dict]:
    if not lines or not image_size or angle in (0, 360):
        return lines
    width, height = image_size
    max_x = 0.0
    max_y = 0.0
    for item in lines:
        bbox = item.get("bbox") or []
        for point in bbox:
            max_x = max(max_x, float(point[0]))
            max_y = max(max_y, float(point[1]))
    fits_original = max_x <= width + 80 and max_y <= height + 80
    if fits_original:
        return lines
    mapped: list[dict] = []
    for item in lines:
        bbox = item.get("bbox")
        if not bbox:
            mapped.append(item)
            continue
        new_bbox = [
            list(_map_point(float(point[0]), float(point[1]), angle, image_size))
            for point in bbox
        ]
        mapped.append({**item, "bbox": new_bbox})
    return mapped


def _latin_ratio(text: str) -> float:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return 0.0
    letters = sum(1 for char in compact if char.isalpha() and ord(char) < 128)
    return letters / len(compact)


def _is_paddle_chrome(
    text: str,
    bbox: list[list[float]] | None,
    image_size: tuple[int, int] | None,
) -> bool:
    if not bbox or not image_size:
        return False
    _left, top, _right, bottom = _bbox_rect(bbox)
    _width, height = image_size
    if height <= 1:
        return False
    compact = re.sub(r"\s+", "", text or "")
    y0, y1 = top / height, bottom / height
    if y0 <= _HEADER_Y and (
        _HEADER_RE.search(compact)
        or (_latin_ratio(compact) >= 0.7 and not _CJK_RE.search(compact))
    ):
        return True
    if y1 >= _FOOTER_Y and (
        _FOOTER_RE.search(compact) or re.fullmatch(r"\d{6,}", compact) is not None
    ):
        return True
    return False


def _join_row_texts(texts: list[str]) -> str:
    if not texts:
        return ""
    out = texts[0]
    for piece in texts[1:]:
        if _CJK_RE.search(out[-1:]) and _CJK_RE.search(piece[:1]):
            out += piece
        else:
            out += " " + piece
    return out.strip()


def _union_bbox(boxes: list[list[list[float]]]) -> list[list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for bbox in boxes:
        left, top, right, bottom = _bbox_rect(bbox)
        xs.extend([left, right])
        ys.extend([top, bottom])
    left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
    return [[left, top], [right, top], [right, bottom], [left, bottom]]


def _merge_same_row(lines: list[dict]) -> list[dict]:
    usable = [item for item in lines if item.get("bbox")]
    orphans = [item for item in lines if not item.get("bbox")]
    if len(usable) < 2:
        return lines
    heights = [_bbox_rect(item["bbox"])[3] - _bbox_rect(item["bbox"])[1] for item in usable]
    heights.sort()
    median = heights[len(heights) // 2] or 1.0
    ordered = sorted(
        usable,
        key=lambda item: (
            (_bbox_rect(item["bbox"])[1] + _bbox_rect(item["bbox"])[3]) / 2,
            _bbox_rect(item["bbox"])[0],
        ),
    )
    rows: list[list[dict]] = []
    for item in ordered:
        center = (_bbox_rect(item["bbox"])[1] + _bbox_rect(item["bbox"])[3]) / 2
        if rows:
            prev = rows[-1][-1]
            prev_center = (_bbox_rect(prev["bbox"])[1] + _bbox_rect(prev["bbox"])[3]) / 2
            if abs(center - prev_center) <= median * 0.55:
                rows[-1].append(item)
                continue
        rows.append([item])
    merged: list[dict] = []
    for row in rows:
        row.sort(key=lambda item: _bbox_rect(item["bbox"])[0])
        if len(row) == 1:
            merged.append(row[0])
            continue
        confs = [float(item["conf"]) for item in row if item.get("conf") is not None]
        item: dict[str, Any] = {
            "text": _join_row_texts([str(part["text"]) for part in row]),
            "bbox": _union_bbox([part["bbox"] for part in row]),
        }
        if confs:
            item["conf"] = round(sum(confs) / len(confs), 4)
        merged.append(item)
    return merged + orphans


def extract_paddle_lines(
    raw: Any,
    image_size: tuple[int, int] | None = None,
) -> list[dict]:
    """从 Paddle ``predict`` / 落盘 JSON 抽出 LLM 用的行：text + conf + bbox。"""
    lines: list[dict] = []
    for page in _as_pages(raw):
        texts = list(page.get("rec_texts") or [])
        scores = list(page.get("rec_scores") or [])
        polys = page.get("rec_polys")
        if polys is None or len(polys) == 0:
            polys = page.get("rec_boxes") or page.get("dt_polys") or []
        angles = list(page.get("textline_orientation_angles") or [])
        pre = page.get("doc_preprocessor_res") or {}
        try:
            page_angle = int(pre.get("angle") or 0) % 360
        except (TypeError, ValueError):
            page_angle = 0
        page_lines: list[dict] = []
        for idx, raw_text in enumerate(texts):
            text = str(raw_text or "").strip()
            if not text:
                continue
            conf = None
            if idx < len(scores):
                try:
                    conf = float(scores[idx])
                except (TypeError, ValueError):
                    conf = None
            if conf is not None and conf < _MIN_CONF:
                continue
            bbox = _poly_to_bbox(polys[idx]) if idx < len(polys) else None
            item: dict[str, Any] = {"text": text}
            if conf is not None:
                item["conf"] = conf
            if bbox:
                item["bbox"] = bbox
            if idx < len(angles):
                try:
                    item["line_angle"] = int(angles[idx])
                except (TypeError, ValueError):
                    pass
            page_lines.append(item)
        page_lines = _maybe_remap_bboxes(page_lines, page_angle, image_size)
        page_lines = _merge_same_row(page_lines)
        for item in page_lines:
            if _is_paddle_chrome(item.get("text") or "", item.get("bbox"), image_size):
                continue
            lines.append(
                {
                    "text": item["text"],
                    **({"conf": item["conf"]} if item.get("conf") is not None else {}),
                    **({"bbox": item["bbox"]} if item.get("bbox") else {}),
                }
            )
    return lines


def _build_engine():
    cuda = os.getenv("PADDLE_OCR_CUDA_VISIBLE_DEVICES", "").strip()
    if cuda:
        os.environ["CUDA_VISIBLE_DEVICES"] = cuda
    from paddleocr import PaddleOCR

    device = _device()
    det = os.getenv("PADDLE_OCR_DET_MODEL", "PP-OCRv5_server_det").strip()
    rec = os.getenv("PADDLE_OCR_REC_MODEL", "PP-OCRv5_server_rec").strip()
    use_doc = os.getenv("PADDLE_OCR_DOC_ORIENTATION", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    kwargs: dict[str, Any] = {
        "text_detection_model_name": det,
        "text_recognition_model_name": rec,
        "device": device,
    }
    try:
        return PaddleOCR(
            **kwargs,
            use_doc_orientation_classify=use_doc,
            use_textline_orientation=True,
        )
    except TypeError:
        logger.warning("当前 PaddleOCR 不支持 PP-OCRv5 参数，回退 lang=ch")
        return PaddleOCR(lang="ch")


def _worker_pool() -> ThreadPoolExecutor:
    """常驻线程池：引擎与线程绑定后跨请求复用，避免每批新建线程导致无法并行。"""
    global _POOL
    with _CREATE_LOCK:
        if _POOL is None:
            n = paddle_concurrency()
            _POOL = ThreadPoolExecutor(max_workers=n, thread_name_prefix="paddle-ocr")
        return _POOL


def _thread_engine():
    """引擎绑在当前线程：创建和 predict 必须同一线程，否则 Paddle 会串行/抢上下文。"""
    global _CREATED
    engine = getattr(_TLS, "engine", None)
    if engine is not None:
        return engine
    n = paddle_concurrency()
    with _CREATE_LOCK:
        engine = getattr(_TLS, "engine", None)
        if engine is not None:
            return engine
        if _CREATED >= n:
            raise RuntimeError(
                f"PaddleOCR 并发超过 {n} 路（device={_device()}）。"
                "请用 PADDLE_OCR_POOL_SIZE 调整实例数；显存紧张时降到 2 或 1。"
            )
        idx = _CREATED + 1
        logger.info("PaddleOCR 初始化引擎 %s/%s（device=%s，线程绑定）", idx, n, _device())
        engine = _build_engine()
        _CREATED += 1
        _TLS.engine = engine
        logger.info("PaddleOCR 引擎 %s/%s 就绪", idx, n)
        return engine


def _ocr_predict(path: str) -> dict:
    image_size = None
    try:
        from PIL import Image

        with Image.open(path) as img:
            image_size = img.size
    except Exception:  # noqa: BLE001
        image_size = None
    engine = _thread_engine()
    t0 = time.monotonic()
    result = engine.predict(path)
    logger.info("PaddleOCR 完成 %s（%.1fs）", os.path.basename(path), time.monotonic() - t0)
    return {"engine": "paddleocr", "lines": extract_paddle_lines(result, image_size=image_size)}


def _ocr_on_worker(path: str) -> dict:
    _TLS.worker = True
    return _ocr_predict(path)


def warmup_engines() -> None:
    """在常驻池里先把各路引擎建好，后面的批次才能真正并行。"""
    n = paddle_concurrency()

    def _bind(_: int) -> None:
        _TLS.worker = True
        _thread_engine()

    list(_worker_pool().map(_bind, range(n)))


def ocr_image(path: str) -> dict:
    """对齐 samples/examples/test_paddleOCR.py：``predict`` 后解析 ``res.json``。

    无论从哪条线程调用，都丢进 Paddle 常驻池，保证 4 路引擎各自只在自己的线程里 predict。
    """
    if getattr(_TLS, "worker", False):
        return _ocr_predict(path)
    return _worker_pool().submit(_ocr_on_worker, path).result()


__all__ = ["extract_paddle_lines", "ocr_image", "paddle_concurrency", "warmup_engines"]
