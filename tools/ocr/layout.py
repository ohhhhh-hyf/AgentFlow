"""版面识别：子进程 OCR 文字行 → 结构化行列表；公式候选行走 LaTeX-OCR。

行结构：``{"text": str, "formula": str|None, "bbox": [...], "conf": float, ...}``
- 普通文字行：text 为 OCR 文本
- 公式候选行：对裁剪块跑 LaTeX-OCR（子进程）→ formula（``$$...$$``）
- 标题候选行：结合 bbox、留白、编号/关键词，给出 role_hint / heading_score / heading_level_hint
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# 数学符号启发式：密集出现 → 视为公式候选行
_MATH_RE = re.compile(
    r"[=＋×÷−√∫∑∏≥≤≠≈∞πθαβγλΔΣφΦ]"
    r"|(?<![A-Za-z])[A-Za-z]\s*\^"
    r"|[\^_]\s*\{?"
    r"|\\frac|\\sum|\\int|\\lim|\\sqrt"
)

_HEADING_PATTERN_RE = re.compile(
    r"^("
    r"第[一二三四五六七八九十\d]+[章节篇单元课讲]"
    r"|[一二三四五六七八九十]+[、.．]"
    r"|[(（]?[一二三四五六七八九十\d]+[)）]"
    r"|\d+(\.\d+){0,2}[、.．\s]"
    r"|#{1,6}\s+"
    r")"
)
_HEADING_KEYWORDS = (
    "定义",
    "定理",
    "性质",
    "规则",
    "方法",
    "步骤",
    "例题",
    "小结",
    "总结",
    "重点",
    "难点",
    "考点",
    "知识点",
    "基础",
    "概念",
)


def _looks_like_formula(text: str) -> bool:
    return bool(_MATH_RE.search(text or ""))


def _bbox_rect(bbox) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        xs = [float(pt[0]) for pt in bbox]
        ys = [float(pt[1]) for pt in bbox]
        return min(xs), min(ys), max(xs), max(ys)
    except Exception:  # noqa: BLE001
        return None


def _median(values: list[float], default: float = 1.0) -> float:
    values = sorted(v for v in values if v > 0)
    if not values:
        return default
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def _short_text_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _infer_layout_hints(lines: list[dict], image_size: tuple[int, int] | None) -> list[dict]:
    """给 OCR 行补充版面特征和标题候选提示。"""
    if not lines:
        return lines
    img_w, img_h = image_size or (1, 1)
    rows: list[dict] = []
    for line in lines:
        rect = _bbox_rect(line.get("bbox"))
        if rect is None:
            rows.append({**line, "_rect": (0.0, 0.0, 0.0, 0.0)})
            continue
        left, top, right, bottom = rect
        width = max(1.0, right - left)
        height = max(1.0, bottom - top)
        rows.append(
            {
                **line,
                "_rect": rect,
                "layout": {
                    "left": round(left, 2),
                    "top": round(top, 2),
                    "width": round(width, 2),
                    "height": round(height, 2),
                    "center_x": round((left + right) / 2, 2),
                },
            }
        )
    rows.sort(key=lambda item: (item["_rect"][1], item["_rect"][0]))
    heights = [item["_rect"][3] - item["_rect"][1] for item in rows]
    median_height = max(1.0, _median(heights))

    for idx, item in enumerate(rows):
        text = str(item.get("text") or "").strip()
        left, top, right, bottom = item["_rect"]
        height = max(1.0, bottom - top)
        width = max(1.0, right - left)
        prev_bottom = rows[idx - 1]["_rect"][3] if idx > 0 else 0.0
        next_top = rows[idx + 1]["_rect"][1] if idx + 1 < len(rows) else float(img_h)
        gap_before = max(0.0, top - prev_bottom)
        gap_after = max(0.0, next_top - bottom)
        length = _short_text_len(text)
        height_ratio = height / median_height
        width_ratio = width / max(1, img_w)
        centered = (
            abs(((left + right) / 2) - (img_w / 2)) <= img_w * 0.18
            and width_ratio <= 0.5
        )
        near_left = left <= img_w * 0.18
        page_top = top <= img_h * 0.22
        short_line = 2 <= length <= 24
        very_long_line = length > 38
        score = 0.0

        if height_ratio >= 1.28:
            score += 0.28
        elif height_ratio >= 1.12:
            score += 0.16
        if gap_before >= median_height * 0.85:
            score += 0.18
        if idx + 1 < len(rows) and gap_after >= median_height * 0.55:
            score += 0.12
        if centered:
            score += 0.16
        elif near_left:
            score += 0.07
        if page_top:
            score += 0.12
        if short_line:
            score += 0.14
        if _HEADING_PATTERN_RE.search(text):
            score += 0.22
        if any(keyword in text for keyword in _HEADING_KEYWORDS) and short_line:
            score += 0.10
        if text.endswith(("。", "，", "；", ";", ",")):
            score -= 0.14
        if width_ratio >= 0.58 and not _HEADING_PATTERN_RE.search(text):
            score -= 0.12
        if very_long_line:
            score -= 0.24
        if _looks_like_formula(text):
            score -= 0.10

        score = max(0.0, min(1.0, score))
        role_hint = "heading" if score >= 0.52 else "body"
        if item.get("formula"):
            role_hint = "formula"
        level = None
        if role_hint == "heading":
            if centered and (page_top or height_ratio >= 1.28):
                level = 1
            elif _HEADING_PATTERN_RE.search(text) or height_ratio >= 1.12:
                level = 2
            else:
                level = 3
        layout = item.setdefault("layout", {})
        layout.update(
            {
                "height_ratio": round(height_ratio, 3),
                "gap_before": round(gap_before, 2),
                "gap_after": round(gap_after, 2),
                "centered": centered,
                "near_left": near_left,
            }
        )
        item["role_hint"] = role_hint
        item["heading_score"] = round(score, 3)
        if role_hint == "formula":
            item["title_decision"] = "locked_body"
        elif role_hint == "heading" and score >= 0.75:
            item["title_decision"] = "locked_heading"
        elif (
            role_hint == "body"
            and score <= 0.25
            and not _HEADING_PATTERN_RE.search(text)
            and not (short_line and any(keyword in text for keyword in _HEADING_KEYWORDS))
        ):
            item["title_decision"] = "locked_body"
        else:
            item["title_decision"] = "ambiguous"
        if level is not None:
            item["heading_level_hint"] = level
    for item in rows:
        item.pop("_rect", None)
    return rows


def _save_crop(img, bbox, pad: int = 6) -> str | None:
    """按 bbox 裁剪一行并存临时文件，返回路径（供公式子进程读取）。"""
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
        crop = img.crop((left, top, right, bottom))
        fd = tempfile.NamedTemporaryFile(
            suffix=".png", delete=False, dir=Path(tempfile.gettempdir())
        )
        fd.close()
        path = Path(fd.name)
        crop.save(path)
        return str(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("裁剪公式行失败：%s", exc)
        return None


def ocr_image_lines(image_path: str) -> list[dict]:
    """整图识别（子进程）→ 行列表；公式候选行附加 ``formula``。

    OCR 环境不可用/失败时返回空列表（不阻塞主流程）。
    """
    from .engines import run_ocr_subprocess

    try:
        payload = run_ocr_subprocess(image_path, formula=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR 识别失败：%s", exc)
        return []
    lines: list[dict] = []
    for item in payload.get("lines") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        lines.append(
            {
                "text": text,
                "bbox": item.get("bbox"),
                "conf": float(item.get("conf") or 0.0),
            }
        )
    try:
        from PIL import Image

        img = Image.open(image_path)
        image_size = img.size
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取图片尺寸失败：%s", exc)
        img = None
        image_size = None
    if not lines:
        return []

    # 公式候选：裁剪行 → LaTeX-OCR 子进程。
    # 该步骤会为每个候选行额外启动公式模型，手写笔记场景默认关闭，避免本地 RapidOCR 流程被拖慢。
    formula_enabled = os.getenv("OCR_ENABLE_FORMULA", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    formula_rows = [ln for ln in lines if _looks_like_formula(ln.get("text") or "")]
    if formula_enabled and img is not None and formula_rows:
        try:
            for item in formula_rows:
                crop_path = _save_crop(img, item.get("bbox"))
                if crop_path is None:
                    continue
                try:
                    payload = run_ocr_subprocess(crop_path, formula=True, timeout=120)
                    latex = str(payload.get("formula") or "").strip()
                    if latex:
                        item["formula"] = f"$${latex}$$"
                except Exception as exc:  # noqa: BLE001
                    logger.warning("公式识别失败：%s", exc)
                finally:
                    try:
                        Path(crop_path).unlink(missing_ok=True)
                    except Exception:  # noqa: BLE001
                        pass
        except Exception as exc:  # noqa: BLE001
            logger.warning("公式行裁剪失败：%s", exc)
    lines = _infer_layout_hints(lines, image_size) if lines else []
    return lines


__all__ = ["ocr_image_lines"]
