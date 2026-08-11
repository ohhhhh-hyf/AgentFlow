"""Runtime orchestration for selected task lines."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from llm_client.config import load_env

from .io import load_transcript, load_user, pick_single_file, resolve_path, resolve_sample_path
from .logging_config import setup_logging
from .outputs import (
    export_knowledge_graph,
    export_mindmap_html,
    export_mindmap_png,
    save_all_reports,
    task_output_dir,
)
from .runtime_context import DomainContext, env_path, normalize_tasks
from .template_router import maybe_compile_natural_template

logger = logging.getLogger(__name__)


# ── CLI 参数解析（bootstrap.py 入口用）─────────────────────────

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


async def run(
    ctx: DomainContext,
    file: Path,
    profile: Path,
    env_file: Path,
    templates: dict[str, Path] | None = None,
    tasks: list[str] | None = None,
) -> None:
    """Run selected task lines and persist their final artifacts."""
    setup_logging()
    load_env(resolve_path(ctx, env_file))

    transcript = load_transcript(ctx, file)
    user = load_user(ctx, profile)
    line_names = normalize_tasks(ctx, tasks or [], set(ctx.task_lines))

    template_texts: dict[str, str] = {}
    for line, path in (templates or {}).items():
        if line not in line_names:
            continue
        if path is None:
            continue
        template_file = _resolve_template_file(ctx, line, Path(path))
        if template_file is None:
            continue
        text = template_file.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"{line} 模板文件为空：{template_file}")
        template_texts[line] = await maybe_compile_natural_template(text)

    system = ctx.system_cls()
    any_output = False
    silent_graph_lines = {"mindmap", "knowledge_graph"}
    graph_silent = any(line in silent_graph_lines for line in line_names)

    async for event in system.run_streaming(
        transcript,
        user,
        templates=template_texts,
        lines=line_names,
    ):
        etype = event["type"]
        if etype == "chunk":
            if event.get("line") in silent_graph_lines:
                continue
            any_output = True
            sys.stdout.write(event["text"])
            sys.stdout.flush()
        elif etype == "done":
            await _handle_done(ctx, event)

    if any_output:
        sys.stdout.write("\n")
    elif not graph_silent:
        logger.info("（暂无内容）")


async def _handle_done(ctx: DomainContext, event: dict) -> None:
    if event.get("quality_warning"):
        logger.warning("⚠ %s", event["quality_warning"])
    reports = event.get("reports") or {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    saved_reports = save_all_reports(ctx, reports, timestamp)
    for line_name, paths in saved_reports.items():
        cn = ctx.line_cn_names.get(line_name, line_name)
        if paths.get("json"):
            sys.stdout.write(f"[{cn}] 已保存 JSON：{paths['json']}\n")
        if paths.get("text"):
            sys.stdout.write(f"[{cn}] 已保存文本：{paths['text']}\n")

    if "mindmap" in reports:
        mindmap_dir = task_output_dir(ctx, "mindmap")
        html_path = export_mindmap_html(reports, mindmap_dir)
        if html_path:
            sys.stdout.write(f"\n[思维导图] 已生成 HTML：{html_path}\n")
        png_path = await export_mindmap_png(reports, mindmap_dir, html_path=html_path)
        if png_path:
            sys.stdout.write(f"[思维导图] 已生成 PNG：{png_path}\n")

    if "knowledge_graph" in reports:
        kg_dir = task_output_dir(ctx, "knowledge_graph")
        kg_paths = export_knowledge_graph(reports, kg_dir)
        if kg_paths.get("png"):
            sys.stdout.write(f"[知识图谱] 已生成 PNG：{kg_paths['png']}\n")
        if kg_paths.get("svg"):
            sys.stdout.write(f"[知识图谱] 已生成 SVG：{kg_paths['svg']}\n")
        if kg_paths.get("html"):
            sys.stdout.write(f"[知识图谱] 已生成 HTML：{kg_paths['html']}\n")


def _resolve_template_file(
    ctx: DomainContext, line_name: str, path: Path
) -> Path | None:
    resolved = resolve_sample_path(ctx, path, f"{line_name}_template")
    if resolved.is_file():
        return resolved
    if resolved.is_dir():
        files = sorted(
            item for item in resolved.iterdir()
            if item.is_file() and item.suffix.lower() in {".md", ".txt"}
        )
        if not files:
            return None
        if len(files) > 1:
            names = "\n".join(f"- {file.name}" for file in files)
            raise ValueError(
                f"{line_name} 模板目录中发现多个模板文件，请直接指定其中一个：\n{names}"
            )
        return files[0]
    return pick_single_file(resolved.parent, resolved.name, f"{line_name} 模板")


__all__ = ["build_parser", "collect_templates", "parse_domain_name", "run"]
