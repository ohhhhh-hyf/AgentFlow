"""预处理：打开图片（转 RGB、可选增强）、公式行裁剪。

- ``open_image``：路径 → PIL.Image（RGB）
- ``crop_line``：按 OCR bbox 裁剪一行 → 公式引擎用
"""
from __future__ import annotations

import logging
from typing import Any

from PIL import Image, ImageEnhance, ImageOps

logger = logging.getLogger(__name__)


def open_image(path: str, enhance: bool = True) -> Image.Image | None:
    """打开图片并统一为 RGB；可选灰度增强（提高 OCR 对比度）。"""
    try:
        img = Image.open(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("打开图片失败 %s：%s", path, exc)
        return None
    if img.mode != "RGB":
        img = img.convert("RGB")
    if enhance:
        img = ImageEnhance.Contrast(img).enhance(1.2)
    return img


def crop_line(img: Image.Image, bbox: Any, pad: int = 6) -> Image.Image | None:
    """按 OCR 的 4 点 bbox 裁剪一行（带少量 padding）。

    bbox 形如 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]（左上→右上→右下→左下）。
    公式引擎（pix2tex）输入一般是单行公式图。
    """
    if not bbox:
        return None
    try:
        xs = [int(pt[0]) for pt in bbox]
        ys = [int(pt[1]) for pt in bbox]
        left = max(0, min(xs) - pad)
        top = max(0, min(ys) - pad)
        right = min(img.width, max(xs) + pad)
        bottom = min(img.height, max(ys) + pad)
        if right <= left or bottom <= top:
            return None
        return img.crop((left, top, right, bottom))
    except Exception as exc:  # noqa: BLE001
        logger.warning("裁剪行失败：%s", exc)
        return None


__all__ = ["crop_line", "open_image"]
