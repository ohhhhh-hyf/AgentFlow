"""版面识别：引擎 OCR 文字行 → 结构化行列表。

行结构：``{"text": str, "formula": str|None, "bbox": [...], "conf": float, ...}``
- 普通文字行：text 为 OCR 文本
- 公式行：引擎（如 server OCR）直接返回的 formula 字段原样透传，标记 role_hint="formula"
- 标题候选行：结合 bbox、留白、编号/关键词，给出 role_hint / heading_score / heading_level_hint
"""
from __future__ import annotations

import logging
import os
import re

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

# 页眉页脚 / 机构信息模式（地址、电话、邮箱、网址、邮编、版权、P.R.China 等）
_BOILERPLATE_PATTERNS = (
    r"Tel[:：]?\s*[+\d(（]",
    r"电话[:：]",
    r"传真[:：]|Fax[:：]",
    r"[\w.+-]+@[\w-]+\.[\w.]+",
    r"https?://|www\.\w",
    r"P\.?\s?R\.?\s?China",
    r"©|版权所有|Copyright|All Rights Reserved",
    r"\b\d{6}\b",  # 邮编（6 位数字）
    r"(?:Hubei|Wuhan|湖北|武汉|Beijing|上海|北京|深圳|广州)\s*[,，]?\s*\d{3,}",
)


def _looks_like_boilerplate(text: str) -> bool:
    """页眉页脚/机构信息识别：命中强信号（电话/邮箱/网址/版权）即判；
    邮编/地址组合需 ≥2 个信号。

    例：「华中科技大学 Wuhan 430074, Hubei, P.R.China 中国·武汉 Tel:(027)...」
    命中 P.R.China / 邮编 / Tel 多个信号 → 判为噪音行。
    """
    t = (text or "").strip()
    if not t:
        return False
    strong = re.search(
        r"Tel[:：]?|电话[:：]|邮编[:：]|@[\w-]+\.|https?://|www\.|©|版权所有|Copyright",
        t,
    )
    if strong:
        return True
    hits = sum(1 for p in _BOILERPLATE_PATTERNS if re.search(p, t))
    return hits >= 2


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
        # 页眉页脚/机构信息：模式命中优先于标题/正文判定
        if _looks_like_boilerplate(text):
            role_hint = "boilerplate"
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


# ── 碎片行确定性合并（S3 预规整；OCR_MERGE_FRAGMENTS=1 启用，默认关）──
# 引擎（尤其 serverocr 类）常把同一逻辑行切成多条短碎片：碎片会无差别抬高
# 行数、ambiguous 统计与每页 prompt。合并只做**保守的视觉邻接判定**（同页、
# 垂直间隙小、水平投影重叠大、前行未以句读结束、后行不是编号开头），
# 零 token、不依赖引擎与语料；合并发生在版面推断之前，让下游对"逻辑行"
# 只做一次角色/标题判定。数值默认值属保守设定，非标定目标。
_MERGE_GAP_RATIO = 0.6    # 垂直间隙 ≤ 行高中位数 × 该比例才允许合并
_MERGE_OVERLAP_RATIO = 0.5  # 水平投影重叠 ≥ 较短行宽 × 该比例
_MERGE_STOP_CHARS = set("。！？；;?!")
_MERGE_NUMERIC_START_RE = re.compile(
    r"^(?:第[0-9一二三四五六七八九十百]+[章节篇讲课单元]"
    r"|[（(]?[0-9一二三四五六七八九十百]+[)）]"
    r"|[0-9一二三四五六七八九十百]+[、.．]|\d+(?:\.\d+){0,2}\s)"
)


def _fragment_merge_enabled() -> bool:
    return os.getenv("OCR_MERGE_FRAGMENTS", "0").strip().lower() in {"1", "true", "yes", "on"}


def _rect_bounds(bbox) -> tuple[float, float, float, float] | None:
    rect = _bbox_rect(bbox)
    return rect if rect else None


def _cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def _join_texts(left: str, right: str) -> str:
    a = (left or "").strip()
    b = (right or "").strip()
    if not a or not b:
        return (a + b).strip()
    if _cjk(a[-1]) and _cjk(b[0]):
        return a + b          # 中文相连不加空格
    if (not _cjk(a[-1])) and (not _cjk(b[0])):
        return a + b          # ASCII/数字相邻同样不加（引擎碎片通常在词内断开）
    return a + " " + b        # 中英交界保守加空格


