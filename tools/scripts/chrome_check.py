"""逐图检查页眉/页脚自适应判定（离线，带 OCR 结果缓存以便反复调参）。

用法：
    python tools/scripts/chrome_check.py [图片名...]

默认跑 data/1/docs 下全部 U202314751_*.jpg。首次运行会调引擎并把原始行
缓存到系统临时目录，之后改阈值重跑不再重复 OCR。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client.config import load_env  # noqa: E402

load_env(ROOT / ".env")  # 与服务器一致：OCR_ENGINE / OCR_PARALLEL 等从这里来

from tools.ocr import layout as L  # noqa: E402
from tools.ocr.engines import run_ocr_subprocess  # noqa: E402

CACHE = Path(tempfile.gettempdir()) / "agentflow_ocr_cache"
CACHE.mkdir(parents=True, exist_ok=True)

# 期望被丢弃的页眉/页脚残留（实测来自服务器 merged md 与目录污染）
BAD = ("科技", "華中", "华中", "HAUZHONG", "HUAZHONG", "印刷厂", "UNIVERSITY", "Tel", "明德", "P.R.China")
# 期望保留的正文行（实测来自 _15/_16 的正文起点）
KEEP = ("算符", "角动量")


def raw_payload(image: Path) -> dict:
    cached = CACHE / f"{image.stem}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    payload = run_ocr_subprocess(str(image))
    cached.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def to_lines(payload: dict) -> list[dict]:
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
    return lines


def main() -> int:
    from PIL import Image

    names = sys.argv[1:]
    folder = ROOT / "data" / "1" / "docs"
    images = [folder / n for n in names] if names else sorted(
        folder.glob("U202314751_*.jpg"), key=lambda p: int(p.stem.rsplit("_", 1)[1])
    )
    bad_hits: list[str] = []
    keep_missing: list[str] = []
    for image in images:
        payload = raw_payload(image)
        lines = to_lines(payload)
        lines = L._infer_layout_hints(lines, Image.open(image).size)
        dropped = L._mark_page_chrome(lines)
        survivors = [str(ln.get("text") or "") for ln in lines if ln.get("role_hint") != "boilerplate"]
        header = [str(ln.get("text") or "") for ln in lines if ln.get("chrome_zone") == "header"]
        footer = [str(ln.get("text") or "") for ln in lines if ln.get("chrome_zone") == "footer"]
        blob = "\n".join(survivors)
        for token in BAD:
            if token in blob:
                bad_hits.append(f"{image.name}: 残留 {token!r}")
        if any(t in blob for t in KEEP):
            pass
        print(f"\n=== {image.name} 行数={len(lines)} 丢弃={dropped}")
        if header:
            print(f"    header: {header}")
        if footer:
            print(f"    footer: {footer}")
        print(f"    first3: {survivors[:3]}")
        print(f"    last3 : {survivors[-3:]}")
    print("\n--- 汇总 ---")
    print(f"污染残留: {bad_hits or '无'}")
    if keep_missing:
        print(f"正文被误杀: {keep_missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
