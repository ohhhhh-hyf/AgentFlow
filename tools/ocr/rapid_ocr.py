"""RapidOCR：进程内单例，避免每张图重新加载 ONNX。"""
from __future__ import annotations

import threading
from typing import Any

_ENGINE_LOCK = threading.Lock()
_ENGINE = None


def _to_list(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def get_rapid_engine():
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            from rapidocr_onnxruntime import RapidOCR

            _ENGINE = RapidOCR()
        return _ENGINE


def ocr_image(path: str) -> dict:
    result, _ = get_rapid_engine()(path)
    lines: list[dict] = []
    for item in result or []:
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
