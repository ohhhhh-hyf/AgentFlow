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
7. 方案 A+B 优化对比：底部预填充 100px + 禁用 doc_orientation_classify
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
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


def _pad_image_bottom(image_path: str, pad_px: int = 100) -> str | None:
    """在图片底部添加白色填充，防止 OCR 检测模型边缘截断导致末尾行丢失。"""
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            w, h = img.size
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            new_img = Image.new("RGB", (w, h + pad_px), (255, 255, 255))
            new_img.paste(img, (0, 0))
            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            new_img.save(tmp_path)
            return tmp_path
    except Exception as exc:
        logger.warning("pad_image_bottom failed: %s", exc)
        return None


def _build_engine(use_doc_orientation: bool = True):
    """构建 PaddleOCR 引擎，可控制 use_doc_orientation_classify 参数。"""
    from paddleocr import PaddleOCR

    device = os.getenv("PADDLE_OCR_DEVICE", "cpu").strip() or "cpu"
    det = os.getenv("PADDLE_OCR_DET_MODEL", "PP-OCRv5_server_det").strip()
    rec = os.getenv("PADDLE_OCR_REC_MODEL", "PP-OCRv5_server_rec").strip()
    try:
        engine = PaddleOCR(
            text_detection_model_name=det,
            text_recognition_model_name=rec,
            device=device,
            use_doc_orientation_classify=use_doc_orientation,
            use_textline_orientation=True,
        )
        mode_str = "doc_orient=ON" if use_doc_orientation else "doc_orient=OFF"
        print(f" -> 已成功初始化 PP-OCRv5 引擎 ({mode_str}, device={device})")
        return engine
    except TypeError:
        print(f" -> 当前 PaddleOCR 不支持 PP-OCRv5 参数，回退至 PaddleOCR(lang='ch')")
        return PaddleOCR(use_angle_cls=True, lang="ch")


def _run_ocr(engine, image_path: str):
    """执行 OCR 推理，返回 (raw_texts, raw_scores, raw_polys, duration)。"""
    t0 = time.monotonic()
    raw_texts, raw_scores, raw_polys = [], [], []

    if hasattr(engine, "predict"):
        raw_result = engine.predict(str(image_path))
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
        res_list = engine.ocr(str(image_path), cls=True)
        if res_list and isinstance(res_list[0], list):
            for line_item in res_list[0]:
                poly, (text, conf) = line_item
                raw_texts.append(text)
                raw_scores.append(conf)
                raw_polys.append(poly)

    dur = time.monotonic() - t0
    return raw_texts, raw_scores, raw_polys, dur


def _process_raw(raw_texts, raw_scores, raw_polys, img_height, image_size):
    """从原生 OCR 结果执行完整后处理流水线，返回 (raw_items, retained_lines, dropped_lines)。"""
    raw_items = []
    for idx, text in enumerate(raw_texts):
        conf = float(raw_scores[idx]) if idx < len(raw_scores) else 1.0
        poly = raw_polys[idx] if idx < len(raw_polys) else None
        bbox = _poly_to_bbox(poly)
        y1_ratio = 0.0
        if bbox:
            _, _, _, b = _bbox_rect(bbox)
            y1_ratio = b / img_height
        raw_items.append({
            "idx": idx,
            "text": text,
            "conf": round(conf, 4),
            "bbox": bbox,
            "y1_ratio": y1_ratio,
        })

    # 过滤低置信度 + 空文本
    valid_lines = []
    for item in raw_items:
        if item["conf"] < _MIN_CONF or not item["text"].strip():
            continue
        valid_lines.append({"text": item["text"].strip(), "conf": item["conf"], "bbox": item["bbox"]})

    # 同行合并
    merged_lines = _merge_same_row(valid_lines)

    # 边缘去噪
    retained_lines, dropped_lines = [], []
    for item in merged_lines:
        if _is_paddle_chrome(item["text"], item.get("bbox"), image_size):
            dropped_lines.append(item)
        else:
            retained_lines.append(item)

    return raw_items, retained_lines, dropped_lines


