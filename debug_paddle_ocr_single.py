# -*- coding: utf-8 -*-
"""debug_paddle_ocr_single.py -- 单图 PaddleOCR 识别与排查提取脚本

用于独立复现和查看 PaddleOCR 对单张议程图片的完整识别流程与返回内容。
包含：
1. PaddleOCR 引擎原生识别（raw_texts / raw_polys）
2. 行提取与同水平行合并（_merge_same_row）
3. 边缘去噪与页眉页脚过滤（_is_paddle_chrome）
4. 版面与碎片合并后保留的有效文本行（retained lines）
5. 组装输入给 LLM 结构化提取器（ocr_reconstruct）的最终 Prompt 文本
6. 底部议题（如 SpeechASR 等）坐标、置信度与留存状态专项目检
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# 设置基础日志格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("debug_paddleocr")

# 项目根目录
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# 默认测试图片路径
DEFAULT_IMAGE = ROOT / "data" / "1" / "agenda" / "test1" / "商评1.png"


# =========================================================================
# 1. 精确复刻/复用 tools/ocr/paddle_ocr.py 核心参数与清洗规则
# =========================================================================
_HEADER_RE = re.compile(
    r"(UNIVERSITY|COLLEGE|INSTITUTE"
    r"|Tel[:：.]|电话|传真"
    r"| \d{5,6} "
    r"|P\.?\s?R\.?\s?China|中国·"
    r"|[一-鿿]{2,10}(?:大学|学院))",
    re.I,
)
_FOOTER_RE = re.compile(r"(印刷|第\s*页|^页$)")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_MIN_CONF = 0.25
_HEADER_Y = 0.08
_FOOTER_Y = 0.92


def _bbox_rect(bbox: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in bbox]
    ys = [float(p[1]) for p in bbox]
    return min(xs), min(ys), max(xs), max(ys)


def _latin_ratio(text: str) -> float:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return 0.0
    letters = sum(1 for c in compact if c.isalpha() and ord(c) < 128)
    return letters / len(compact)


def _is_paddle_chrome(
    text: str,
    bbox: list[list[float]] | None,
    image_size: tuple[int, int] | None,
) -> tuple[bool, str]:
    """判断是否被视为页面页眉/页脚噪点，并返回具体过滤理由。"""
    if not bbox or not image_size:
        return False, "无 bbox 或无图尺寸"
    _left, top, _right, bottom = _bbox_rect(bbox)
    _width, height = image_size
    if height <= 1:
        return False, "高度异常"
    compact = re.sub(r"\s+", "", text or "")
    y0, y1 = top / height, bottom / height
    if y0 <= _HEADER_Y and (
        _HEADER_RE.search(compact)
        or (_latin_ratio(compact) >= 0.7 and not _CJK_RE.search(compact))
    ):
        return True, f"命中顶端页眉区(y0={y0:.3f}<={_HEADER_Y})"
    if y1 >= _FOOTER_Y and (
        _FOOTER_RE.search(compact) or re.fullmatch(r"\d{6,}", compact) is not None
    ):
        return True, f"命中底端页脚区(y1={y1:.3f}>={_FOOTER_Y}) 且命中页码/邮编"
    return False, "正常保留"


def _poly_to_bbox(poly: Any) -> list[list[float]] | None:
    if hasattr(poly, "tolist"):
        poly = poly.tolist()
    if not poly:
        return None
    if isinstance(poly, (list, tuple)) and poly and isinstance(poly[0], (int, float)):
        if len(poly) >= 4:
            left, top, right, bottom = [float(v) for v in poly[:4]]
            return [[left, top], [right, top], [right, bottom], [left, bottom]]
        return None
    parsed: list[list[float]] = []
    for pt in poly:
        if hasattr(pt, "tolist"):
            pt = pt.tolist()
        if isinstance(pt, dict):
            x, y = pt.get("x"), pt.get("y")
            if x is not None and y is not None:
                parsed.append([float(x), float(y)])
        elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
            parsed.append([float(pt[0]), float(pt[1])])
    if len(parsed) < 4:
        return None
    return parsed[:4]


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
    xs, ys = [], []
    for b in boxes:
        l, t, r, bot = _bbox_rect(b)
        xs.extend([l, r])
        ys.extend([t, bot])
    return [[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]]


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
        clusters: list[list[dict]] = [[row[0]]]
        for part in row[1:]:
            prev_bbox = _bbox_rect(clusters[-1][-1]["bbox"])
            curr_bbox = _bbox_rect(part["bbox"])
            gap = curr_bbox[0] - prev_bbox[2]
            max_gap = max(median * 2.0, 32.0)
            if gap <= max_gap:
                clusters[-1].append(part)
            else:
                clusters.append([part])
        for cluster in clusters:
            if len(cluster) == 1:
                merged.append(cluster[0])
                continue
            confs = [float(item["conf"]) for item in cluster if item.get("conf") is not None]
            item_merged: dict[str, Any] = {
                "text": _join_row_texts([str(part["text"]) for part in cluster]),
                "bbox": _union_bbox([part["bbox"] for part in cluster]),
            }
            if confs:
                item_merged["conf"] = round(sum(confs) / len(confs), 4)
            merged.append(item_merged)
    return merged + orphans


# =========================================================================
# 2. 调用 PaddleOCR 并提取
# =========================================================================
def run_paddle_ocr_diagnostic(image_path: str):
    path_obj = Path(image_path).resolve()
    if not path_obj.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")

    from PIL import Image

    with Image.open(str(path_obj)) as img:
        img_width, img_height = img.size
    image_size = (img_width, img_height)

    print("=" * 80)
    print(f"【PaddleOCR 单图识别与排查诊断】")
    print(f"目标图片: {path_obj}")
    print(f"图片尺寸: {img_width} x {img_height} (宽 x 高)")
    print("=" * 80)

    # 尝试构建 PaddleOCR
    from paddleocr import PaddleOCR

    device = os.getenv("PADDLE_OCR_DEVICE", "cpu").strip() or "cpu"
    det = os.getenv("PADDLE_OCR_DET_MODEL", "PP-OCRv5_server_det").strip()
    rec = os.getenv("PADDLE_OCR_REC_MODEL", "PP-OCRv5_server_rec").strip()

    print(f"\n[1] 正在初始化 PaddleOCR 引擎 (device={device})...")
    engine = None
    try:
        engine = PaddleOCR(
            text_detection_model_name=det,
            text_recognition_model_name=rec,
            device=device,
            use_doc_orientation_classify=True,
            use_textline_orientation=True,
        )
        print(" -> 已成功初始化 PP-OCRv5 专用模型引擎 (predict 模式)")
    except TypeError:
        print(" -> 当前 PaddleOCR 版本不支持 PP-OCRv5 构造参数，回退至 PaddleOCR(lang='ch', use_angle_cls=True)")
        engine = PaddleOCR(use_angle_cls=True, lang="ch")

    print("\n[2] 开始执行 OCR 推理...")
    t0 = time.monotonic()
    raw_texts = []
    raw_scores = []
    raw_polys = []

    # 判断是 3.x predict 还是 2.x ocr
    if hasattr(engine, "predict"):
        raw_result = engine.predict(str(path_obj))
        # 解析返回格式
        items = raw_result if isinstance(raw_result, list) else [raw_result]
        for it in items:
            res_dict = it.get("res", it) if isinstance(it, dict) else (getattr(it, "json", None) or {})
            if isinstance(res_dict, str):
                try:
                    res_dict = json.loads(res_dict)
                except Exception:
                    res_dict = {}
            if isinstance(res_dict, dict) and "res" in res_dict and isinstance(res_dict["res"], dict):
                res_dict = res_dict["res"]
            raw_texts.extend(res_dict.get("rec_texts") or [])
            raw_scores.extend(res_dict.get("rec_scores") or [])
            polys = res_dict.get("rec_polys")
            if polys is None or len(polys) == 0:
                polys = res_dict.get("rec_boxes") or res_dict.get("dt_polys") or []
            raw_polys.extend(polys or [])
    else:
        # PaddleOCR 2.x ocr(path, cls=True) 模式
        res_list = engine.ocr(str(path_obj), cls=True)
        if res_list and isinstance(res_list[0], list):
            for line_item in res_list[0]:
                poly, (text, conf) = line_item
                raw_texts.append(text)
                raw_scores.append(conf)
                raw_polys.append(poly)

    dur = time.monotonic() - t0
    total_raw = len(raw_texts)
    print(f" -> 推理耗时: {dur:.2f}s, 检测到原生文本框数量: {total_raw}")

    # =========================================================================
    # [3] 详细列出所有原生检测框及其在图片中的垂直位置
    # =========================================================================
    print(f"\n[3] 原生 OCR 检测框清单 (共 {total_raw} 个):")
    print(f"{'序号':<4} | {'垂直范围 (y0~y1)':<18} | {'占比 (y1/H)':<10} | {'置信度':<6} | {'识别文本'}")
    print("-" * 80)
    raw_items = []
    for idx, text in enumerate(raw_texts):
        conf = float(raw_scores[idx]) if idx < len(raw_scores) else 1.0
        poly = raw_polys[idx] if idx < len(raw_polys) else None
        bbox = _poly_to_bbox(poly)
        y_str, y_ratio_str = "无坐标", "N/A"
        y1_ratio = 0.0
        if bbox:
            l, t, r, b = _bbox_rect(bbox)
            y_str = f"{t:4.0f} ~ {b:4.0f}"
            y1_ratio = b / img_height
            y_ratio_str = f"{y1_ratio * 100:5.1f}%"
        raw_items.append({
            "idx": idx,
            "text": text,
            "conf": round(conf, 4),
            "bbox": bbox,
            "y1_ratio": y1_ratio,
        })
        print(f"{idx+1:<4} | {y_str:<18} | {y_ratio_str:<10} | {conf:0.4f} | {text}")

    # =========================================================================
    # [4] 执行 tools/ocr/paddle_ocr.py 中的同行合并 (_merge_same_row)
    # =========================================================================
    valid_lines = []
    for item in raw_items:
        if item["conf"] < _MIN_CONF or not item["text"].strip():
            continue
        valid_lines.append({"text": item["text"].strip(), "conf": item["conf"], "bbox": item["bbox"]})

    merged_lines = _merge_same_row(valid_lines)
    print(f"\n[4] 同行片段智能合并 (_merge_same_row):")
    print(f" -> 合并前: {len(valid_lines)} 行 -> 合并后: {len(merged_lines)} 行")

    # =========================================================================
    # [5] 执行边缘去噪判断 (_is_paddle_chrome)
    # =========================================================================
    print(f"\n[5] 边缘去噪与页眉页脚检测 (_is_paddle_chrome):")
    retained_lines = []
    dropped_lines = []
    for item in merged_lines:
        is_chrome, reason = _is_paddle_chrome(item["text"], item.get("bbox"), image_size)
        if is_chrome:
            dropped_lines.append((item, reason))
        else:
            retained_lines.append(item)

    if dropped_lines:
        print(f" -> 共有 {len(dropped_lines)} 行被判定为噪点并丢弃:")
        for item, reason in dropped_lines:
            print(f"    [丢弃] 原因: {reason} | 文本: {item['text']}")
    else:
        print(f" -> 没有行被 _is_paddle_chrome 丢弃 (0/len(merged_lines))")

    print(f" -> 最终 PaddleOCR 返回保留行数: {len(retained_lines)} 行 (与线上 retained={len(retained_lines)} 对应)")

    # =========================================================================
    # [6] 组装给下游 LLM 的纯文本内容 (user_content)
    # =========================================================================
    user_content = "\n".join(item["text"] for item in retained_lines if item.get("text"))
    print("\n" + "=" * 80)
    print(f"【送入下游 LLM (reconstruct_agenda_markdown) 的完整文本 (共 {len(retained_lines)} 行)】:")
    print("=" * 80)
    for i, line_text in enumerate(user_content.split("\n"), 1):
        print(f"{i:02d}: {line_text}")

    # =========================================================================
    # [7] 关键底部议题专项诊断 (SpeechASR)
    # =========================================================================
    print("\n" + "=" * 80)
    print("【关键底部议题专项诊断排查 (SpeechASR / 最后一行议题)】:")
    print("=" * 80)
    speech_asr_raw = [item for item in raw_items if "speech" in item["text"].lower() or "1.4.5.302" in item["text"]]
    if speech_asr_raw:
        for it in speech_asr_raw:
            print(f"✅ [原生 OCR 阶段] 成功检测到包含 SpeechASR 的文本框:")
            print(f"   - 原始文本: {it['text']}")
            print(f"   - 置信度: {it['conf']}")
            print(f"   - 垂直高度占比 (y1/H): {it['y1_ratio']*100:.2f}%")
    else:
        print("❌ [原生 OCR 阶段] 未在原生检测框中找到 SpeechASR 关键字！请检查检测模型是否切掉了底部！")

    speech_asr_retained = [item for item in retained_lines if "speech" in item["text"].lower() or "1.4.5.302" in item["text"]]
    if speech_asr_retained:
        for it in speech_asr_retained:
            print(f"✅ [后处理留存阶段] SpeechASR 成功保留在 retained 列表中:")
            print(f"   - 保留文本: {it['text']}")
            print(f"   - 状态: 已进入下游送给 LLM 的 user_content 中！")
    else:
        print("❌ [后处理留存阶段] SpeechASR 在后处理（合并或去噪）中被丢弃！")

    # =========================================================================
    # [8] 输出结果落盘保存
    # =========================================================================
    out_dir = ROOT / "logs" / "agenda_ocr"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "debug_paddle_ocr_single_output.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"图片: {path_obj}\n")
        f.write(f"尺寸: {img_width} x {img_height}\n")
        f.write(f"原生检测框数: {total_raw}, 最终保留行数: {len(retained_lines)}\n\n")
        f.write("=== 最终输出给 LLM 的文本 ===\n")
        f.write(user_content + "\n")
    print(f"\n[8] 完整诊断报告与提取文本已落盘至:\n    {out_file.resolve()}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PaddleOCR 单图识别与排查脚本")
    parser.add_argument(
        "image_path",
        nargs="?",
        default=str(DEFAULT_IMAGE),
        help=f"待识别的图片绝对路径或相对路径 (默认: {DEFAULT_IMAGE.name})",
    )
    args = parser.parse_args()
    run_paddle_ocr_diagnostic(args.image_path)
