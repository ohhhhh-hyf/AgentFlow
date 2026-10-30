#!/usr/bin/env python
"""本地调用 visual_minutes 生成图文纪要。

用法：
    python test_visual_minutes.py 纪要.md 会议文本.txt
    python test_visual_minutes.py 纪要.md 会议文本.txt -o 输出.html

不传输出路径时，默认在纪要同目录生成 ``<纪要文件名>_visual.html``。
LLM 连接、API Key、模型、vLLM / WebSocket 等全部由项目根目录 .env 决定。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from domains.shared.visual_minutes import generate_visual_minutes


def _read_text(path: Path, label: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"{label}不存在：{path}")
    return path.read_text(encoding="utf-8-sig")


def _default_output(minutes_path: Path) -> Path:
    return minutes_path.with_name(f"{minutes_path.stem}_visual.html")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="读取纪要 Markdown 与会议文本，调用 visual_minutes 生成图文纪要 HTML。",
    )
    parser.add_argument("minutes", help="纪要 Markdown 文件路径")
    parser.add_argument("transcript", help="会议文本 txt 文件路径")
    parser.add_argument(
        "-o",
        "--output",
        help="输出 HTML 路径；不传则生成 <纪要文件名>_visual.html",
    )
    args = parser.parse_args(argv)

    minutes_path = Path(args.minutes).expanduser().resolve()
    transcript_path = Path(args.transcript).expanduser().resolve()
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else _default_output(minutes_path)
    )
    if output_path.is_dir():
        output_path = output_path / _default_output(minutes_path).name

    print(f"纪要：{minutes_path}")
    print(f"原文：{transcript_path}")
    print(f"输出：{output_path}")

    minutes_markdown = _read_text(minutes_path, "纪要文件")
    meeting_transcript = _read_text(transcript_path, "会议文本")

    result = generate_visual_minutes(
        minutes_markdown,
        meeting_transcript,
        output_path=str(output_path),
    )

    kinds = [
        f"{item.section_id}:{item.visual.kind}"
        for item in result.ir.sections
        if item.visual is not None
    ]
    print(f"完成：{output_path}")
    print(f"正文视觉：{', '.join(kinds) if kinds else '无'}")
    print(f"HTML 字符数：{len(result.html)}")

    if result.warnings:
        print("警告：")
        for warning in result.warnings:
            print(f"  - {warning}")
    else:
        print("警告：无")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - CLI 入口统一给出可读错误
        print(f"生成失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
