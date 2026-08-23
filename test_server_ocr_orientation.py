"""Quickly test whether the configured server OCR handles image orientation.

Usage:
    python test_server_ocr_orientation.py examples/U202314948_1.jpg

The script rotates the same image by 0/90/180/270 degrees and sends each
variant directly to the server OCR adapter. It intentionally bypasses the
RapidOCR fallback so the result reflects the server OCR only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _chinese_ratio(text: str) -> float:
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return 0.0
    chinese = sum(1 for ch in chars if "\u4e00" <= ch <= "\u9fff")
    return chinese / len(chars)


def _avg_conf(lines: list[dict[str, Any]]) -> float | None:
    values: list[float] = []
    for line in lines:
        value = line.get("conf")
        if isinstance(value, (int, float)):
            values.append(float(value))
    return mean(values) if values else None


def _char_bigrams(text: str) -> set[str]:
    compact = "".join(ch for ch in text if not ch.isspace())
    if len(compact) < 2:
        return set(compact)
    return {compact[i : i + 2] for i in range(len(compact) - 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _collect_result(angle: int, image_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    lines = payload.get("lines") or []
    texts = [str(item.get("text", "")).strip() for item in lines if isinstance(item, dict)]
    text = "\n".join(t for t in texts if t)
    avg_conf = _avg_conf(lines)
    score = len(text) * (0.4 + _chinese_ratio(text))
    return {
        "rotation_degrees": angle,
        "temp_image": str(image_path),
        "line_count": len([t for t in texts if t]),
        "text_chars": len(text),
        "chinese_ratio": round(_chinese_ratio(text), 4),
        "avg_conf": round(avg_conf, 6) if avg_conf is not None else None,
        "rough_score": round(score, 2),
        "preview": [t for t in texts if t][:12],
        "text": text,
    }


def _print_result(result: dict[str, Any]) -> None:
    print("=" * 72)
    print(f"rotation_degrees: {result['rotation_degrees']}")
    print(f"temp_image: {result['temp_image']}")
    print(f"line_count: {result['line_count']}")
    print(f"text_chars: {result['text_chars']}")
    print(f"chinese_ratio: {result['chinese_ratio']:.3f}")
    if result["avg_conf"] is None:
        print("avg_conf: N/A")
    else:
        print(f"avg_conf: {result['avg_conf']:.4f}")
    print(f"rough_score: {result['rough_score']:.1f}")
    print("preview:")
    for item in result["preview"]:
        print(f"  {item}")


def _analyze(results: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [item for item in results if not item.get("error")]
    if not ok:
        return {
            "verdict": "all_failed",
            "message": "所有旋转角度都调用失败，先检查服务器 OCR 地址、鉴权或网络。",
        }

    ordered = sorted(ok, key=lambda item: item.get("rough_score", 0), reverse=True)
    best = ordered[0]
    worst = ordered[-1]
    best_score = float(best.get("rough_score") or 0)
    worst_score = float(worst.get("rough_score") or 0)
    score_ratio = (worst_score / best_score) if best_score > 0 else 0.0

    similarities: list[dict[str, Any]] = []
    for item in ok:
        if item is best:
            continue
        similarities.append(
            {
                "angle": item["rotation_degrees"],
                "similarity_to_best": round(
                    _jaccard(_char_bigrams(best.get("text", "")), _char_bigrams(item.get("text", ""))),
                    4,
                ),
            }
        )
    min_similarity = min((x["similarity_to_best"] for x in similarities), default=1.0)

    if len(ok) >= 4 and score_ratio >= 0.65 and min_similarity >= 0.35:
        verdict = "likely_orientation_adaptive"
        message = (
            "四个方向的文本量和内容相似度都比较接近，服务器 OCR 很可能具备方向自适应。"
        )
    elif len(ok) >= 2 and score_ratio < 0.35:
        verdict = "likely_orientation_sensitive"
        message = (
            "不同旋转角度的识别分数差异很大，服务器 OCR 很可能对方向敏感，调用前需要旋正。"
        )
    else:
        verdict = "inconclusive"
        message = (
            "结果不够明确，需要结合每个角度的 preview 判断；可能有一定方向能力，但不稳定。"
        )

    return {
        "verdict": verdict,
        "message": message,
        "best_rotation_degrees": best["rotation_degrees"],
        "best_score": best_score,
        "worst_rotation_degrees": worst["rotation_degrees"],
        "worst_score": worst_score,
        "score_ratio_worst_to_best": round(score_ratio, 4),
        "min_similarity_to_best": min_similarity,
        "similarities": similarities,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test server OCR orientation handling with 0/90/180/270 rotations."
    )
    parser.add_argument("image", help="Path to a PNG/JPG/JPEG image.")
    parser.add_argument(
        "--env",
        default=str(ROOT / ".env"),
        help="Path to .env. Defaults to project root .env.",
    )
    args = parser.parse_args()

    _load_env_file(Path(args.env))

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Image not found: {image_path}", file=sys.stderr)
        return 2

    from tools.ocr.server_ocr import ocr_image

    print("Server OCR orientation test")
    print(f"source_image: {image_path.resolve()}")
    print(f"server_url: {os.getenv('SERVER_OCR_URL', 'http://10.33.111.33:8080/service')}")
    print("tip: Copy the whole terminal output to me if you want a diagnosis.")
    print("tip: If only one rotation is good, the caller should rotate before OCR.")

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="agentflow_server_ocr_orientation_") as temp_dir:
        temp_root = Path(temp_dir)
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            for angle in (0, 90, 180, 270):
                rotated = image.rotate(angle, expand=True)
                rotated_path = temp_root / f"{image_path.stem}_rotate_{angle}.jpg"
                rotated.save(rotated_path, format="JPEG", quality=90, optimize=True)
                try:
                    payload = ocr_image(str(rotated_path))
                except Exception as exc:  # noqa: BLE001
                    print("=" * 72)
                    print(f"rotation_degrees: {angle}")
                    print(f"error: {type(exc).__name__}: {exc}")
                    results.append(
                        {
                            "rotation_degrees": angle,
                            "temp_image": str(rotated_path),
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
                    continue
                result = _collect_result(angle, rotated_path, payload)
                results.append(result)
                _print_result(result)

    analysis = _analyze(results)
    summary = {
        "source_image": str(image_path.resolve()),
        "server_url": os.getenv("SERVER_OCR_URL", "http://10.33.111.33:8080/service"),
        "analysis": analysis,
        "results": [
            {key: value for key, value in item.items() if key != "text"}
            for item in results
        ],
    }

    print("=" * 72)
    print("auto_analysis:")
    print(f"  verdict: {analysis['verdict']}")
    print(f"  message: {analysis['message']}")
    if "best_rotation_degrees" in analysis:
        print(f"  best_rotation_degrees: {analysis['best_rotation_degrees']}")
        print(f"  score_ratio_worst_to_best: {analysis['score_ratio_worst_to_best']}")
        print(f"  min_similarity_to_best: {analysis['min_similarity_to_best']}")
    print("=" * 72)
    print("copyable_summary_json:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
