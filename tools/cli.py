"""CLI argument parsing for bootstrap.py."""
from __future__ import annotations

import argparse
from pathlib import Path

from .runtime_context import DomainContext, env_path


def build_parser(ctx: DomainContext) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"运行 {ctx.name} 域任务线（可用 --task 指定生成哪条线）",
    )
    parser.add_argument(
        "--domain",
        default=ctx.name,
        help=f"领域名（默认 {ctx.name}）",
    )
    parser.add_argument(
        "--file",
        dest="file",
        type=Path,
        default=env_path(ctx, "FILE", ctx.default_file_dir),
        help="输入文本文件或目录。传目录时，目录中需要包含一个 .txt 文件",
    )
    parser.add_argument(
        "--profile",
        dest="profile",
        type=Path,
        default=env_path(ctx, "PROFILE", ctx.default_profile_dir),
        help="用户画像 JSON 文件或目录。传目录时，目录中需要包含一个 .json 文件",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=ctx.project_root / ".env",
        help="环境变量文件路径",
    )
    for line in sorted(ctx.task_lines):
        cn = ctx.line_cn_names.get(line, line)
        parser.add_argument(
            f"--{line}_template",
            dest=f"{line}_template",
            type=Path,
            default=env_path(ctx, f"{line.upper()}_TEMPLATE", None),
            help=f"{cn}线渲染模板（.md 文件）。模板中用 [描述] 作为占位符，"
            "系统将自动填充内容。不指定则使用默认格式",
        )
    parser.add_argument(
        "--task",
        dest="tasks",
        action="append",
        required=True,
        metavar="任务",
        help="要生成的任务，可多次指定。"
        f"可用：{' / '.join(sorted(ctx.task_lines))}，也支持友好名 "
        f"{' / '.join(sorted(ctx.task_aliases))}",
    )
    return parser


def collect_templates(ctx: DomainContext, args: argparse.Namespace) -> dict[str, Path]:
    templates: dict[str, Path] = {}
    for line in ctx.task_lines:
        path = getattr(args, f"{line}_template")
        if path is not None:
            templates[line] = path
    return templates


def parse_domain_name(default: str = "meeting") -> str:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--domain", default=default)
    pre_args, _ = pre.parse_known_args()
    return pre_args.domain


__all__ = ["build_parser", "collect_templates", "parse_domain_name"]