def _print_raw_boxes(raw_items, img_height, label=""):
    """打印原生检测框列表。"""
    prefix = f" ({label})" if label else ""
    print(f"\n[原生 OCR 检测框清单{prefix}] (共 {len(raw_items)} 个):")
    print(f"{'序号':<4} | {'垂直范围 (y0~y1)':<18} | {'占比 (y1/H)':<10} | {'置信度':<6} | {'识别文本'}")
    print("-" * 80)
    for item in raw_items:
        bbox = item["bbox"]
        y_str, y_ratio_str = "无坐标", "N/A"
        if bbox:
            l, t, r, b = _bbox_rect(bbox)
            y_str = f"{t:4.0f} ~ {b:4.0f}"
            y_ratio_str = f"{item['y1_ratio'] * 100:5.1f}%"
        print(f"{item['idx']+1:<4} | {y_str:<18} | {y_ratio_str:<10} | {item['conf']:0.4f} | {item['text']}")


def run_paddle_ocr_diagnostic(image_path: str):
    path_obj = Path(image_path).resolve()
    if not path_obj.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")

    from PIL import Image

    with Image.open(str(path_obj)) as img:
        img_width, img_height = img.size
    image_size = (img_width, img_height)

    print("=" * 80)
    print(f"【PaddleOCR 单图识别与排查诊断 (含方案 A+B 优化对比)】")
    print(f"目标图片: {path_obj}")
    print(f"图片尺寸: {img_width} x {img_height} (宽 x 高)")
    print("=" * 80)

    # ==========================================================================
    # 阶段 1: 原始模式（与服务器线上一致：doc_orient=ON，原图无填充）
    # ==========================================================================
    print("\n" + "=" * 80)
    print("【阶段 1】 原始模式（doc_orient=ON，原图无填充）—— 与线上服务器行为一致")
    print("=" * 80)

    print("\n[1.1] 初始化原始引擎 (doc_orient=ON)...")
    engine_orig = _build_engine(use_doc_orientation=True)

    print("\n[1.2] 执行 OCR 推理 (原图)...")
    raw_texts_orig, raw_scores_orig, raw_polys_orig, dur_orig = _run_ocr(engine_orig, str(path_obj))
    print(f" -> 推理耗时: {dur_orig:.2f}s, 检测到原生文本框: {len(raw_texts_orig)}")

    raw_items_orig, retained_orig, dropped_orig = _process_raw(
        raw_texts_orig, raw_scores_orig, raw_polys_orig, img_height, image_size
    )
    _print_raw_boxes(raw_items_orig, img_height, "原始模式")

    print(f"\n[1.3] 同行合并与去噪:")
    print(f" -> 丢弃 {len(dropped_orig)} 行, 保留 {len(retained_orig)} 行")

    # ==========================================================================
    # 阶段 2: 优化模式（方案 A: 底部填充 100px + 方案 B: doc_orient=OFF）
    # ==========================================================================
    print("\n" + "=" * 80)
    print("【阶段 2】 优化模式（方案 A: 底部填充 100px + 方案 B: doc_orient=OFF）")
    print("=" * 80)

    print("\n[2.1] 初始化议程专用引擎 (doc_orient=OFF)...")
    engine_agenda = _build_engine(use_doc_orientation=False)

    print("\n[2.2] 底部预填充 100px (方案 A)...")
    padded_path = _pad_image_bottom(str(path_obj), pad_px=100)
    if padded_path:
        with Image.open(padded_path) as padded_img:
            pw, ph = padded_img.size
        print(f" -> 填充后尺寸: {pw} x {ph} (原始: {img_width} x {img_height}, +100px)")
    else:
        print(" -> ⚠ 填充失败，使用原图")

    actual_path = padded_path or str(path_obj)
    padded_height = ph if padded_path else img_height
    padded_image_size = (img_width, padded_height)

    print("\n[2.3] 执行 OCR 推理 (填充后 + doc_orient=OFF)...")
    raw_texts_opt, raw_scores_opt, raw_polys_opt, dur_opt = _run_ocr(engine_agenda, actual_path)
    print(f" -> 推理耗时: {dur_opt:.2f}s, 检测到原生文本框: {len(raw_texts_opt)}")

    raw_items_opt, retained_opt, dropped_opt = _process_raw(
        raw_texts_opt, raw_scores_opt, raw_polys_opt, padded_height, padded_image_size
    )
    _print_raw_boxes(raw_items_opt, padded_height, "优化模式")

    print(f"\n[2.4] 同行合并与去噪:")
    print(f" -> 丢弃 {len(dropped_opt)} 行, 保留 {len(retained_opt)} 行")

    # 清理临时文件
    if padded_path:
        try:
            os.unlink(padded_path)
        except OSError:
            pass

    # ==========================================================================
    # 阶段 3: A+B 效果对比
    # ==========================================================================
    print("\n" + "=" * 80)
    print("【阶段 3】 方案 A+B 优化效果对比")
    print("=" * 80)
    delta_raw = len(raw_texts_opt) - len(raw_texts_orig)
    delta_retained = len(retained_opt) - len(retained_orig)
    print(f"  原始模式 → 原生检测框: {len(raw_texts_orig)}, 保留行: {len(retained_orig)}")
    print(f"  优化模式 → 原生检测框: {len(raw_texts_opt)}, 保留行: {len(retained_opt)}")
    print(f"  差异     → 原生 Δ{delta_raw:+d}, 保留 Δ{delta_retained:+d}")

    # ==========================================================================
    # 阶段 4: 前置版面优化（使用优化模式结果）
    # ==========================================================================
    structured_prompt_text = prepare_agenda_ocr_prompt_text(retained_opt)
    print("\n" + "=" * 80)
    print(f"【前置版面优化后的结构化提示词文本 (优化模式)】:")
    print("=" * 80)
    for i, line_text in enumerate(structured_prompt_text.split("\n"), 1):
        print(f"{i:02d}: {line_text}")

    # ==========================================================================
    # 阶段 5: 关键底部议题专项诊断
    # ==========================================================================
    print("\n" + "=" * 80)
    print("【关键底部议题专项诊断排查 (SpeechASR / 最后一行议题)】:")
    print("=" * 80)

    # 检查原始模式
    print("\n--- 原始模式 (doc_orient=ON, 无填充) ---")
    speech_orig = [item for item in raw_items_orig if "speech" in item["text"].lower() or "1.4.5.302" in item["text"]]
    if speech_orig:
        for it in speech_orig:
            print(f"  ✅ 检测到 SpeechASR: {it['text']} (y1={it['y1_ratio']*100:.1f}%)")
    else:
        print(f"  ❌ 未检测到 SpeechASR — OCR 引擎底部截断!")

    # 检查优化模式
    print("\n--- 优化模式 (方案 A+B: 填充 + doc_orient=OFF) ---")
    speech_opt = [item for item in raw_items_opt if "speech" in item["text"].lower() or "1.4.5.302" in item["text"]]
    if speech_opt:
        for it in speech_opt:
            print(f"  ✅ 检测到 SpeechASR: {it['text']} (y1={it['y1_ratio']*100:.1f}%)")
    else:
        print(f"  ❌ 优化模式仍未检测到 SpeechASR!")

    speech_retained = [item for item in retained_opt if "speech" in item["text"].lower() or "1.4.5.302" in item["text"]]
    if speech_retained:
        print(f"  ✅ SpeechASR 已进入最终保留行列表，将被送入 LLM 结构化提取器")
    elif speech_opt:
        print(f"  ⚠ SpeechASR 被检测到但在后处理中被丢弃!")

    # ==========================================================================
    # 阶段 6: 输出落盘
    # ==========================================================================
    out_dir = ROOT / "logs" / "agenda_ocr"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "debug_paddle_ocr_single_output.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"图片: {path_obj}\n")
        f.write(f"尺寸: {img_width} x {img_height}\n\n")
        f.write(f"=== 原始模式 ===\n")
        f.write(f"原生检测框: {len(raw_texts_orig)}, 保留行: {len(retained_orig)}\n")
        f.write(f"SpeechASR 检出: {'是' if speech_orig else '否'}\n\n")
        f.write(f"=== 优化模式 (方案 A+B) ===\n")
        f.write(f"原生检测框: {len(raw_texts_opt)}, 保留行: {len(retained_opt)}\n")
        f.write(f"SpeechASR 检出: {'是' if speech_opt else '否'}\n\n")
        f.write(f"=== 前置版面优化后的结构化文本 (优化模式) ===\n")
        f.write(structured_prompt_text + "\n")
    print(f"\n[6] 完整诊断报告已落盘至:\n    {out_file.resolve()}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PaddleOCR 单图识别与排查脚本 (含 A+B 优化对比)")
    parser.add_argument(
        "image_path",
        nargs="?",
        default=str(DEFAULT_IMAGE),
        help=f"待识别的图片绝对路径或相对路径 (默认: {DEFAULT_IMAGE.name})",
    )
    args = parser.parse_args()
    run_paddle_ocr_diagnostic(args.image_path)
