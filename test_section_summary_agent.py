"""Section Summary Agent 手动测试脚本。

用法（在项目根目录运行）：

    python test_section_summary_agent.py --text "张三 00:00:01\n大家好……"
    python test_section_summary_agent.py --file transcript.txt
    python test_section_summary_agent.py          # 从 stdin 读取，Ctrl+Z 回车 / Ctrl+D 结束

默认使用项目根目录 .env 中配置的 LLM，并保存：

    section_summary_raw.json    模型原始 JSON（无法解析时保存含 raw_response 的对象）
    section_summary_output.md   渲染后的 Markdown
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domains.shared.section_summary import SectionSummaryAgent  # noqa: E402
from domains.shared.section_summary.validation import extract_json_array  # noqa: E402

# 防止 pytest 把本脚本当测试模块收集
__test__ = False


def _read_transcript(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    print(
        "请输入会议原文，结束输入请按 Ctrl+Z 回车（Windows）"
        "或 Ctrl+D（macOS/Linux）："
    )
    return sys.stdin.read()


def _save_raw_json(raw: str, result, path: Path) -> None:
    data = None
    if raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            try:
                data = extract_json_array(raw)
            except Exception:  # noqa: BLE001 - 兜底时保存原始文本与规整结果
                data = None
    if data is None:
        data = {
            "raw_response": raw,
            "sections": [section.model_dump() for section in result.sections],
        }
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Section Summary Agent 手动测试")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text", help="直接传入会议原文")
    source.add_argument("--file", help="从文件读取会议原文（UTF-8）")
    parser.add_argument(
        "--out",
        default=str(ROOT / "section_summary_raw.json"),
        help="原始 JSON 保存路径",
    )
    parser.add_argument(
        "--md-out",
        default=str(ROOT / "section_summary_output.md"),
        help="Markdown 保存路径",
    )
    args = parser.parse_args()

    transcript = _read_transcript(args).strip()
    if not transcript:
        print("没有输入内容。", file=sys.stderr)
        return 1

    try:
        agent = SectionSummaryAgent()
    except Exception as exc:  # noqa: BLE001 - 初始化失败给友好提示
        print(f"初始化 LLM 失败：{exc}", file=sys.stderr)
        return 1

    print(
        f"LLM: backend={agent.client.backend} model={agent.client.model} "
        f"base_url={agent.client.base_url or agent.client.ws_url}",
        file=sys.stderr,
    )
    print(f"输入: {len(transcript)} 字符", file=sys.stderr)

    try:
        result = agent.run(transcript)
    except Exception as exc:  # noqa: BLE001 - 输入解析失败等
        print(f"生成失败：{exc}", file=sys.stderr)
        return 1

    raw_path = Path(args.out)
    md_path = Path(args.md_out)
    _save_raw_json(result.raw_response, result, raw_path)
    md_path.write_text(result.markdown, encoding="utf-8")

    if result.warnings:
        print("Warnings:", file=sys.stderr)
        for warning in result.warnings:
            print(f"  - {warning}", file=sys.stderr)

    print(
        f"原始 JSON: {raw_path} ({raw_path.stat().st_size} bytes)",
        file=sys.stderr,
    )
    print(
        f"Markdown: {md_path} ({md_path.stat().st_size} bytes)",
        file=sys.stderr,
    )
    print("")
    print(result.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
