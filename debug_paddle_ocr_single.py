# -*- coding: utf-8 -*-
"""debug_paddle_ocr_single.py -- 单图 PaddleOCR 识别与排查提取脚本

用于独立复现和查看 PaddleOCR 对单张议程图片的完整识别流程与返回内容。
包含：
1. PaddleOCR 引擎原生识别（raw_texts / raw_polys）
2. 行提取与同水平行合并（_merge_same_row，来自 tools.ocr.paddle_ocr）
3. 边缘去噪与页眉页脚过滤（_is_paddle_chrome）
4. 版面分列排版（prepare_agenda_ocr_prompt_text，过滤左侧装饰侧栏，保留水平列间距）
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

from tools.ocr.paddle_ocr import (
    _bbox_rect,
    _is_paddle_chrome,
    _join_row_texts,
    _merge_same_row,
    _poly_to_bbox,
    _MIN_CONF,
)
from domain.meeting.tasks.agenda_minutes.agenda_extractor import (
    prepare_agenda_ocr_prompt_text,
    apply_agenda_completeness_guardrail,
)


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
        is_chrome = _is_paddle_chrome(item["text"], item.get("bbox"), image_size)
        if is_chrome:
            dropped_lines.append(item)
        else:
            retained_lines.append(item)

    if dropped_lines:
        print(f" -> 共有 {len(dropped_lines)} 行被判定为噪点并丢弃:")
        for item in dropped_lines:
            print(f"    [丢弃] 文本: {item['text']}")
    else:
        print(f" -> 没有行被 _is_paddle_chrome 丢弃 (0/len(merged_lines))")

    print(f" -> 最终 PaddleOCR 返回保留行数: {len(retained_lines)} 行 (与线上 retained={len(retained_lines)} 对应)")

    # =========================================================================
    # [6] 优化版面排版结构 (prepare_agenda_ocr_prompt_text)
    # =========================================================================
    structured_prompt_text = prepare_agenda_ocr_prompt_text(retained_lines)
    print("\n" + "=" * 80)
    print(f"【前置版面优化后的结构化提示词文本 (过滤侧栏噪点，按水平行分列)】:")
    print("=" * 80)
    for i, line_text in enumerate(structured_prompt_text.split("\n"), 1):
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
        f.write("=== 前置版面优化后的结构化文本 ===\n")
        f.write(structured_prompt_text + "\n")
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
