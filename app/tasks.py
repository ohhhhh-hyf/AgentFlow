"""任务执行核心：请求 → 输入组装 → run() → 产物保存 → 4 字段响应。

错误约定：校验失败抛 ApiError(status=400, message)；任务运行失败抛 500。
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi.responses import StreamingResponse

from .config import PROJECT_ROOT, load_domain, load_env, profile_path, resolve_template_format
from .outputs import output_dir, save_task_outputs
from .schemas import TaskRequest, TaskResponse

logger = logging.getLogger("agentflow")

# 内部任务名 → 实际代码线名（两者一致；文档内部任务标识为可读长名）
LINE_NAMES = {
    "minutes": "minutes",
    "actions": "actions",
    "risks": "risks",
    "minutes_styles": "minutes_styles",
    "minutes_trace": "minutes_trace",
    "graph": "graph",
    "library": "library",
    "catalog": "catalog",
    "checklist": "checklist",
}

STYLE_CHOICES = {"time", "logic", "causal", "party", "urgency"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


class ApiError(Exception):
    """API 业务错误：status 即业务码（HTTP 状态码）。"""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _input_file(user_id: str, kind: str, name: str) -> Path:
    """按目录规则解析输入文件。

    查找链（优先到兜底）：
    1. data/{user_id}/{kind}/{name}（X-User-Id 对应目录）
    2. data/{kind}/{name}（公共兜底）
    """
    raw = (name or "").strip()
    if not raw or "/" in raw or "\\" in raw or raw in {".", ".."}:
        raise ApiError(400, f"{kind} 文件名非法：{name!r}")
    data_root = (PROJECT_ROOT / "data").resolve()
    candidates: list[Path] = []
    if (user_id or "").strip():
        candidates.append(data_root / (user_id or "").strip() / kind / raw)
    candidates.append(data_root / kind / raw)
    for cand in candidates:
        resolved = cand.resolve()
        if resolved.is_file() and data_root in resolved.parents:
            return resolved
    raise ApiError(
        404,
        f"本地文件不存在：{kind}/{raw}"
        f"（请放入 data/{user_id or ''}/{kind}/ 或 data/{kind}/）",
    )


def _catalog_input_file(user_id: str, subject: str, name: str) -> Path:
    """checklist 的 docs：catalog 文件名 → data/{user_id}/knowledge/catalogs/{subject}/{name}。"""
    from domain.notes.tasks.catalog.store import _subject_filename

    raw = (name or "").strip()
    if not raw or "/" in raw or "\\" in raw or raw in {".", ".."}:
        raise ApiError(400, f"catalog 文件名非法：{name!r}")
    folder = (
        PROJECT_ROOT / "data" / (user_id or "").strip() / "knowledge" / "catalogs"
        / _subject_filename(subject)
    )
    candidate = (folder / raw).resolve()
    data_root = (PROJECT_ROOT / "data").resolve()
    if candidate.is_file() and data_root in candidate.parents:
        return candidate
    raise ApiError(
        404,
        f"catalog 文件不存在：{raw}"
        f"（请放入 data/{user_id or ''}/knowledge/catalogs/{_subject_filename(subject)}/）",
    )


def _collect_texts(req: TaskRequest) -> tuple[str, str, str]:
    """返回 (主文本, keypoints, notes)。老师重点不再从 texts 获取（经 docs 的 .txt 文件注入）。"""
    texts = req.texts or {}
    transcript = (texts.get("transcript") or "").strip()
    keypoints = (texts.get("keypoints") or "").strip()
    notes = (texts.get("notes") or "").strip()
    return transcript, keypoints, notes


def _is_image_name(name: str) -> bool:
    return Path(name or "").suffix.lower() in IMAGE_EXTS


def _is_catalog_json_name(name: str) -> bool:
    return Path(name or "").suffix.lower() == ".json"


def _is_teacher_txt_name(name: str) -> bool:
    """catalog / checklist 的 docs：.txt 文件视为老师重点文件。"""
    return Path(name or "").suffix.lower() == ".txt"


def _load_teacher_texts(user_id: str, names: list[str]) -> str:
    """读取老师重点 .txt 文件（data/{user_id}/docs/），拼成「老师重点」注入块。"""
    parts: list[str] = []
    for name in names:
        path = _input_file(user_id, "docs", name)
        try:
            body = path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            body = path.read_text(encoding="gbk", errors="replace").strip()
        if body:
            parts.append(body)
    if not parts:
        return ""
    return "【老师重点】\n" + "\n\n".join(parts)


def _ocr_docs(user_id: str, docs: list[str]) -> str:
    """docs 中的图片 → OCR 文本（逐张，失败降级跳过）。"""
    names = [name for name in (docs or []) if _is_image_name(name)]
    if not names:
        return ""
    from tools.ocr.engines import ocr_engine_label
    from tools.ocr.levels.light import ocr_log

    engine = ocr_engine_label()
    total = len(names)
    ocr_log(f"[OCR] 使用引擎 {engine}，共 {total} 张")
    parts: list[str] = []
    for index, name in enumerate(names, 1):
        path = _input_file(user_id, "docs", name)
        try:
            from tools.ocr import ocr_image_to_markdown

            body = ocr_image_to_markdown(str(path)).strip()
            if body:
                parts.append(body)
            ocr_log(f"[OCR/{engine}] {index}/{total} 完成 {name}")
        except Exception as exc:  # noqa: BLE001 - OCR 失败不阻断主流程
            parts.append(f"（图片 {name} OCR 失败：{exc}）")
            ocr_log(f"[OCR/{engine}] {index}/{total} 失败 {name}（{exc}）")
    return "\n\n".join(parts).strip()


def _doc_previews(user_id: str, docs: list[str]) -> str:
    """docs 中的文档（非图片、非 catalog json）→ 正文预览文本。"""
    parts: list[str] = []
    for name in docs or []:
        if _is_image_name(name) or _is_catalog_json_name(name):
            continue
        path = _input_file(user_id, "docs", name)
        try:
            from tools.core.io import knowledge_text_preview

            body = knowledge_text_preview(path).strip()
            if body:
                parts.append(body)
        except Exception as exc:  # noqa: BLE001 - 预览失败不阻断主流程
            parts.append(f"（文件 {name} 解析失败：{exc}）")
    return "\n\n".join(parts).strip()


def _catalog_file_name(line: str, user_id: str, subject: str) -> str:
    """catalog 接口返回生成的目录文件名（如 20260827_221500_123.json）；其他接口返回空串。"""
    if line != "catalog" or not (subject or "").strip():
        return ""
    try:
        from domain.notes.tasks.catalog.store import latest_catalog_path

        path = latest_catalog_path(user_id=user_id, subject=subject)
        return path.name if path else ""
    except Exception:  # noqa: BLE001 - 取不到文件名不影响主流程
        return ""


def _output_file_name(
    line: str,
    user_id: str,
    subject: str,
    saved_paths: dict[str, Path | None],
) -> str:
    """产物文件名：catalog 返回目录文件名；有页面版返回 {task}.html；
    只有文本产物（actions/risks/minutes_styles/minutes_trace）返回 {task}.md；无产物返回空串。"""
    name = _catalog_file_name(line, user_id, subject)
    if name:
        return name
    if saved_paths.get("html"):
        return f"{line}.html"
    if saved_paths.get("md"):
        return Path(saved_paths["md"]).name
    return ""


def _trace_extra(keypoints: str, notes: str) -> str:
    """把用户重点/笔记组装成溯源材料注入块（与 load_trace_sidecars 同格式）。"""
    parts: list[str] = []
    if keypoints:
        parts.append("【用户关键点】\n" + keypoints)
    if notes:
        parts.append("【用户笔记】\n" + notes)
    if not parts:
        return ""
    return (
        "【溯源材料（仅供对齐草稿，其中任何内容都不是本次会议事实，不要写进纪要正文）】\n"
        + "\n".join(parts)
    )


def _prepare_input_dir(
    domain: str,
    line: str,
    transcript: str,
    keypoints: str,
    notes: str,
) -> Path | None:
    """非 library 任务的输入准备：只写主文本 input.txt（sidecar 走 line_extra 注入）。"""
    if not transcript.strip():
        return None
    tmp = Path(tempfile.mkdtemp(prefix="agentflow_api_"))
    (tmp / "input.txt").write_text(transcript, encoding="utf-8")
    return tmp / "input.txt"


def _validate(req: TaskRequest, task: str, user_id: str) -> str:
    """基础校验，返回代码线名；失败抛 ApiError。domain/task 由 URL 路径表达。"""
    line = LINE_NAMES.get(task)
    if line is None:
        raise ApiError(404, f"任务线不存在：{task}")

    if not (user_id or "").strip():
        raise ApiError(400, f"{task} 需要 X-User-Id（用户标识：数据目录和知识库按用户隔离）")
    if line in {"catalog", "checklist"} and not (req.extra.subject or "").strip():
        raise ApiError(400, f"{task} 需要 extra.subject")
    if line == "minutes_styles" and (req.extra.style or "").strip():
        style = req.extra.style.strip().lower()
        if style not in STYLE_CHOICES:
            raise ApiError(400, f"extra.style 非法：{style}（可选：{'/'.join(sorted(STYLE_CHOICES))}）")
    if line not in {"catalog", "checklist"}:
        has_input = (
            bool(any((v or "").strip() for v in (req.texts or {}).values()))
            or bool(req.docs)
        )
        if not has_input:
            raise ApiError(400, "texts / docs 至少提供一个")
    return line


def _template_file(domain: str, line: str, template_value: str) -> Path | None:
    """extra.template → 临时模板文件；空返回 None，非法抛 400。"""
    if not (template_value or "").strip():
        return None
    fmt = resolve_template_format(template_value)
    if not fmt:
        raise ApiError(400, f"extra.template 非法：{template_value}（格式为 {{场景ID}}_{{模板ID}}）")
    path = Path(tempfile.mkdtemp(prefix="agentflow_tpl_")) / "template.md"
    path.write_text(fmt, encoding="utf-8")
    return path


def _profile_file(domain: str, profile_value: str) -> Path:
    path = profile_path(domain, profile_value)
    if not path or not path.is_file():
        raise ApiError(400, f"extra.profile 非法：{profile_value or '(空)'}（可选：空=客观全员 或 职业模板名）")
    return path


def _subject_pinyin(subject: str) -> str:
    """学科统一转拼音（物理 → wuli），与知识库 subject / catalog 目录一致；空值原样。"""
    from tools.knowledge.config import subject_to_pinyin

    return subject_to_pinyin(subject)


@dataclass
class _Prepared:
    """请求校验 + 输入组装结果（同步 / 流式接口共用）。"""

    line: str
    ctx: object
    profile_file: Path
    templates: dict[str, Path]
    modes: dict[str, str]
    extra_line_inputs: dict[str, str]
    input_files: list[Path] | Path | None
    user_id: str
    project: str
    subject: str
    memory: bool


def _prepare(domain: str, task: str, req: TaskRequest, user_id: str) -> _Prepared:
    """校验 + 输入组装（run_task / stream_task 共用；失败抛 ApiError）。"""
    load_env()  # 提前加载：docs 的 OCR 引擎分派依赖 OCR_ENGINE
    line = _validate(req, task, user_id)
    extra = req.extra

    # 必填字段前置校验：一次性列出全部缺失项，秒回 400
    from .requirements import check_required

    missing = check_required(line, req, user_id)
    if missing:
        raise ApiError(400, f"{task} 缺少必填项：" + "、".join(missing))

    transcript, keypoints, notes = _collect_texts(req)
    catalog_files: list[str] = []
    teacher_docs: list[str] = []
    material_docs: list[str] = []
    try:
        if line != "library" and req.docs:
            if line == "checklist":
                # checklist 的 docs：.json 为 catalog 目录文件，.txt 为老师重点文件，其余拒绝
                for name in req.docs:
                    if _is_catalog_json_name(name):
                        _catalog_input_file(user_id, extra.subject, name)
                        catalog_files.append(name.strip())
                    elif _is_teacher_txt_name(name):
                        teacher_docs.append(name.strip())
                    else:
                        raise ApiError(
                            400,
                            f"checklist 的 docs 应为 catalog 文件名（.json）或老师重点文件（.txt）：{name}",
                        )
            elif line == "catalog":
                # catalog 的 docs：.txt 为老师重点文件，其余按资料处理（OCR/解析并入主文本）
                for name in req.docs:
                    if _is_teacher_txt_name(name):
                        teacher_docs.append(name.strip())
                    else:
                        material_docs.append(name.strip())
            else:
                material_docs = [name.strip() for name in req.docs]
            if material_docs and line == "graph":
                # graph：图片走「OCR + LLM 整理审校」生成 md 后直接解析图谱（不经知识库入库）；
                # 非图片文档仍走正文预览
                image_docs = [n for n in material_docs if _is_image_name(n)]
                other_docs = [n for n in material_docs if not _is_image_name(n)]
                if image_docs:
                    from tools.ocr.levels.light import images_to_reviewed_markdown

                    image_paths = [_input_file(user_id, "docs", n) for n in image_docs]
                    md_text = images_to_reviewed_markdown(image_paths)
                    transcript = "\n\n".join(part for part in (transcript, md_text) if part)
                if other_docs:
                    preview = _doc_previews(user_id, other_docs)
                    transcript = "\n\n".join(part for part in (transcript, preview) if part)
            elif material_docs:
                ocr_text = _ocr_docs(user_id, material_docs)
                transcript = "\n\n".join(part for part in (transcript, ocr_text) if part)
                preview = _doc_previews(user_id, material_docs)
                transcript = "\n\n".join(part for part in (transcript, preview) if part)
    except ApiError:
        raise

    ctx = load_domain(domain)
    profile_file = _profile_file(domain, extra.profile)
    template_path = _template_file(domain, line, extra.template)

    # 输入文件：library 传原文件路径列表（docs 图片+文档全量入库）；其余传临时文件/目录
    input_files: list[Path] | Path | None
    if line == "library":
        input_files = [_input_file(user_id, "docs", name) for name in req.docs]
    elif line in {"catalog", "checklist"} and not transcript.strip():
        input_files = None
    else:
        input_files = _prepare_input_dir(domain, line, transcript, keypoints, notes)
        if input_files is None and line not in {"catalog", "checklist"}:
            raise ApiError(400, "texts / docs 未能产生有效输入")

    modes: dict[str, str] = {}
    if line == "minutes_styles" and (extra.style or "").strip():
        modes["minutes_styles"] = extra.style.strip().lower()
    templates: dict[str, Path] = {}
    if template_path is not None:
        templates[line] = template_path
    extra_line_inputs: dict[str, str] = {}
    if line == "minutes_trace":
        trace_text = _trace_extra(keypoints, notes)
        if trace_text:
            extra_line_inputs["minutes_trace"] = trace_text
    if line == "checklist" and catalog_files:
        extra_line_inputs["checklist"] = "【目录文件】" + catalog_files[0]
    if line in {"catalog", "checklist"} and teacher_docs:
        teacher_block = _load_teacher_texts(user_id, teacher_docs)
        if teacher_block:
            prev = extra_line_inputs.get(line) or ""
            extra_line_inputs[line] = f"{prev}\n\n{teacher_block}".strip()

    return _Prepared(
        line=line,
        ctx=ctx,
        profile_file=profile_file,
        templates=templates,
        modes=modes,
        extra_line_inputs=extra_line_inputs,
        input_files=input_files,
        user_id=(user_id or "").strip(),
        project=(extra.project or "").strip(),
        subject=_subject_pinyin(extra.subject),
        memory=bool(extra.memory),
    )


async def run_task(
    domain: str,
    task: str,
    req: TaskRequest,
    *,
    user_id: str = "",
    request_id: str = "",
) -> TaskResponse:
    """执行一次任务调用，返回通用响应（monitor + data）。"""
    _start_time = time.time()
    request_id = (request_id or "").strip() or uuid.uuid4().hex
    return await _run_task_impl(domain, task, req, user_id, request_id, _start_time)


async def _run_task_impl(
    domain: str,
    task: str,
    req: TaskRequest,
    user_id: str,
    request_id: str,
    _start_time: float,
) -> TaskResponse:
    p = await asyncio.to_thread(_prepare, domain, task, req, user_id)
    # 产物直接写入本次请求目录（data/{user_id}/output/{request_id}/），不再走根目录 output/ 归档
    p.ctx.output_dir = output_dir(user_id, request_id)

    from tools.core.runner import run

    try:
        result = await run(
            p.ctx,
            p.input_files,
            p.profile_file,
            PROJECT_ROOT / ".env",
            p.templates,
            [p.line],
            p.modes,
            p.user_id or None,
            p.project or None,
            p.subject or None,
            None, None, None, None, None, None,
            compile_natural=True,
            monitor=False,
            collect_reports=True,
            extra_line_inputs=p.extra_line_inputs,
            memory=p.memory,
        )
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001 - 运行失败统一转 500
        raise ApiError(500, f"任务运行失败：{exc}") from exc

    saved = (result or {}).get("saved") or {}
    saved_paths = save_task_outputs(user_id, request_id, saved)
    reports = (result or {}).get("reports") or {}
    usage = (result or {}).get("usage") or {}

    md_text = ""
    if p.line == "checklist" and p.line in reports:
        # checklist 以 HTML 交互页为主：data.text 返回精简摘要（统计 + 卡片列表），
        # 全量 Markdown 仍落盘 result.md 存档
        from domain.notes.tasks.checklist.display import build_checklist_summary

        _report = reports[p.line]
        _cards = (
            _report.get("cards")
            if isinstance(_report, dict)
            else getattr(_report, "cards", None)
        ) or []
        if _cards:
            if isinstance(_report, dict):
                _course = _report.get("course") or ""
                _version = _report.get("catalog_version") or ""
            else:
                _course = getattr(_report, "course", "") or ""
                _version = getattr(_report, "catalog_version", "") or ""
            md_text = build_checklist_summary(
                course=str(_course),
                catalog_version=str(_version),
                cards=_cards,
            )
    if not md_text and saved_paths.get("md"):
        md_text = Path(saved_paths["md"]).read_text(encoding="utf-8")
    if not md_text and p.line in reports:
        from tools.exports.outputs import report_text

        md_text = report_text(reports[p.line])
    from .schemas import Monitor, ResponseData

    return TaskResponse(
        code=0,
        request_id=request_id,
        message="success",
        monitor=Monitor(
            token_usage=int(usage.get("total_tokens", 0) or 0),
            cache_hit=int(usage.get("cache_hit_tokens", 0) or 0),
            cost_time=round((time.time() - _start_time), 1),
        ),
        data=ResponseData(
            text=md_text,
            file_name=_output_file_name(p.line, user_id, p.subject, saved_paths),
        ),
    )


def _ndjson(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False) + "\n"


async def stream_task(
    domain: str,
    task: str,
    req: TaskRequest,
    *,
    user_id: str = "",
    request_id: str = "",
) -> StreamingResponse:
    """流式任务执行：NDJSON 事件流（chunk / done / error），请求字段与同步接口一致。

    事件协议（每行一个 JSON）：
    - {"type": "chunk", "line": str, "title": str, "text": str}  渲染文本增量
    - {"type": "done", "code": 0, "request_id": str, "message": "success",
       "quality_warning": str|null, "monitor": {...}, "data": {...}}  最终结果（与同步响应同构）
    - {"type": "error", "code": 500, "message": str}  运行失败
    参数校验失败（400/404）仍直接返回 HTTP 错误，不走流。
    """
    request_id = (request_id or "").strip() or uuid.uuid4().hex
    return await _stream_task_impl(domain, task, req, user_id, request_id)


async def _stream_task_impl(
    domain: str,
    task: str,
    req: TaskRequest,
    user_id: str,
    request_id: str,
) -> StreamingResponse:
    p = await asyncio.to_thread(_prepare, domain, task, req, user_id)
    # 产物直接写入本次请求目录（data/{user_id}/output/{request_id}/），不再走根目录 output/ 归档
    p.ctx.output_dir = output_dir(user_id, request_id)

    async def event_stream():
        from tools.core.runner import _handle_done, prepare_run

        _start_time = time.time()
        try:
            prep = await prepare_run(
                p.ctx,
                p.input_files,
                p.profile_file,
                PROJECT_ROOT / ".env",
                p.templates,
                [p.line],
                p.modes,
                p.user_id or None,
                p.project or None,
                p.subject or None,
                None, None, None, None, None, None,
                compile_natural=True,
                monitor=False,
                collect_reports=True,
                extra_line_inputs=p.extra_line_inputs,
                memory=p.memory,
            )
        except Exception as exc:  # noqa: BLE001 - 准备失败推 error 事件
            yield _ndjson({"type": "error", "code": 500, "message": f"任务准备失败：{exc}"})
            return

        system = prep.system
        last_done = None
        try:
            async for event in system.run_streaming(
                prep.transcript,
                prep.user,
                templates=prep.template_texts,
                lines=prep.line_names,
                line_modes=p.modes,
                line_extra=prep.line_extra,
            ):
                if event["type"] == "phase":
                    yield _ndjson({"type": "phase", "node": event["node"]})
                elif event["type"] == "chunk":
                    yield _ndjson({
                        "type": "chunk",
                        "line": event["line"],
                        "title": event["title"],
                        "text": event["text"],
                    })
                elif event["type"] == "done":
                    last_done = event
                    saved = await _handle_done(prep.ctx, event) or {}
                    saved_paths = save_task_outputs(user_id, request_id, saved)
                    md_text = ""
                    if saved_paths.get("md"):
                        md_text = Path(saved_paths["md"]).read_text(encoding="utf-8")
                    if p.line == "checklist" and p.line in (event.get("reports") or {}):
                        from domain.notes.tasks.checklist.display import build_checklist_summary
                        from tools.exports.outputs import report_to_dict

                        _report = report_to_dict((event.get("reports") or {})[p.line])
                        _cards = _report.get("cards") or []
                        if _cards:
                            md_text = build_checklist_summary(
                                course=str(_report.get("course") or ""),
                                catalog_version=str(_report.get("catalog_version") or ""),
                                cards=_cards,
                            )
                    if not md_text and p.line in (event.get("reports") or {}):
                        from tools.exports.outputs import report_text, report_to_dict

                        md_text = report_text(
                            report_to_dict((event.get("reports") or {})[p.line])
                        )
                    if prep.memory_enabled and prep.memory_bind is not None:
                        from tools.memory import persist

                        persist(
                            prep.ctx.project_root,
                            prep.ctx.name,
                            user_id,
                            prep.memory_bind,
                            event.get("reports") or {},
                            event.get("understanding") or {},
                            prep.transcript,
                            prep.subject,
                        )
                    snap = system.client.monitor_snapshot().get("usage_totals") or {}
                    usage = {
                        key: int(snap.get(key, 0)) - int(prep.usage_before.get(key, 0))
                        for key in ("total_tokens", "cache_hit_tokens")
                    }
                    yield _ndjson({
                        "type": "done",
                        "code": 0,
                        "request_id": request_id,
                        "message": "success",
                        "quality_warning": event.get("quality_warning"),
                        "monitor": {
                            "token_usage": int(usage.get("total_tokens", 0) or 0),
                            "cache_hit": int(usage.get("cache_hit_tokens", 0) or 0),
                            "cost_time": round((time.time() - _start_time), 1),
                        },
                        "data": {
                            "text": md_text,
                            "file_name": _output_file_name(p.line, user_id, p.subject, saved_paths),
                        },
                    })
        except Exception as exc:  # noqa: BLE001 - 运行失败推 error 事件
            yield _ndjson({"type": "error", "code": 500, "message": f"任务运行失败：{exc}"})
        finally:
            if prep.task_monitor is not None:
                try:
                    prep.task_monitor.finish(
                        done_event=last_done,
                        extra={"ok": last_done is not None, "error": ""},
                    )
                except Exception:  # noqa: BLE001 - 监控落盘失败不影响主流程
                    pass

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


__all__ = ["ApiError", "LINE_NAMES", "run_task", "stream_task"]
