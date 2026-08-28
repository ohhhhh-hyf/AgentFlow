"""Runtime orchestration for selected task lines.

- ``prepare_run``：输入组装 + 注入 + 模板编译（run 与 API 流式接口共用）
- ``run``：准备 + 消费流式事件 + 产物落盘（同步聚合入口）
- ``_handle_done``：done 事件落盘 + 图类导出
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from client.config import load_env

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
from tools.outputs import (
    export_graph,
    export_mindmap_html,
    export_mindmap_png,
    report_to_dict,
    save_all_reports,
    task_output_dir,
)
from .runtime_context import DomainContext, normalize_tasks
from tools.memory.runtime import MEMORY_LINES
from tools.runtime.kinds import sidecar_lines
from tools.template_router import LINE_SCHEMA_HINTS, maybe_compile_natural_template

logger = logging.getLogger(__name__)


def _monitor_enabled(no_monitor: bool) -> bool:
    """任务监控开关：run(monitor=) 参数优先，其次 TASK_MONITOR 环境变量，默认开启。"""
    if no_monitor:
        return False
    env = os.getenv("TASK_MONITOR", "").strip().lower()
    if env in {"0", "false", "off", "no", "disable", "disabled"}:
        return False
    return True


def _client_usage(system) -> dict:
    """读取 LLM client 的 usage 快照；不可用时返回空。"""
    try:
        snapshot = system.client.monitor_snapshot()
        return dict(snapshot.get("usage_totals") or {})
    except Exception:  # noqa: BLE001 - 监控统计失败不影响任务
        return {}


_USAGE_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "calls",
    "cache_hit_tokens",
)


def _usage_diff(before: dict, after: dict) -> dict:
    """基线差值：本次任务实际消耗（供 API 的 token_usage / cache_hit_tokens 字段）。"""
    return {
        key: int(after.get(key, 0)) - int(before.get(key, 0))
        for key in _USAGE_KEYS
    }


def _as_file_list(file: Path | list[Path] | tuple[Path, ...] | None) -> list[Path]:
    if not file:
        return []
    if isinstance(file, (list, tuple)):
        return [Path(item) for item in file if item]
    return [Path(file)]


@dataclass
class PreparedRun:
    """run() 的共享准备结果：输入组装 + 注入 + 模板编译（同步/流式共用）。"""

    ctx: DomainContext
    system: object
    user: object
    transcript: str
    line_names: list[str]
    template_texts: dict[str, str]
    line_extra: dict[str, str]
    memory_bind: object | None
    memory_enabled: bool
    graph_silent: bool
    usage_before: dict
    task_monitor: object | None
    subject: str | None


async def prepare_run(
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
    *,
    compile_natural: bool = True,
    monitor: bool = True,
    collect_reports: bool = False,
    extra_line_inputs: dict[str, str] | None = None,
) -> PreparedRun:
    """输入组装 + 注入 + 模板编译（run 与流式接口共用；本函数不执行任务）。"""
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
    if "library" in line_names and not (user_id or "").strip():
        raise ValueError(
            "资料入库需要 --user_id：入库资料按用户隔离，"
            "不传会进无主统一库、之后按用户检索不到"
        )
    if not file_list:
        if "catalog" in line_names or "checklist" in line_names:
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
    elif "checklist" in line_names:
        if len(file_list) > 1:
            raise ValueError("复习清单的 --file 只用于老师划重点文本，请只传一份")
        if file_list:
            transcript = load_transcript(ctx, file_list[0])
        else:
            transcript = "根据已有知识目录和知识库生成复习清单"
    else:
        if len(file_list) > 1:
            raise ValueError(
                "该任务只接受一个 --file。多文件入库请使用 --task library"
            )
        transcript = load_transcript(ctx, file)

    system = ctx.system_cls()
    usage_before = _client_usage(system) if collect_reports else {}
    # ── 任务监控（tools.monitor；异常不影响主流程）──────────────
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
    graph_silent = any(line in {"mindmap", "graph"} for line in line_names)

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
    for line_name, value in (extra_line_inputs or {}).items():
        if line_name not in line_names or not (value or "").strip():
            continue
        prev = line_extra.get(line_name) or ""
        line_extra[line_name] = (
            f"{prev}\n\n{value}".strip() if prev else value
        )

    # 模板编译（异步；异常向上抛，由调用方决定降级）
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

    return PreparedRun(
        ctx=ctx,
        system=system,
        user=user,
        transcript=transcript,
        line_names=line_names,
        template_texts=template_texts,
        line_extra=line_extra,
        memory_bind=memory_bind,
        memory_enabled=memory_enabled,
        graph_silent=graph_silent,
        usage_before=usage_before,
        task_monitor=_task_monitor,
        subject=subject,
    )


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
    collect_reports: bool = False,
    extra_line_inputs: dict[str, str] | None = None,
) -> dict | None:
    """Run selected task lines and persist their final artifacts.

    compile_natural：为 False 时不再把模板当自然语言二次编译。
    monitor：是否启用任务监控（tools.monitor）。None 时按环境变量 TASK_MONITOR 决定。
    collect_reports：为 True 时返回结构化结果（供 API 层使用），
    返回 {"monitor", "reports", "understanding", "quality_warning", "saved", "usage"}：
      reports = {线名: 报告 dict}；saved = {线名: {text/html/... 产物路径}}；
      usage = {total_tokens, cache_hit_tokens, ...}（基线差值）；
    为 False 时保持旧行为，只返回任务监控 payload（或无）。
    extra_line_inputs：{线名: 注入文本}，直接注入该线的 line_extra（供 API 层传
    溯源材料等文本，避免落临时 sidecar 文件）。
    """
    prep = await prepare_run(
        ctx, file, profile, env_file, templates, tasks, modes, user_id,
        project_id, subject, chapter, level, grade, edition, difficulty, qtype,
        compile_natural=compile_natural, monitor=monitor,
        collect_reports=collect_reports, extra_line_inputs=extra_line_inputs,
    )
    system = prep.system
    ctx = prep.ctx
    line_names = prep.line_names
    transcript = prep.transcript
    user = prep.user
    template_texts = prep.template_texts
    line_extra = prep.line_extra
    memory_enabled = prep.memory_enabled
    memory_bind = prep.memory_bind
    graph_silent = prep.graph_silent
    usage_before = prep.usage_before
    _task_monitor = prep.task_monitor
    subject = prep.subject

    last_done = None
    run_error: BaseException | None = None
    monitor_payload = None
    collected: dict[str, object] = {
        "reports": {},
        "understanding": {},
        "quality_warning": None,
        "saved": {},
    }
    any_output = False
    try:
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
                if event.get("line") in {"mindmap", "graph"}:
                    continue
                any_output = True
                sys.stdout.write(event["text"])
                sys.stdout.flush()
            elif etype == "done":
                last_done = event
                if collect_reports:
                    collected["reports"] = {
                        line: report_to_dict(report)
                        for line, report in (event.get("reports") or {}).items()
                    }
                    collected["understanding"] = event.get("understanding") or {}
                    collected["quality_warning"] = event.get("quality_warning")
                    collected["saved"] = await _handle_done(ctx, event) or {}
                else:
                    await _handle_done(ctx, event)
                if memory_enabled and memory_bind is not None:
                    from tools.memory import persist

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
    if collect_reports:
        return {
            "monitor": monitor_payload,
            "reports": collected["reports"],
            "understanding": collected["understanding"],
            "quality_warning": collected["quality_warning"],
            "saved": collected["saved"],
            "usage": _usage_diff(usage_before, _client_usage(system)),
        }
    return monitor_payload


async def _handle_done(ctx: DomainContext, event: dict) -> dict | None:
    """处理 done 事件：落盘 + 图类导出；返回各产物路径（供 API 层收集）。"""
    if event.get("quality_warning"):
        logger.warning("⚠ %s", event["quality_warning"])
    reports = event.get("reports") or {}
    # 毫秒级时间戳：同秒多次运行不互相覆盖产物
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    saved: dict[str, dict[str, Path]] = {}

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
    saved.update(saved_reports)
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
            saved["mindmap"] = {
                "html": html_path,
                "png": png_path,
            }
        except Exception:  # noqa: BLE001 - 单类导出失败不中断主流程
            logger.error("思维导图导出失败", exc_info=True)

    if "graph" in reports:
        try:
            kg_dir = task_output_dir(ctx, "graph")
            kg_paths = export_graph(reports, kg_dir)
            if kg_paths.get("html"):
                sys.stdout.write(f"[知识图谱] 已生成 HTML：{kg_paths['html']}\n")
            if kg_paths.get("text"):
                sys.stdout.write(f"[知识图谱] 已生成学习地图：{kg_paths['text']}\n")
            saved["graph"] = kg_paths
        except Exception:  # noqa: BLE001 - 单类导出失败不中断主流程
            logger.error("知识图谱导出失败", exc_info=True)

    return saved


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


__all__ = ["PreparedRun", "prepare_run", "run"]
