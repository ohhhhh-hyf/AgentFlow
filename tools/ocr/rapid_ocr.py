"""RapidOCR：进程内最多 4 台实例，四路并行且互不抢同一引擎。"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any

logger = logging.getLogger(__name__)

RAPID_OCR_POOL_SIZE = 4

_CREATE_LOCK = threading.Lock()
_IDLE: queue.Queue = queue.Queue()
_CREATED = 0


def _to_list(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def _build_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _acquire_engine():
    global _CREATED
    try:
        return _IDLE.get_nowait()
    except queue.Empty:
        pass
    with _CREATE_LOCK:
        if _CREATED < RAPID_OCR_POOL_SIZE:
            engine = _build_engine()
            _CREATED += 1
            logger.debug("RapidOCR 引擎池 %s/%s", _CREATED, RAPID_OCR_POOL_SIZE)
            return engine
    return _IDLE.get()


def _release_engine(engine) -> None:
    _IDLE.put(engine)


def get_rapid_engine():
    """调试入口：取出池中一台引擎。长期占用会少一路并行。"""
    return _acquire_engine()


def ocr_image(path: str) -> dict:
    engine = _acquire_engine()
    try:
        result, _ = engine(path)
        items = list(result or [])
    finally:
        _release_engine(engine)
    lines: list[dict] = []
    for item in items:
        box, text, conf = item[0], item[1], item[2]
        lines.append(
            {
                "text": str(text),
                "conf": float(conf),
                "bbox": _to_list(box),
            }
        )
    return {"engine": "rapidocr", "lines": lines}


__all__ = ["get_rapid_engine", "ocr_image"]
