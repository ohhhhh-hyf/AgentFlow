"""calendar 命令行入口。

默认输出：标准业务待办对象数组，每项包含 raw, deadline, time_slot, kind。
示例：
    python -m infra.calendar.cli \
      --meeting-time "2026-10-29 14:30:45" \
      --input -
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, List

from infra.llm.config import load_env

from .agent import run_deadline_agent
from .config import DEFAULT_TIMEZONE


def _text_from_mapping(item: dict) -> str:
    for key in ("deadline", "text", "raw", "ddl"):
        if key in item:
            value = item.get(key)
            return "" if value is None else str(value)
    for key in ("task", "title"):
        if key in item and item.get(key) is not None:
            return str(item.get(key))
    return ""


def normalize_input(data: Any) -> List[str]:
    """把多种输入 JSON 形态统一成待解析文本列表。"""
    if isinstance(data, str):
        return [data]
    if isinstance(data, list):
        out: List[str] = []
        for item in data:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                out.append(_text_from_mapping(item))
            else:
                out.append(str(item))
        return out
    if isinstance(data, dict):
        if "action_groups" in data and isinstance(data["action_groups"], list):
            out = []
            for group in data["action_groups"]:
                if not isinstance(group, dict):
                    continue
                for bucket in ("assigned", "unassigned"):
                    for item in group.get(bucket) or []:
                        if isinstance(item, dict):
                            out.append(_text_from_mapping(item))
            return out
        for key in ("items", "deadlines", "texts", "actions", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return normalize_input(value)
        return [_text_from_mapping(data)]
    raise ValueError(f"不支持的输入 JSON 类型：{type(data).__name__}")


def _load_input(path: str) -> Any:
    if path == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="把待办中的自然语言 deadline 转成绝对时间与时段标记"
    )
    parser.add_argument(
        "--meeting-time",
        required=True,
        help='会议开始时间，例如 "2026-10-29 14:30:45"',
    )
    parser.add_argument(
        "--input",
        required=True,
        help="输入 JSON 文件路径；传 - 表示从 stdin 读取",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help=f"IANA 时区，默认 {DEFAULT_TIMEZONE}",
    )
    parser.add_argument("--output", help="输出 JSON 文件路径；不填则打印到 stdout")
    parser.add_argument(
        "--dates-only",
        action="store_true",
        help="仅输出时间字符串数组（扁平模式，如 ['2026/10/30', ...]）",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="输出带 index/raw/kind/time_slot/warnings/error 的完整诊断对象",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="输出紧凑 JSON（默认缩进 2 空格）",
    )
    parser.add_argument(
        "--no-fast-path",
        action="store_true",
        help="禁用 Fast-Path 规则引擎，强制全量走 LLM 深度提取",
    )
    return parser


def _one_to_one(results: List[dict], count: int) -> List[Any]:
    """把详细结果压成与输入一一对应的 deadline 字符串数组。"""
    values: List[Any] = []
    for index in range(count):
        if index < len(results):
            values.append(results[index].get("deadline"))
        else:
            values.append(None)
    return values


def _to_clean_items(results: List[dict], count: int, texts: List[str]) -> List[dict]:
    """返回标准的对象数组，每项包含 raw, deadline, time_slot, kind。"""
    out: List[dict] = []
    for index in range(count):
        raw_t = texts[index] if index < len(texts) else ""
        if index < len(results):
            r = results[index]
            out.append({
                "raw": r.get("raw") or raw_t,
                "deadline": r.get("deadline"),
                "deadline_start": r.get("deadline_start"),
                "deadline_end": r.get("deadline_end"),
                "time_slot": r.get("time_slot"),
                "kind": r.get("kind", "none"),
            })
        else:
            out.append({
                "raw": raw_t,
                "deadline": None,
                "deadline_start": None,
                "deadline_end": None,
                "time_slot": None,
                "kind": "none",
            })
    return out


def _report_errors(results: List[dict]) -> None:
    for item in results:
        if item.get("error"):
            print(
                f"[calendar] index {item.get('index')}: {item['error']}",
                file=sys.stderr,
            )


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # 独立 CLI 运行：加载项目根目录 .env，供 infra.llm.LLMClient 使用。
    root = Path(__file__).resolve().parents[2]
    load_env(root / ".env")

    try:
        raw = _load_input(args.input)
        texts = normalize_input(raw)
    except Exception as exc:  # noqa: BLE001
        print(f"[calendar] 读取输入失败：{exc}", file=sys.stderr)
        return 2

    try:
        result = asyncio.run(
            run_deadline_agent(
                meeting_start_time=args.meeting_time,
                texts=texts,
                timezone=args.timezone,
                use_fast_path=not args.no_fast_path,
            )
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[calendar] 执行失败：{exc}", file=sys.stderr)
        return 1

    if result.get("error"):
        print(f"[calendar] {result['error']}", file=sys.stderr)
    _report_errors(result.get("results") or [])

    results_list = result.get("results") or []

    payload: Any
    if args.detailed:
        payload = result
    elif args.dates_only:
        payload = _one_to_one(results_list, len(texts))
    else:
        # 默认：标准业务结构 [{"raw": ..., "deadline": ..., "time_slot": ..., "kind": ...}]
        payload = _to_clean_items(results_list, len(texts), texts)

    if args.compact:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
