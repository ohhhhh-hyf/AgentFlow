"""逐图检查页眉/页脚自适应判定（离线，带 OCR 结果缓存以便反复调参）。

用法：
    python tools/scripts/chrome_check.py [--dir 目录] [图片名...]
        [--expect-drop 词1,词2] [--expect-keep 词1,词2]

默认跑 ``data/1/docs`` 下全部 .jpg。首次运行会调引擎并把原始行缓存到系统
临时目录，之后改阈值重跑不再重复 OCR。

``--expect-drop`` / ``--expect-keep`` 是**可选**的期望词表：给了才做
"污染残留 / 正文被误杀" 的汇总判定（不给就只打印每图的判定明细），
避免把任何个案词表固化在脚本里。
"""

from __future__ import annotations

import argparse
import json
import re
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

DEFAULT_DIR = ROOT / "data" / "1" / "docs"


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


def _natural_key(path: Path):
    """图片按文件名末尾的数字排序（没有数字就按名字）。"""
    numbers = re.findall(r"\d+", path.stem)
    return (int(numbers[-1]) if numbers else 0, path.name)


def main() -> int:
    from PIL import Image

    ap = argparse.ArgumentParser(description="逐图检查页眉/页脚判定")
    ap.add_argument("images", nargs="*", help="图片名（默认取 --dir 下全部 .jpg）")
    ap.add_argument("--dir", default=str(DEFAULT_DIR), help=f"图片目录（默认 {DEFAULT_DIR}）")
    ap.add_argument("--expect-drop", default="", help="期望被丢弃的词，逗号分隔（可空）")
    ap.add_argument("--expect-keep", default="", help="期望保留的词，逗号分隔（可空）")
    args = ap.parse_args()

    def _tokens(raw: str) -> tuple[str, ...]:
        return tuple(t.strip() for t in (raw or "").split(",") if t.strip())

    expect_drop = _tokens(args.expect_drop)
    expect_keep = _tokens(args.expect_keep)

    folder = Path(args.dir)
    images = (
        [folder / n for n in args.images]
        if args.images
        else sorted(folder.glob("*.jpg"), key=_natural_key)
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
        for token in expect_drop:
            if token in blob:
                bad_hits.append(f"{image.name}: 残留 {token!r}")
        for token in expect_keep:
            if token not in blob:
                keep_missing.append(f"{image.name}: 丢失 {token!r}")
        print(f"\n=== {image.name} 行数={len(lines)} 丢弃={dropped}")
        if header:
            print(f"    header: {header}")
        if footer:
            print(f"    footer: {footer}")
        print(f"    first3: {survivors[:3]}")
        print(f"    last3 : {survivors[-3:]}")
    if expect_drop or expect_keep:
        print("\n--- 汇总（按你给的期望词表） ---")
        print(f"污染残留: {bad_hits or '无'}")
        print(f"正文被误杀: {keep_missing or '无'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
