"""在独立 OCR 环境（.ocrvenv）中执行的识别脚本。

被 tools/ocr/engines.run_ocr_subprocess 以子进程调用：
    python tools/ocr/runner_ocr.py --input 图.png            → {"lines": [...]}
    python tools/ocr/runner_ocr.py --input 公式块.png --formula → {"formula": "..."}

输出 JSON 到 stdout（OCR 引擎日志不影响解析，上层读取最后一行 JSON）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(ROOT / ".paddlex_cache"))


def _to_list(value):
    """兼容 PaddleOCR 返回的 numpy array。"""
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def _ocr_text_paddle(path: str) -> dict:
    """PaddleOCR 3.x 文字识别。"""
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(
        lang="ch",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    results = ocr.predict(path)
    lines: list[dict] = []
    for page in results or []:
        texts = list(page.get("rec_texts") or [])
        scores = list(page.get("rec_scores") or [])
        polys = page.get("rec_polys")
        if polys is None or len(polys) == 0:
            polys = page.get("dt_polys")
        if polys is None:
            polys = []
        for idx, text in enumerate(texts):
            text = str(text).strip()
            if not text:
                continue
            conf = float(scores[idx]) if idx < len(scores) else 0.0
            box = _to_list(polys[idx]) if idx < len(polys) else None
            lines.append({"text": text, "conf": conf, "bbox": box})
    payload = {"engine": "paddleocr", "lines": lines}
    payload["visual_regions"] = _detect_visual_regions_safe(path, lines)
    return payload


def _ocr_text_rapid(path: str) -> dict:
    """RapidOCR 兜底文字识别。"""
    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    result, _ = ocr(path)
    lines: list[dict] = []
    for item in result or []:
        # item = [bbox(4点), text, conf]
        box, text, conf = item[0], item[1], item[2]
        lines.append({"text": str(text), "conf": float(conf), "bbox": box})
    payload = {"engine": "rapidocr", "lines": lines}
    payload["visual_regions"] = _detect_visual_regions_safe(path, lines)
    return payload


def _detect_visual_regions_safe(path: str, lines: list[dict]) -> list[dict]:
    try:
        from tools.ocr.visual_regions import detect_visual_regions

        return detect_visual_regions(path, lines)
    except Exception:
        return []


def _ocr_text_server(path: str) -> dict:
    """调用服务器 OCR；失败或空结果时降级 RapidOCR。"""
    from tools.ocr.server_ocr import ocr_image

    try:
        payload = ocr_image(path)
        if payload.get("lines"):
            return payload
        fallback = _ocr_text_rapid(path)
        fallback["engine"] = "rapidocr"
        fallback["fallback_from"] = "serverocr"
        fallback["fallback_reason"] = "serverocr 返回空结果"
        return fallback
    except Exception as server_exc:  # noqa: BLE001
        fallback = _ocr_text_rapid(path)
        fallback["engine"] = "rapidocr"
        fallback["fallback_from"] = "serverocr"
        fallback["fallback_reason"] = str(server_exc)
        return fallback


def _ocr_text(path: str) -> dict:
    """按 OCR_ENGINE 选择引擎；默认 RapidOCR，服务器 OCR 可选。"""
    engine = os.environ.get("OCR_ENGINE", "rapidocr").strip().lower()
    if engine in {"server", "serverocr", "remote"}:
        return _ocr_text_server(path)
    if engine in {"paddle", "paddleocr"}:
        try:
            return _ocr_text_paddle(path)
        except Exception as paddle_exc:  # noqa: BLE001
            payload = _ocr_text_rapid(path)
            payload["fallback_reason"] = str(paddle_exc)
            return payload
    if engine in {"auto", "best"}:
        return _ocr_text_auto(path)
    try:
        return _ocr_text_rapid(path)
    except Exception as rapid_exc:  # noqa: BLE001
        payload = _ocr_text_paddle(path)
        payload["fallback_reason"] = str(rapid_exc)
        return payload


def _ocr_text_auto(path: str) -> dict:
    """实验模式：本地引擎都跑，按简单质量分选择。"""
    candidates: list[dict] = []
    errors: list[str] = []
    for name, fn in (("rapidocr", _ocr_text_rapid), ("paddleocr", _ocr_text_paddle)):
        try:
            payload = fn(path)
            payload["quality_score"] = _quality_score(payload.get("lines") or [])
            candidates.append(payload)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
    if not candidates:
        raise RuntimeError("; ".join(errors) or "没有可用 OCR 引擎")
    candidates.sort(key=lambda item: item.get("quality_score") or 0, reverse=True)
    best = candidates[0]
    best["auto_candidates"] = [
        {
            "engine": item.get("engine"),
            "quality_score": item.get("quality_score"),
            "line_count": len(item.get("lines") or []),
        }
        for item in candidates
    ]
    if errors:
        best["auto_errors"] = errors
    return best


def _quality_score(lines: list[dict]) -> float:
    if not lines:
        return 0.0
    texts = [str(item.get("text") or "").strip() for item in lines]
    useful = [txt for txt in texts if txt and len(txt) > 1 and txt.lower() not in {"no:", "date:"}]
    avg_conf = sum(float(item.get("conf") or 0.0) for item in lines) / max(1, len(lines))
    char_count = sum(len(txt) for txt in useful)
    noise = sum(1 for txt in texts if len(txt) <= 1 or txt.lower() in {"no:", "date:"})
    return char_count * 0.04 + len(useful) * 0.8 + avg_conf * 6 - noise * 0.6


def _ocr_formula(path: str) -> dict:
    try:
        from pix2tex.cli import LatexOCR

        ocr = LatexOCR()
        latex = ocr(path)
        return {"formula": str(latex)}
    except ImportError:
        # LaTeX-OCR 未安装 → 空公式（上层降级为文字）
        return {"formula": ""}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="图片路径")
    parser.add_argument("--formula", action="store_true", help="公式模式（LaTeX-OCR）")
    args = parser.parse_args()
    try:
        if args.formula:
            payload = _ocr_formula(args.input)
        else:
            payload = _ocr_text(args.input)
    except Exception as exc:  # noqa: BLE001
        _write_json_line({"error": str(exc)})
        return 1
    _write_json_line(payload)
    return 0


def _write_json_line(payload: dict) -> None:
    """Write UTF-8 JSON regardless of the Windows console code page."""
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    sys.exit(main())