def _merge_pair(left: dict, right: dict) -> dict:
    lr = _rect_bounds(left.get("bbox"))
    rr = _rect_bounds(right.get("bbox"))
    out: dict = {"text": _join_texts(str(left.get("text") or ""), str(right.get("text") or ""))}
    if lr and rr:
        x0 = min(lr[0], rr[0])
        y0 = min(lr[1], rr[1])
        x1 = max(lr[2], rr[2])
        y1 = max(lr[3], rr[3])
        out["bbox"] = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    confs = [
        float(item["conf"])
        for item in (left, right)
        if item.get("conf") is not None
    ]
    if confs:
        out["conf"] = min(confs)   # 保守：取碎片中最低置信
    return out


def _can_merge_fragments(left: dict, right: dict, median_height: float) -> bool:
    """保守邻接判定：只有全部条件满足才允许合并。"""
    if str(left.get("formula") or "").strip() or str(right.get("formula") or "").strip():
        return False
    lr = _rect_bounds(left.get("bbox"))
    rr = _rect_bounds(right.get("bbox"))
    if not lr or not rr:
        return False
    lx0, ly0, lx1, ly1 = lr
    rx0, ry0, rx1, ry1 = rr
    if ry0 < ly1:            # 纵向重叠（不同行）不合并
        return False
    gap = ry0 - ly1
    if gap < 0 or gap > median_height * _MERGE_GAP_RATIO:
        return False
    overlap = min(lx1, rx1) - max(lx0, rx0)
    if overlap <= 0:
        return False
    shorter = min(lx1 - lx0, rx1 - rx0)
    if shorter <= 0 or overlap / shorter < _MERGE_OVERLAP_RATIO:
        return False
    text_left = str(left.get("text") or "").strip()
    text_right = str(right.get("text") or "").strip()
    if not text_left or not text_right:
        return False
    if text_left[-1] in _MERGE_STOP_CHARS:      # 前行以句读结束 → 逻辑行已完
        return False
    if _MERGE_NUMERIC_START_RE.match(text_right):  # 后行是编号开头（新条目）
        return False
    return True


def merge_fragment_lines(lines: list[dict]) -> list[dict]:
    """把同页碎片行按保守邻接规则合并成逻辑行（零 LLM）。"""
    if not _fragment_merge_enabled() or not lines:
        return lines
    items = [dict(item) for item in lines if isinstance(item, dict)]
    heights = []
    for item in items:
        rect = _rect_bounds(item.get("bbox"))
        if rect:
            heights.append(rect[3] - rect[1])
    if not heights:
        return lines
    heights.sort()
    median_height = heights[len(heights) // 2] or 1.0
    merged: list[dict] = []
    idx = 0
    n = len(items)
    while idx < n:
        acc = items[idx]
        idx += 1
        while idx < n and _can_merge_fragments(acc, items[idx], median_height):
            acc = _merge_pair(acc, items[idx])
            idx += 1
        merged.append(acc)
    if len(merged) != len(items):
        logger.info("碎片行合并：%d → %d 行", len(items), len(merged))
    return merged


def ocr_image_lines(image_path: str) -> list[dict]:
    """整图识别 → 行列表；引擎返回的 ``formula`` 字段原样透传。

    serverocr / paddleocr / rapidocr 均主进程直调（后两者复用实例）。失败时返回空列表。
    """
    from .engines import run_ocr_subprocess

    try:
        payload = run_ocr_subprocess(image_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR 识别失败：%s", exc)
        return []
    lines: list[dict] = []
    for item in payload.get("lines") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        formula = str(item.get("formula") or "").strip()
        if not text and not formula:
            continue
        row: dict = {"text": text, "bbox": item.get("bbox")}
        if formula:
            row["formula"] = formula
        if item.get("conf") is not None:
            row["conf"] = float(item["conf"])
        lines.append(row)
    try:
        from PIL import Image

        image_size = Image.open(image_path).size
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取图片尺寸失败：%s", exc)
        image_size = None
    if not lines:
        return []

    if _fragment_merge_enabled():
        lines = merge_fragment_lines(lines)
    lines = _infer_layout_hints(lines, image_size) if lines else []
    return lines


__all__ = ["ocr_image_lines"]
