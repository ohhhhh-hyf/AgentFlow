"""OCR CLI：``python -m tools.ocr.cli --input 图.png --output 笔记.md``

示例：
    python -m tools.ocr.cli --input page1.png page2.jpg --output notes.md
    python -m tools.ocr.cli --input 图.png --engine serverocr --output notes.md
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.ocr import ocr_images_to_markdown  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR 笔记还原：图片 → Markdown")
    parser.add_argument("--input", nargs="+", required=True, help="图片路径（可多张=多页）")
    parser.add_argument("--output", default="", help="输出 .md 路径（不传则打印到终端）")
    parser.add_argument(
        "--engine",
        choices=("rapidocr", "serverocr", "paddleocr", "auto"),
        default="rapidocr",
        help="文字 OCR 引擎：rapidocr 默认；serverocr 调服务器接口；paddleocr 可对照；auto 会本地两套粗略择优",
    )
    args = parser.parse_args()

    for path in args.input:
        if not Path(path).exists():
            print(f"文件不存在：{path}", file=sys.stderr)
            return 1

    old_engine = os.environ.get("OCR_ENGINE")
    os.environ["OCR_ENGINE"] = args.engine
    try:
        text = ocr_images_to_markdown(
            args.input,
            output=args.output or None,
            use_llm=True,
        )
    finally:
        if old_engine is None:
            os.environ.pop("OCR_ENGINE", None)
        else:
            os.environ["OCR_ENGINE"] = old_engine
    if not args.output:
        print(text)
    else:
        print(f"已写入：{args.output}（{len(text)} 字符）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
