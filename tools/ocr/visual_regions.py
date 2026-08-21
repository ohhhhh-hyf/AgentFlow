"""轻量图示区域检测：不理解图片内容，只记录非文字墨迹的位置与粗分类。"""
from __future__ import annotations

from typing import Any


def _bbox_rect(bbox: Any) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        xs = [float(pt[0]) for pt in bbox]
        ys = [float(pt[1]) for pt in bbox]
        return min(xs), min(ys), max(xs), max(ys)
    except Exception:
        return None


def _overlap_ratio(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0.0
    inter = (right - left) * (bottom - top)
    area = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    return inter / area


def _line_signal(mask, axis: int, threshold: float = 0.45) -> int:
    import numpy as np

    if mask.size == 0:
        return 0
    ratios = np.mean(mask > 0, axis=axis)
    return int(np.sum(ratios >= threshold))


def _classify_region(mask, w: int, h: int, image_w: int, image_h: int) -> str:
    try:
        import cv2
        import numpy as np
    except Exception:
        return "diagram"

    area_ratio = (w * h) / max(1, image_w * image_h)
    density = float(np.mean(mask > 0)) if mask.size else 0.0
    horizontal = _line_signal(mask, axis=1)
    vertical = _line_signal(mask, axis=0)
    long_h = horizontal >= max(1, int(h * 0.025))
    long_v = vertical >= max(1, int(w * 0.025))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rect_like = 0
    for contour in contours:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.04 * peri, True)
        x, y, cw, ch = cv2.boundingRect(contour)
        if len(approx) >= 4 and cw * ch >= max(80, w * h * 0.015):
            rect_like += 1

    if long_h and long_v and area_ratio >= 0.025:
        return "coordinate_plot"
    if rect_like >= 2 and (long_h or long_v):
        return "flowchart"
    if long_h and long_v:
        return "table_or_grid"
    if density < 0.035 and (w >= image_w * 0.25 or h >= image_h * 0.16):
        return "sketch"
    return "diagram"


def detect_visual_regions(image_path: str, text_lines: list[dict]) -> list[dict]:
    """检测被 OCR 文字框覆盖之外的手绘图/图表区域。

    返回的区域只表达“有图、在哪里、粗略像什么”，不做语义识别。
    """
    try:
        import cv2
        import numpy as np
    except Exception:
        return []

    img = cv2.imread(str(image_path))
    if img is None:
        return []
    image_h, image_w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)

    text_rects: list[tuple[int, int, int, int]] = []
    for line in text_lines:
        rect = _bbox_rect(line.get("bbox"))
        if rect is None:
            continue
        left, top, right, bottom = rect
        pad_x = max(3, int((right - left) * 0.18))
        pad_y = max(3, int((bottom - top) * 0.35))
        text_rect = (
            max(0, int(left) - pad_x),
            max(0, int(top) - pad_y),
            min(image_w, int(right) + pad_x),
            min(image_h, int(bottom) + pad_y),
        )
        text_rects.append(text_rect)
        cv2.rectangle(ink, text_rect[:2], text_rect[2:], 0, thickness=-1)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 9))
    merged = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions: list[dict] = []
    min_bbox_area = max(900, int(image_w * image_h * 0.008))
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h < min_bbox_area or w < 35 or h < 25:
            continue
        if w > image_w * 0.96 and h > image_h * 0.96:
            continue
        rect = (x, y, x + w, y + h)
        if any(_overlap_ratio(rect, text_rect) > 0.72 for text_rect in text_rects):
            continue
        region_mask = ink[y : y + h, x : x + w]
        ink_density = float(np.mean(region_mask > 0)) if region_mask.size else 0.0
        if ink_density < 0.003 or ink_density > 0.55:
            continue
        kind = _classify_region(region_mask, w, h, image_w, image_h)
        regions.append(
            {
                "type": kind,
                "bbox": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
                "layout": {
                    "left": round(x, 2),
                    "top": round(y, 2),
                    "width": round(w, 2),
                    "height": round(h, 2),
                    "center_x": round(x + w / 2, 2),
                    "width_ratio": round(w / max(1, image_w), 3),
                    "height_ratio": round(h / max(1, image_h), 3),
                    "centered": abs((x + w / 2) - image_w / 2) <= image_w * 0.2,
                },
                "ink_density": round(ink_density, 4),
            }
        )

    regions.sort(key=lambda item: (item["layout"]["top"], item["layout"]["left"]))
    for idx, region in enumerate(regions, start=1):
        region["id"] = f"visual_{idx}"
    return regions


__all__ = ["detect_visual_regions"]
