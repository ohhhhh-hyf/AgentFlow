"""Runtime orchestration for selected task lines."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from llm_client.config import load_env

from .io import (
    format_trace_extra,
    load_trace_sidecars,
    load_transcript,
    load_user,
    pick_single_file,
    resolve_path,
    resolve_sample_path,
)
from .logging_config import setup_logging
from .outputs import (
    export_knowledge_graph,
    export_mindmap_html,
    export_mindmap_png,
    save_all_reports,
    task_output_dir,
)
from .runtime_context import DomainContext, env_path, normalize_tasks
from tools.runtime.kinds import sidecar_lines
from .template_router import LINE_SCHEMA_HINTS, maybe_compile_natural_template

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
    _default_profile = env_path(ctx, "PROFILE", None)
    if _default_profile is None:
        _objective = ctx.cli_samples_dir / "profile" / "object_profile.json"
        _default_profile = (
            _objective if _objective.exists() else ctx.default_profile_dir
        )
    parser.add_argument(
        "--profile",
        dest="profile",
        type=Path,
        default=_default_profile,
        help="用户画像 JSON 文件或目录。"
        "默认 samples/{domain}/profile/object_profile.json（客观全员）；"
        "个人视角请指定 personal_profile.json。"
        "传目录时优先 object_profile.json",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=ctx.project_root / ".env",
        help="环境变量文件路径",
    )
    parser.add_argument(
        "--user_id",
        default=None,
        help="用户标识。提供后启用项目记忆：纪要对照历史，知识图谱增量合并",
    )
    parser.add_argument(
        "--project",
        dest="project_id",
        default=None,
        help="项目标识（可选）。会议域指定则强制写入该项目；"
        "笔记域若未传 --subject，可把本项当作学科名",
    )
    parser.add_argument(
        "--subject",
        default=None,
        help="学科名称（笔记记忆用）。同一 --user_id + --subject 共用一份知识图谱并增量合并",
    )
    for line in sorted(ctx.task_lines):
        cn = ctx.line_cn_names.get(line, line)
        policy = (ctx.line_policies or {}).get(line)
        if policy is None or policy.cli_template:
            parser.add_argument(
                f"--{line}_template",
                dest=f"{line}_template",
                type=Path,
                default=env_path(ctx, f"{line.upper()}_TEMPLATE", None),
                help=f"{cn}线渲染模板（.md 文件）。模板中用 [描述] 作为占位符，"
                "系统将自动填充内容。不指定则使用默认格式",
            )
        if policy is not None and policy.cli_mode:
            parser.add_argument(
                f"--{line}_mode",
                dest=f"{line}_mode",
                default=None,
                help=f"{cn}线组织模式（如 multi_styles 的 "
                "time/logic/causal/party/urgency；仅支持组织模式的线生效）",
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
        path = getattr(args, f"{line}_template", None)
        if path is not None:
            templates[line] = path
    return templates


def collect_modes(ctx: DomainContext, args: argparse.Namespace) -> dict[str, str]:
    """收集各线组织模式参数（--{线名}_mode，仅传了才生效）。"""
    modes: dict[str, str] = {}
    for line in ctx.task_lines:
        value = getattr(args, f"{line}_mode", None)
        if value:
            modes[line] = value.strip().lower()
    return modes


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
    modes: dict[str, str] | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    subject: str | None = None,
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
        template_texts[line] = await maybe_compile_natural_template(
            text,
            domain=ctx.name,
            line_name=line,
            schema_hint=LINE_SCHEMA_HINTS.get(line, ""),
        )

    system = ctx.system_cls()
    any_output = False
    silent_graph_lines = {"mindmap", "knowledge_graph"}
    graph_silent = any(line in silent_graph_lines for line in line_names)

    memory_bind = None
    line_extra: dict[str, str] = {}
    if user_id:
        from tools.memory import persist, prepare

        memory_bind, line_extra = prepare(
            ctx.project_root,
            ctx.name,
            user_id,
            transcript,
            line_names,
            project_id,
            subject,
        )
    for sidecar_line in sidecar_lines(line_names, ctx.line_policies):
        try:
            extra = format_trace_extra(load_trace_sidecars(ctx, file))
        except (OSError, ValueError):
            extra = ""
        if extra:
            prev = line_extra.get(sidecar_line) or ""
            line_extra[sidecar_line] = (
                f"{prev}\n\n{extra}".strip() if prev else extra
            )

    async for event in system.run_streaming(
        transcript,
        user,
        templates=template_texts,
        lines=line_names,
        line_modes=modes or {},
        line_extra=line_extra,
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
            if user_id and memory_bind is not None:
                persist(
                    ctx.project_root,
                    ctx.name,
                    user_id,
                    memory_bind,
                    event.get("reports") or {},
                    event.get("understanding") or {},
                    transcript,
                    subject,
                )

    if any_output:
        sys.stdout.write("\n")
    elif not graph_silent:
        logger.info("（暂无内容）")


async def _handle_done(ctx: DomainContext, event: dict) -> None:
    if event.get("quality_warning"):
        logger.warning("⚠ %s", event["quality_warning"])
    reports = event.get("reports") or {}
    # 毫秒级时间戳：同秒多次运行不互相覆盖产物
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]

    try:
        saved_reports = save_all_reports(
            ctx,
            reports,
            timestamp,
            gate_by_line=event.get("gate_by_line") or {},
        )
    except Exception:  # noqa: BLE001 - 落盘失败不中断其余导出
        logger.error("报告落盘失败", exc_info=True)
        saved_reports = {}
    for line_name, paths in saved_reports.items():
        cn = ctx.line_cn_names.get(line_name, line_name)
        if paths.get("html"):
            sys.stdout.write(f"[{cn}] 已保存 HTML：{paths['html']}\n")
        if paths.get("text"):
            sys.stdout.write(f"[{cn}] 已保存文本：{paths['text']}\n")
        if paths.get("rejected"):
            sys.stdout.write(
                f"[{cn}] 门禁未通过，已保存排查文本：{paths['rejected']}\n"
            )

    if "mindmap" in reports:
        try:
            mindmap_dir = task_output_dir(ctx, "mindmap")
            html_path = export_mindmap_html(reports, mindmap_dir)
            if html_path:
                sys.stdout.write(f"\n[思维导图] 已生成 HTML：{html_path}\n")
            png_path = await export_mindmap_png(
                reports, mindmap_dir, html_path=html_path
            )
            if png_path:
                sys.stdout.write(f"[思维导图] 已生成 PNG：{png_path}\n")
        except Exception:  # noqa: BLE001 - 单类导出失败不中断主流程
            logger.error("思维导图导出失败", exc_info=True)

    if "knowledge_graph" in reports:
        try:
            kg_dir = task_output_dir(ctx, "knowledge_graph")
            kg_paths = export_knowledge_graph(reports, kg_dir)
            if kg_paths.get("png"):
                sys.stdout.write(f"[知识图谱] 已生成 PNG：{kg_paths['png']}\n")
            if kg_paths.get("svg"):
                sys.stdout.write(f"[知识图谱] 已生成 SVG：{kg_paths['svg']}\n")
            if kg_paths.get("html"):
                sys.stdout.write(f"[知识图谱] 已生成 HTML：{kg_paths['html']}\n")
        except Exception:  # noqa: BLE001 - 单类导出失败不中断主流程
            logger.error("知识图谱导出失败", exc_info=True)


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


__all__ = ["build_parser", "collect_modes", "collect_templates", "parse_domain_name", "run"]
