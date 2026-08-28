"""任务执行核心：请求 → 输入组装 → run() → 产物保存 → 4 字段响应。

错误约定：校验失败抛 ApiError(status=400, message)；任务运行失败抛 500。
"""
from __future__ import annotations

import shutil
import tempfile
import time
import uuid
from pathlib import Path

from .config import PROJECT_ROOT, load_domain, load_env, profile_path, resolve_template_format
from .outputs import save_task_outputs
from .schemas import TaskRequest, TaskResponse

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
    """返回 (主文本, keypoints, notes)。transcript 与 teacher_focus 均并入主文本。"""
    texts = req.texts or {}
    transcript = "\n\n".join(
        part for part in (texts.get("transcript"), texts.get("teacher_focus")) if (part or "").strip()
    ).strip()
    keypoints = (texts.get("keypoints") or "").strip()
    notes = (texts.get("notes") or "").strip()
    return transcript, keypoints, notes


def _is_image_name(name: str) -> bool:
    return Path(name or "").suffix.lower() in IMAGE_EXTS


def _is_catalog_json_name(name: str) -> bool:
    return Path(name or "").suffix.lower() == ".json"


def _ocr_docs(user_id: str, docs: list[str]) -> str:
    """docs 中的图片 → OCR 文本（逐张，失败降级跳过）。"""
    parts: list[str] = []
    for name in docs or []:
        if not _is_image_name(name):
            continue
        path = _input_file(user_id, "docs", name)
        try:
            from tools.ocr import ocr_image_to_markdown

            body = ocr_image_to_markdown(str(path)).strip()
            if body:
                parts.append(body)
        except Exception as exc:  # noqa: BLE001 - OCR 失败不阻断主流程
            parts.append(f"（图片 {name} OCR 失败：{exc}）")
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
    """catalog 接口返回生成的目录文件名（如 catalog_20260827_221500_123.json）；其他接口返回空串。"""
    if line != "catalog" or not (subject or "").strip():
        return ""
    try:
        from domain.notes.tasks.catalog.store import latest_catalog_path

        path = latest_catalog_path(user_id=user_id, subject=subject)
        return path.name if path else ""
    except Exception:  # noqa: BLE001 - 取不到文件名不影响主流程
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


def _validate(req: TaskRequest, domain: str, task: str, user_id: str) -> str:
    """基础校验，返回代码线名；失败抛 ApiError。"""
    if (req.domain or "").strip() and (req.domain or "").strip() != domain:
        raise ApiError(400, f"请求体 domain={req.domain!r} 与路径不一致（应为 {domain}）")
    if (req.task or "").strip() and (req.task or "").strip() != task:
        raise ApiError(400, f"请求体 task={req.task!r} 与路径不一致（应为 {task}）")
    line = LINE_NAMES.get(task)
    if line is None:
        raise ApiError(404, f"任务线不存在：{task}")

    if not (user_id or "").strip():
        raise ApiError(400, f"{task} 需要 X-User-Id（用户标识：会议纪要关联记忆、知识库按用户隔离）")
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
    line = _validate(req, domain, task, user_id)
    extra = req.extra

    # 必填字段前置校验：一次性列出全部缺失项，秒回 400
    from .requirements import check_required

    missing = check_required(line, req, user_id)
    if missing:
        raise ApiError(400, f"{task} 缺少必填项：" + "、".join(missing))

    transcript, keypoints, notes = _collect_texts(req)
    catalog_files: list[str] = []
    try:
        if line != "library" and req.docs:
            if line == "checklist":
                # checklist 的 docs 是 catalog 文件名（.json，非笔记文本）：校验存在并记录
                for name in req.docs:
                    if not _is_catalog_json_name(name):
                        raise ApiError(400, f"checklist 的 docs 应为 catalog 文件名（.json）：{name}")
                    _catalog_input_file(user_id, extra.subject, name)
                    catalog_files.append(name.strip())
            else:
                ocr_text = _ocr_docs(user_id, req.docs)
                transcript = "\n\n".join(part for part in (transcript, ocr_text) if part)
                preview = _doc_previews(user_id, req.docs)
                transcript = "\n\n".join(part for part in (transcript, preview) if part)
    except ApiError:
        raise

    load_env()
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

    from tools.core.runner import run

    try:
        result = await run(
            ctx,
            input_files,
            profile_file,
            PROJECT_ROOT / ".env",
            templates,
            [line],
            modes,
            (user_id or "").strip() or None,
            (extra.project or "").strip() or None,
            (extra.subject or "").strip() or None,
            None, None, None, None, None, None,
            compile_natural=True,
            monitor=False,
            collect_reports=True,
            extra_line_inputs=extra_line_inputs,
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
    if saved_paths.get("md"):
        md_text = Path(saved_paths["md"]).read_text(encoding="utf-8")
    if not md_text and line in reports:
        from tools.exports.outputs import report_text

        md_text = report_text(reports[line])
    from .schemas import Monitor, ResponseData

    return TaskResponse(
        code=0,
        request_id=request_id,
        message="ok",
        monitor=Monitor(
            token_usage=int(usage.get("total_tokens", 0) or 0),
            cache_hit=int(usage.get("cache_hit_tokens", 0) or 0),
            cost_time=round((time.time() - _start_time), 1),
        ),
        data=ResponseData(
            text=md_text,
            file_name=_catalog_file_name(line, user_id, extra.subject),
        ),
    )


__all__ = ["ApiError", "LINE_NAMES", "run_task"]
