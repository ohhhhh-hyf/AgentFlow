"""Runtime orchestration for selected task lines."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from llm_client.config import load_env

from .io import (
    format_trace_extra,
    knowledge_text_preview,
    load_trace_sidecars,
    load_transcript,
    load_user,
    pick_single_file,
    resolve_knowledge_input,
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
from tools.memory.runtime import MEMORY_LINES
from tools.runtime.kinds import sidecar_lines
from .template_router import LINE_SCHEMA_HINTS, maybe_compile_natural_template

logger = logging.getLogger(__name__)


# ── CLI 参数解析（bootstrap.py 入口用）─────────────────────────

def _monitor_enabled(no_monitor: bool) -> bool:
    """任务监控开关：--no-monitor 优先，其次 TASK_MONITOR 环境变量，默认开启。

    TASK_MONITOR 取值：0/false/off/no/disable → 关闭；其它或未设置 → 开启。
    """
    if no_monitor:
        return False
    env = os.getenv("TASK_MONITOR", "").strip().lower()
    if env in {"0", "false", "off", "no", "disable", "disabled"}:
        return False
    return True


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
        dest="files",
        action="append",
        type=Path,
        default=None,
        help="输入文件或目录，可重复：--file a.pptx --file b.pdf。"
        "资料入库可一次传多份；其它任务沿用第一个文件。"
        "不传则用默认样例目录",
    )
    _default_profile = env_path(ctx, "PROFILE", None)
    if _default_profile is None:
        from tools.profiles import SHARED_PROFILE_DIR

        _objective = ctx.cli_samples_dir / "profile" / "object_profile.json"
        if not _objective.exists():
            # 客观画像已抽到跨域公共目录（perspective/profiles）
            _objective = SHARED_PROFILE_DIR / "object_profile.json"
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
        "--no-monitor",
        dest="no_monitor",
        action="store_true",
        default=False,
        help="关闭任务监控（token/耗时/按层细分落盘 output/monitor/）。"
        "默认开启；也可用环境变量 TASK_MONITOR=0 关闭",
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
        help="学科名称。资料入库/知识目录/复习清单：与 --user_id 一起决定知识库范围；"
        "笔记图谱记忆：同一 --user_id + --subject 增量合并图谱；"
        "自测题：只用来调难度，不写记忆",
    )
    parser.add_argument(
        "--chapter",
        default=None,
        help="章节名称（笔记自测题用，可选）",
    )
    parser.add_argument(
        "--level",
        default=None,
        help="已弃用。自测题水平固定为期中备考，传入值会被忽略。",
    )
    parser.add_argument(
        "--grade",
        default=None,
        help="已弃用。年级由笔记对齐到的知识点反推，传入值会被忽略。",
    )
    parser.add_argument(
        "--edition",
        default=None,
        help="已弃用。课本版本由笔记对齐到的知识点反推，传入值会被忽略。",
    )
    parser.add_argument(
        "--difficulty",
        default=None,
        help="题目难度：容易 / 较易 / 适中 / 较难 / 困难（笔记自测题搜题用，可选）",
    )
    parser.add_argument(
        "--qtype",
        default=None,
        help="题目类型：单选题 / 多选题 / 填空题 / 解答题 / 判断题（笔记自测题搜题用，可选）",
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


def collect_input_files(ctx: DomainContext, args: argparse.Namespace) -> list[Path]:
    """收集 --file（可多次）。未传则回退默认样例路径。"""
    items = [Path(item) for item in (getattr(args, "files", None) or []) if item]
    if items:
        return items
    fallback = env_path(ctx, "FILE", ctx.default_file_dir)
    return [Path(fallback)] if fallback else []


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


def _as_file_list(file: Path | list[Path] | tuple[Path, ...] | None) -> list[Path]:
    if file is None:
        return []
    if isinstance(file, (list, tuple)):
        return [Path(item) for item in file if item]
    return [Path(file)]


async def run(
    ctx: DomainContext,
    file: Path | list[Path],
    profile: Path,
    env_file: Path,
    templates: dict[str, Path] | None = None,
    tasks: list[str] | None = None,
    modes: dict[str, str] | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    subject: str | None = None,
    chapter: str | None = None,
    level: str | None = None,
    grade: str | None = None,
    edition: str | None = None,
    difficulty: str | None = None,
    qtype: str | None = None,
    compile_natural: bool = True,
    monitor: bool = True,
) -> dict | None:
    """Run selected task lines and persist their final artifacts.

    compile_natural：为 False 时不再把模板当自然语言二次编译。
    前端「确认模板并运行」必须关，否则用户改过的友好模板会被重新编译回首稿。
    monitor：是否启用任务监控（tools.monitor）。None 时按环境变量 TASK_MONITOR 决定。
    返回本次任务监控 payload（关闭监控或初始化失败则为 None）。
    """
    setup_logging()
    load_env(resolve_path(ctx, env_file))

    # 产物/监控按用户顶层隔离（output/{user_id}/...）
    ctx.user_id = user_id or ""

    user = load_user(ctx, profile)
    line_names = normalize_tasks(ctx, tasks or [], set(ctx.task_lines))
    file_list = _as_file_list(file)
    if "catalog" in line_names or "checklist" in line_names:
        if not (user_id or "").strip() or not (subject or "").strip():
            raise ValueError(
                "知识目录/复习清单需要 --user_id 和 --subject，用来定位知识库和已生成目录"
            )
    if not file_list:
        if "checklist" in line_names:
            raise ValueError("复习清单需要 --file 提供本次老师划重点文本")
        if "catalog" in line_names:
            file = None
        else:
            raise ValueError("请用 --file 指定输入文件")
    else:
        file = file_list[0]
    pending_extra: dict[str, str] = {}
    scope_bits: list[str] = []
    if (user_id or "").strip():
        scope_bits.append(f"【用户ID】{user_id.strip()}")
    if (subject or "").strip():
        scope_bits.append(f"【学科/课程】{subject.strip()}")
    scope_text = "\n".join(scope_bits)
    if "library" in line_names:
        sources = [resolve_knowledge_input(ctx, item) for item in file_list]
        lib_extra = "【入库文件】\n" + "\n".join(str(item) for item in sources)
        if scope_text:
            lib_extra += "\n" + scope_text
        pending_extra["library"] = lib_extra
        transcript = "\n\n".join(knowledge_text_preview(item) for item in sources)
        if not transcript.strip():
            transcript = "知识库资料入库"
    elif "catalog" in line_names:
        if len(file_list) > 1:
            raise ValueError("知识目录的 --file 只用于老师划重点文本，请只传一份")
        if file_list:
            transcript = load_transcript(ctx, file_list[0])
        else:
            transcript = "根据已入库资料生成知识目录"
    else:
        if len(file_list) > 1:
            raise ValueError(
                "该任务只接受一个 --file。多文件入库请使用 --task library"
            )
        transcript = load_transcript(ctx, file)

    system = ctx.system_cls()
    # ── 任务监控（tools.monitor；异常不影响主流程）──────────────
    # 开关：run(monitor=) 参数（CLI --no-monitor）优先，其次 TASK_MONITOR 环境变量
    _task_monitor = None
    if monitor and _monitor_enabled(no_monitor=False):
        try:
            from tools.monitor import TaskMonitor

            from tools.memory.store import safe_id

            monitor_dir = (
                ctx.project_root / "output" / safe_id(user_id or "")
                / "monitor"
                if (user_id or "").strip()
                else None
            )
            _task_monitor = TaskMonitor(
                getattr(system, "client", None),
                task_name="+".join(line_names),
                meta={
                    "domain": ctx.name,
                    "file": str(file) if file else "",
                    "profile": str(profile),
                    "user_id": (user_id or "").strip(),
                    "subject": (subject or "").strip(),
                },
                out_dir=monitor_dir,
            )
        except Exception:  # noqa: BLE001 - 监控组件异常不应阻断任务
            logger.warning("任务监控初始化失败，本次不监控", exc_info=True)
            _task_monitor = None
    if _task_monitor is not None:
        try:
            _task_monitor.start(transcript=transcript)
        except Exception:  # noqa: BLE001 - 监控失败不阻断任务
            logger.warning("任务监控 start 失败，本次不监控", exc_info=True)
            _task_monitor = None
    any_output = False
    silent_graph_lines = {"mindmap", "knowledge_graph"}
    graph_silent = any(line in silent_graph_lines for line in line_names)

    memory_bind = None
    line_extra: dict[str, str] = {}
    memory_enabled = bool(user_id and (set(line_names) & MEMORY_LINES))
    if "quiz" in line_names:
        quiz_rows: list[str] = ["用户水平：期中备考"]
        bank_rows: list[str] = []
        if (subject or "").strip():
            quiz_rows.append(f"学科/课程：{subject.strip()}")
        if (chapter or "").strip():
            quiz_rows.append(f"章节：{chapter.strip()}")
        if (difficulty or "").strip():
            bank_rows.append(f"题目难度：{difficulty.strip()}")
        if (qtype or "").strip():
            bank_rows.append(f"题目类型：{qtype.strip()}")
        parts: list[str] = []
        if quiz_rows:
            parts.append(
                "【出题上下文（只调难度与问法，不是另一份笔记）】\n"
                + "\n".join(quiz_rows)
            )
        if bank_rows:
            parts.append(
                "【题库检索（只用来搜真题，不要改成本卷题型）】\n"
                + "\n".join(bank_rows)
            )
        if parts:
            pending_extra["quiz"] = "\n\n".join(parts)
    if memory_enabled:
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
    if scope_text:
        for extra_line in ("catalog", "checklist"):
            if extra_line in line_names:
                pending_extra[extra_line] = scope_text
    for key, value in pending_extra.items():
        prev = line_extra.get(key) or ""
        line_extra[key] = f"{prev}\n\n{value}".strip() if prev else value
    for sidecar_line in sidecar_lines(line_names, ctx.line_policies):
        try:
            extra = format_trace_extra(load_trace_sidecars(ctx, file)) if file else ""
        except (OSError, ValueError):
            extra = ""
        if extra:
            prev = line_extra.get(sidecar_line) or ""
            line_extra[sidecar_line] = (
                f"{prev}\n\n{extra}".strip() if prev else extra
            )

    last_done = None
    run_error: BaseException | None = None
    monitor_payload = None
    try:
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
            if compile_natural:
                text = await maybe_compile_natural_template(
                    text,
                    domain=ctx.name,
                    line_name=line,
                    schema_hint=LINE_SCHEMA_HINTS.get(line, ""),
                    client=getattr(system, "client", None),
                )
            template_texts[line] = text
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
                last_done = event
                await _handle_done(ctx, event)
                if memory_enabled and memory_bind is not None:
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
    except Exception as exc:
        run_error = exc
        raise
    finally:
        if _task_monitor is not None:
            try:
                monitor_payload = _task_monitor.finish(
                    done_event=last_done,
                    extra={
                        "ok": run_error is None and last_done is not None,
                        "error": str(run_error) if run_error else "",
                    },
                )
            except Exception:  # noqa: BLE001 - 监控落盘失败不影响主流程
                logger.warning("任务监控落盘失败", exc_info=True)
        if run_error is not None and monitor_payload is not None:
            setattr(run_error, "monitor_payload", monitor_payload)

    if any_output:
        sys.stdout.write("\n")
    elif not graph_silent:
        logger.info("（暂无内容）")
    return monitor_payload


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
            if kg_paths.get("svg"):
                sys.stdout.write(f"[知识图谱] 已生成 SVG：{kg_paths['svg']}\n")
            if kg_paths.get("html"):
                sys.stdout.write(f"[知识图谱] 已生成 HTML：{kg_paths['html']}\n")
            if kg_paths.get("text"):
                sys.stdout.write(f"[知识图谱] 已生成学习地图：{kg_paths['text']}\n")
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


__all__ = [
    "build_parser",
    "collect_input_files",
    "collect_modes",
    "collect_templates",
    "parse_domain_name",
    "run",
]
