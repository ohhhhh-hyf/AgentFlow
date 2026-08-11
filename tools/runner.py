"""Runtime orchestration for selected task lines."""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from llm_client.config import load_env

from .archive import save_all_reports, task_output_dir
from .exporters import (
    export_knowledge_graph,
    export_mindmap_html,
    export_mindmap_png,
)
from .io import load_transcript, load_user, resolve_path
from .logging_config import setup_logging
from .runtime_context import DomainContext, normalize_tasks
from .template_router import maybe_compile_natural_template

logger = logging.getLogger(__name__)


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
        if path is None:
            continue
        text = resolve_path(ctx, Path(path)).read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"{line} 模板文件为空：{path}")
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


__all__ = ["run"]
