from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .layout import ocr_image_lines


def _clean_ocr_text(value) -> str:
    if isinstance(value, bytes):
        for encoding in ("utf-8", "gb18030", "latin1"):
            try:
                return value.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        return value.decode("utf-8", errors="replace").strip()
    return str(value or "").strip()


@contextmanager
def temporary_ocr_engine(engine: str):
    old_engine = os.environ.get("OCR_ENGINE")
    os.environ["OCR_ENGINE"] = engine
    try:
        yield
    finally:
        if old_engine is None:
            os.environ.pop("OCR_ENGINE", None)
        else:
            os.environ["OCR_ENGINE"] = old_engine


def current_ocr_engine() -> str:
    return os.environ.get("OCR_ENGINE", "serverocr").strip().lower() or "serverocr"


def recognize_image(image_path: str | Path, *, engine: str | None = None) -> dict[str, Any]:
    """Recognize text through one OCR adapter controlled by OCR_ENGINE.

    serverocr: 主进程直调服务器 FOCUS OCR。
    paddleocr: 主进程单例 PP-OCRv5。
    rapidocr: 主进程单例 RapidOCR。
    各引擎失败重试三次后返回空行，互不兜底。
    """
    selected = (engine or current_ocr_engine()).strip().lower()
    with temporary_ocr_engine(selected):
        lines = ocr_image_lines(str(image_path))
    return {"engine": selected, "lines": lines}


def raw_text_from_lines(lines: list[dict]) -> str:
    raw_lines = [
        _clean_ocr_text(item.get("text") or item.get("formula"))
        for item in lines
        if isinstance(item, dict) and _clean_ocr_text(item.get("text") or item.get("formula"))
    ]
    return "\n".join(raw_lines).strip()


__all__ = ["current_ocr_engine", "raw_text_from_lines", "recognize_image", "temporary_ocr_engine"]
