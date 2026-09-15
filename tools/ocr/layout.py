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
    r"(?:[A-Za-z]{2,12}|[一-鿿]{2,8})\s*[,，]?\s*\d{5,6}",  # 任意地名/机构词 + 邮编组合
)


def _looks_like_boilerplate(text: str) -> bool:
    """页眉页脚/机构信息识别：命中强信号（电话/邮箱/网址/版权）即判；
    邮编/地址组合需 ≥2 个信号。

    例：「某大学 Wuhan 430074, P.R.China Tel:(027)...」式署名行
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


# ── 页眉/页脚自适应判定（逐图独立标定，零 token）──
# 实测动机：印刷页眉页脚的字号/位置**每张照片都不一样**，任何固定阈值都会漏。
# 同一批笔记中实测：某图页眉行高 138px = 本图中位行高（67px）的 2.07 倍，
# 同图正文标题 1.17 倍、正文 1.00 倍；另一图页眉为本图中位行高的 2.26 倍。
# 故标尺改用**本图自身的中位行高**，逐图自适应，不依赖引擎与固定坐标。
# 判定只在"边缘区"内进行（y 落在本图检测行范围的上下 12%，或处于最上/最下 2 行），
# 从边缘向内**连续**丢弃，遇到第一个"明显正文行"即停；且要求该段内至少一行命中
# **强特征**（超大字号 / 机构联系类文本 / 纯大写拉丁短行 / 纯数字编号），
# 否则一行都不丢——宁漏不误杀。
_CHROME_ZONE_RATIO = 0.12       # 边缘区厚度（相对本图检测到的行范围）
_CHROME_ZONE_ROWS = 2           # 最上/最下 N 行无论位置都算在边缘区内
_CHROME_BIG_RATIO = 1.6         # 行高 ≥ 中位行高 × 此倍数 → 印刷大字（校名/logo）
_CHROME_BODY_MIN = 0.85         # 明显正文行的行高倍率下限
_CHROME_BODY_MAX = 1.45         # 明显正文行的行高倍率上限（更高者视为印刷大字）
_CHROME_MAX_DROP = 8            # 单侧丢弃行数硬上限
_CHROME_MAX_DROP_RATIO = 0.25   # 单侧丢弃行数 ≤ 本图行数 × 此比例（防整页被吃）
# 机构/联系类文本。分两档避免误杀：本身即机构词的可独立命中（大学/学院/科技/印刷厂…），
# 而「农业/交通/工业/师范」这类日常词必须与「大学/学院」组成校名才算命中
# （否则农学、经济类笔记的页首正文标题会被当成页眉）。覆盖实测残缺识别变体：科技大 / 華中。
_CHROME_KEYWORDS_RE = re.compile(
    r"UNIVERSITY|COLLEGE|INSTITUTE|ACADEMY|TECHNOLOGY"
    r"|Tel|电话|传真|Fax|邮编|邮箱|E-?mail|https?://|www\."
    r"|P\.?\s?R\.?\s?China|中国[·•・]"
    r"|印刷厂|印刷|出版社"
    r"|大学|大學|学院|學院|科技"
    r"|(?:师范|理工|医科|农业|财经|政法|工业|交通|邮电|医科|外国语|民族|海洋|航空|航天)(?:大学|大學|学院|學院)",
    re.IGNORECASE,
)
_CHROME_LATIN_RE = re.compile(r"^[A-Z0-9 .,&'’()\[\]·\-]+$")  # 纯大写拉丁（可含数字/标点）
_CHROME_DIGITS_RE = re.compile(r"^\d{3,}$")                   # 印刷编号 / 电话 / 邮编
_CHROME_PAGE_WORDS = {"第", "页", "共", "页次", "页码", "#"}


def _page_chrome_enabled() -> bool:
    """页眉页脚逐图剔除开关（默认开；``OCR_PAGE_CHROME=0`` 可整体回退）。"""
    return os.getenv("OCR_PAGE_CHROME", "1").strip().lower() in {"1", "true", "yes", "on"}


def _line_rect(line: dict) -> tuple[float, float, float, float] | None:
    """行框，优先用版面推断已算好的 ``layout``（避免重复解析 bbox）。"""
    rect = _bbox_rect(line.get("bbox"))
    if rect is not None:
        return rect
    layout = line.get("layout") or {}
    try:
        left = float(layout["left"])
        top = float(layout["top"])
        return left, top, left + float(layout["width"]), top + float(layout["height"])
    except Exception:  # noqa: BLE001
        return None


def _looks_like_chrome_strong(text: str, ratio: float) -> bool:
    """强特征：单凭此行即可断定是印刷页眉/页脚。"""
    length = _short_text_len(text)
    if not length:
        return False
    if ratio >= _CHROME_BIG_RATIO:  # 校名/logo 式大字
        return True
    if _looks_like_boilerplate(text) or _CHROME_KEYWORDS_RE.search(text):
        return True
    if text in _CHROME_PAGE_WORDS or _CHROME_DIGITS_RE.match(text):
        return True
    if length >= 4 and _CHROME_LATIN_RE.match(text) and not _looks_like_formula(text):
        return True
    return False


def _looks_like_chrome_body(text: str, ratio: float) -> bool:
    """明显正文行：正常字号 + 非机构文本 + 非纯拉丁/数字/单字页号 → 判定为正文起点。"""
    length = _short_text_len(text)
    if length < 2:
        return False
    if not (_CHROME_BODY_MIN <= ratio <= _CHROME_BODY_MAX):
        return False
    if _looks_like_boilerplate(text) or _CHROME_KEYWORDS_RE.search(text):
        return False
    if text in _CHROME_PAGE_WORDS or _CHROME_DIGITS_RE.match(text):
        return False
    if _CHROME_LATIN_RE.match(text) and not _looks_like_formula(text):
        return False
    return True


def _mark_page_chrome(lines: list[dict]) -> int:
    """逐图判定印刷页眉/页脚，命中行标 ``role_hint="boilerplate"``（下游自动跳过）。

    返回标记条数。入参须为已完成版面推断的行（含 ``layout.height_ratio``）。
    """
    rows: list[tuple[dict, tuple[float, float, float, float], float]] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        rect = _line_rect(line)
        if rect is None or rect[3] <= rect[1]:
            continue
        ratio = float((line.get("layout") or {}).get("height_ratio") or 0.0)
        rows.append((line, rect, ratio))
    if len(rows) < 4:  # 行太少无统计意义
        return 0
    rows.sort(key=lambda item: (item[1][1], item[1][0]))
    top = min(rect[1] for _l, rect, _r in rows)
    bottom = max(rect[3] for _l, rect, _r in rows)
    span = max(1.0, bottom - top)
    zone = span * _CHROME_ZONE_RATIO
    limit = min(_CHROME_MAX_DROP, max(1, int(len(rows) * _CHROME_MAX_DROP_RATIO)))
    marked = 0
    for reverse in (False, True):
        ordered = list(reversed(rows)) if reverse else rows
        cluster: list[dict] = []
        for idx, (line, rect, ratio) in enumerate(ordered):
            in_zone = idx < _CHROME_ZONE_ROWS or (
                rect[1] - top <= zone if not reverse else bottom - rect[3] <= zone
            )
            if not in_zone:
                break
            text = str(line.get("text") or "").strip()
            if _looks_like_chrome_body(text, ratio):
                break
            cluster.append(line)
            if len(cluster) >= limit:
                break
        # 至少一行命中强特征才允许整段丢弃（否则宁可保留）
        if cluster and any(
            _looks_like_chrome_strong(
                str(item.get("text") or "").strip(),
                float((item.get("layout") or {}).get("height_ratio") or 0.0),
            )
            for item in cluster
        ):
            for item in cluster:
                item["role_hint"] = "boilerplate"
                item["chrome_zone"] = "footer" if reverse else "header"
                marked += 1
    return marked


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
# 零 token、不依赖引擎与语料。
# 防结构吞并（实测缺陷：标题行被并进下一行正文）：合并必须在**版面推断之后**
# 执行，且只允许 role 相同的行合并（heading 碎片可并；heading 与 body 永不可并），
# 合并后对结果行重推一次版面推断。数值默认值属保守设定，非标定目标。
_MERGE_GAP_RATIO = 0.6    # 垂直间隙 ≤ 行高中位数 × 该比例才允许合并
_MERGE_OVERLAP_RATIO = 0.5  # 水平投影重叠 ≥ 较短行宽 × 该比例
_MERGE_STOP_CHARS = set("。！？；;?!")
_MERGE_NUMERIC_START_RE = re.compile(
    r"^(?:第[0-9一二三四五六七八九十百]+[章节篇讲课单元]"
    r"|[（(]?[0-9一二三四五六七八九十百]+[)）]"
    r"|[0-9一二三四五六七八九十百]+[、.．]|\d+(?:\.\d+){0,2}\s)"
)
_MERGE_ALLOWED_ROLES = {"body", "heading"}


def _fragment_merge_enabled() -> bool:
    return os.getenv("OCR_MERGE_FRAGMENTS", "0").strip().lower() in {"1", "true", "yes", "on"}


def _rect_bounds(bbox) -> tuple[float, float, float, float] | None:
    rect = _bbox_rect(bbox)
    return rect if rect else None


def _cjk(ch: str) -> bool:
    # 汉字 + CJK 标点（全角）都视为连续书写，不加空格
    return (
        "\u4e00" <= ch <= "\u9fff"
        or "\u3000" <= ch <= "\u303f"
        or "\uff00" <= ch <= "\uffef"
    )


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
    # 版面角色/标题元数据以左侧行为准（合并后调用方会重推版面推断）
    for key in ("role_hint", "title_decision", "heading_score", "heading_level_hint", "layout"):
        if key in left:
            out[key] = left[key]
    return out


def _can_merge_fragments(left: dict, right: dict, median_height: float) -> bool:
    """保守邻接判定：全部条件满足才允许合并（含同角色约束）。"""
    left_role = str(left.get("role_hint") or "")
    right_role = str(right.get("role_hint") or "")
    if left_role not in _MERGE_ALLOWED_ROLES or right_role != left_role:
        return False                      # 结构保护：heading 与 body 永不可并
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
    """把同页碎片行按保守邻接+同角色规则合并成逻辑行（零 LLM）。

    入参为已完成版面推断的行（带 role_hint）；返回合并后的行，
    调用方应再跑一次版面推断以获得一致的版面特征。
    """
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
        logger.info("merge fragments %d -> %d lines", len(items), len(merged))
    return merged


def ocr_image_lines(image_path: str) -> list[dict]:
    """整图识别 → 行列表；引擎返回的 ``formula`` 字段原样透传。

    serverocr / paddleocr / rapidocr 均主进程直调（后两者复用实例）。失败时返回空列表。
    """
    from .engines import run_ocr_subprocess

    try:
        payload = run_ocr_subprocess(image_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ocr failed: %s", exc)
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
        logger.warning("read image size failed: %s", exc)
        image_size = None
    if not lines:
        return []

    lines = _infer_layout_hints(lines, image_size) if lines else []
    if _fragment_merge_enabled():
        merged = merge_fragment_lines(lines)
        if merged is not lines and len(merged) != len(lines):
            # 合并后重推版面推断，保证每条"逻辑行"的角色/标题特征一致
            lines = _infer_layout_hints(merged, image_size)
    # 页眉页脚：按本图中位行高自适应判定，标 role_hint=boilerplate（下游跳过）
    dropped = _mark_page_chrome(lines) if _page_chrome_enabled() else 0
    if dropped:
        logger.info(
            "page chrome: %d/%d lines dropped as header/footer (%s)",
            dropped,
            len(lines),
            "; ".join(
                str(item.get("text") or "")[:24]
                for item in lines
                if item.get("role_hint") == "boilerplate" and item.get("chrome_zone")
            )[:160],
        )
    return lines


__all__ = ["ocr_image_lines"]
