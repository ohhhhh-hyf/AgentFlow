"""任务执行核心：请求 → 输入组装 → run() → 产物保存 → 4 字段响应。

错误约定：校验失败抛 ApiError(status=400, message)；任务运行失败抛 500。
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from fastapi.responses import StreamingResponse

from infra.storage.document_processor import IMAGE_EXTS

from .config import (
    DEFAULT_CONSENSUS_DECISION_TEMPLATE,
    DEFAULT_MINUTES_TEMPLATE,
    DEFAULT_PERSONAL_MINUTES_TEMPLATE,
    PROJECT_ROOT,
    load_domain,
    load_env,
    profile_path,
    resolve_agenda_template_format,
    resolve_template_format,
    style_template_path,
    template_key,
    template_registry,
)
from core.runner.profiles import (
    is_user_profile_file,
    resolve_profile_mode,
    sanitize_user_profile,
)
from domains.meeting.domain_config import minutes_template_auto_mode

from .id_worker import next_request_id
from .outputs import output_dir, save_task_outputs
from .schemas import TaskRequest, TaskResponse, ndjson_line as _ndjson
from .tasklines import all_lines

logger = logging.getLogger("app.tasks")

# task 取值 → 代码线名。清单声明在 app/tasklines.py，
# 路由注册与异步接口校验都从同一份声明派生，避免多处清单不同步。
LINE_NAMES = all_lines()

# 多样式纪要严格限定的 5 大黄金模式
STYLE_CHOICES = {"brief", "topic", "review", "retro", "alignment"}
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


def _catalog_quality_monitor(line: str, user_id: str, subject: str) -> dict:
    """catalog 跑完后的"目录体检"（覆盖 / 同级顺序 / 内容可核）→ 响应 monitor.catalog。

    读**刚存下的**目录 json + 原文骨架算指标（零 LLM），让你一眼验收而不是读整棵树；
    任何异常都只丢指标、不影响目录结果本身。
    """
    if line != "catalog":
        return {}
    try:
        from domains.notes.tasks.catalog.skeleton import (
            build_source_skeleton,
            catalog_quality_report,
        )
        from domains.notes.tasks.catalog.store import load_catalog

        draft = load_catalog(user_id=user_id, subject=subject)
        if not draft:
            return {}
        # 作用域标签只在真有值时写：空值写成「【用户ID】」会让下游解析出空串，
        # 进而落到无主知识库目录（data/knowledge）。
        scope = ""
        if str(user_id or "").strip():
            scope += f"【用户ID】{str(user_id).strip()}\n"
        if str(subject or "").strip():
            scope += f"【学科/课程】{str(subject).strip()}\n"
        skeleton = build_source_skeleton(scope)
        if not skeleton.get("topics"):
            return {}
        metrics = catalog_quality_report(skeleton, draft)["metrics"]
        metrics["skeleton_kind"] = str(skeleton.get("kind") or "md")
        metrics["fake_heading_chunks"] = _fake_heading_chunk_count(user_id, subject)
        return {"catalog": metrics}
    except Exception:  # noqa: BLE001 - 体检失败不影响任务结果
        logger.warning("catalog quality monitor failed", exc_info=True)
        return {}


def _fake_heading_chunk_count(user_id: str, subject: str) -> int:
    """入库自检：知识库里有多少块的 heading 是"句子型伪标题"（正文被误判成标题）。

    只看形态（长度 > 24 或含逗号/句号），不看内容——它是入库标题识别的回归哨兵：
    `③ …` 经 NFKC 变 `3 …` 后曾被当成章级标题，顺着候选池长成目录里的假章节。
    """
    try:
        from domains.notes.tasks.catalog.gather import open_knowledge

        kb = open_knowledge(user_id=user_id)
        if kb is None:
            return 0
        chunks = kb.list_chunks(user_id=user_id, subject=subject, with_text=False) or []
    except Exception:  # noqa: BLE001 - 统计失败不影响结果
        return 0
    fake = 0
    for chunk in chunks:
        heading = str((chunk.get("metadata") or {}).get("heading") or "")
        if heading and (len(heading) > 24 or any(ch in heading for ch in "，。；,;")):
            fake += 1
    return fake


def _catalog_input_file(user_id: str, subject: str, name: str) -> Path:
    """checklist 的 extra.catalog：catalog 文件名 → data/{user_id}/knowledge/catalogs/{subject}/{name}。"""
    from domains.notes.tasks.catalog.store import _subject_filename

    uid = (user_id or "").strip()
    if not uid:
        raise ApiError(400, "checklist 需要 X-User-Id（知识目录按用户隔离）")
    raw = (name or "").strip()
    if not raw or "/" in raw or "\\" in raw or raw in {".", ".."}:
        raise ApiError(400, f"catalog 文件名非法：{name!r}")
    folder = (
        PROJECT_ROOT / "data" / uid / "knowledge" / "catalogs"
        / _subject_filename(subject)
    )
    candidate = (folder / raw).resolve()
    data_root = (PROJECT_ROOT / "data").resolve()
    if candidate.is_file() and data_root in candidate.parents:
        return candidate
    raise ApiError(
        404,
        f"catalog 文件不存在：{raw}"
        f"（请放入 data/{uid}/knowledge/catalogs/{_subject_filename(subject)}/）",
    )


def _collect_texts(req: TaskRequest) -> tuple[str, str, str, str, str]:
    """返回 (transcript, keypoints, notes, vision_info, actions_text)。"""
    texts = req.texts or {}
    transcript = (texts.get("transcript") or "").strip()
    keypoints = (texts.get("keypoints") or "").strip()
    notes = (texts.get("notes") or "").strip()
    vision_info = (texts.get("vision_info") or "").strip()
    actions_text = (texts.get("actions_text") or "").strip()
    return transcript, keypoints, notes, vision_info, actions_text


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
    """docs 中的图片 → OCR 文本（两阶段并发：先识别、跨页去噪，再逐张重构）。

    阶段划分的原因：

    1. **并发识别**（``ocr_image_lines``，多路取 ``ocr_concurrency()``）—— 引擎侧本来就是
       线程绑定的实例池，逐张串行会闲置大部分 worker；这一步不调模型。
       版面推断之后该函数还会做**逐图自适应**的页眉页脚剔除（按本图中位行高与边缘带判定，
       校名/地址/印刷编号标 boilerplate），逐张处理也能生效。
    2. **跨页去噪**（``concat_page_lines(require_edge=True)``）—— 只有拿到"多页放在一起"的
       视角才能判页眉页脚（同一短行 ≥2 页且落在页面上下边缘带 → 标 boilerplate）。
       逐张处理时这条判据无从生效，校名/页眉就会混进正文，进而污染所有下游任务与知识目录；
       它与第 1 步的逐图判据互为补位（一个管"每页位置/字号不同"，一个管"跨页文本重复"）。
    3. **并发重构**（``reconstruct_markdown``，每张一次 LLM）—— 它会自动跳过
       ``role_hint="boilerplate"`` 的行（拼接与送模型两处都过滤）。

    结果按传入顺序拼接（``pool.map`` 按入参顺序产出，与完成顺序无关）；单张失败降级跳过。
    """
    names = [name for name in (docs or []) if _is_image_name(name)]
    if not names:
        return ""
    from infra.ocr.engines import ocr_concurrency, ocr_engine_label
    from infra.ocr.levels.light import concat_page_lines, ocr_log

    engine = ocr_engine_label()
    total = len(names)
    workers = max(1, min(ocr_concurrency(), total))
    ocr_log(f"ocr start engine={engine} images={total} workers={workers}")

    def _lines_one(indexed: tuple[int, str]) -> tuple[int, list | None, str]:
        index, name = indexed
        # 文件不存在时与原实现一致：ApiError 往上抛（任务以 404 结束）
        path = _input_file(user_id, "docs", name)
        try:
            from infra.ocr.layout import ocr_image_lines

            lines = ocr_image_lines(str(path)) or []
            ocr_log(f"ocr item ok {index}/{total} lines={len(lines)} file={name}")
            return index, lines, ""
        except Exception as exc:  # noqa: BLE001 - 单张失败不阻断其余图片
            ocr_log(f"ocr item fail {index}/{total} file={name} err={exc}")
            return index, None, str(exc)

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ocr-doc") as pool:
        rows = list(pool.map(_lines_one, enumerate(names, 1)))

    # 跨页去噪：需要多页视图（_page 从 0 开始编号，对应 names 的下标）
    pages = [{"lines": lines or []} for _index, lines, _err in rows]
    combined = concat_page_lines(pages, require_edge=True)
    by_page: dict[str, list] = {}
    for line in combined:
        by_page.setdefault(str(line.get("_page") or ""), []).append(line)
    boiler = sum(
        1 for line in combined if str(line.get("role_hint") or "") == "boilerplate"
    )
    if boiler:
        ocr_log(f"ocr drop boilerplate lines={boiler}")

    errors = {index: err for index, _lines, err in rows if err}

    def _md_one(indexed: tuple[int, str]) -> tuple[int, str]:
        index, name = indexed
        if index in errors:
            return index, f"（图片 {name} OCR 失败：{errors[index]}）"
        lines = by_page.get(str(index - 1), [])
        try:
            from infra.ocr.reconstruct import reconstruct_markdown

            return index, reconstruct_markdown(lines).strip()
        except Exception as exc:  # noqa: BLE001 - 单张重构失败不阻断其余图片
            ocr_log(f"ocr item fail {index}/{total} file={name} err={exc}")
            return index, f"（图片 {name} OCR 失败：{exc}）"

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ocr-llm") as pool:
        parts = [body for _index, body in pool.map(_md_one, enumerate(names, 1))]
    ocr_log(f"ocr join images={total} order=input first={names[0]} last={names[-1]}")
    return "\n\n".join(part for part in parts if part).strip()


def _pad_image_bottom(image_path: str, pad_px: int = 100) -> str | None:
    """在图片底部添加白色填充（委托 domains.meeting.agenda_vision.pad_image_bottom 实现）。"""
    from domains.meeting.agenda_vision import pad_image_bottom

    return pad_image_bottom(image_path, pad_px=pad_px)


def _ocr_single_agenda_doc(
    user_id: str,
    docs: list[str],
    candidate_speakers: list[str] | set[str] | None = None,
    transcript: str = "",
) -> str:
    """提取 docs 中的议程图片（统一委托 domains.meeting.agenda_vision.extract_agenda_from_image_docs 调度）。"""
    names = [name for name in (docs or []) if _is_image_name(name)]
    if not names:
        return ""
    from domains.meeting.agenda_vision import extract_agenda_from_image_docs

    image_paths = [_input_file(user_id, "docs", name) for name in names]
    _, md_text = extract_agenda_from_image_docs(
        user_id=user_id,
        image_docs=names,
        transcript=transcript,
        candidate_speakers=candidate_speakers,
        image_paths=image_paths,
    )
    return md_text



def _doc_previews(user_id: str, docs: list[str]) -> str:
    """docs 中的文档（非图片、非 catalog json）→ 正文预览文本。"""
    parts: list[str] = []
    for name in docs or []:
        if _is_image_name(name) or _is_catalog_json_name(name):
            continue
        path = _input_file(user_id, "docs", name)
        try:
            from core.runner.io import knowledge_text_preview

            body = knowledge_text_preview(path).strip()
            if body:
                parts.append(body)
        except Exception as exc:  # noqa: BLE001 - 预览失败不阻断主流程
            parts.append(f"（文件 {name} 解析失败：{exc}）")
    return "\n\n".join(parts).strip()


def _output_file_name(
    line: str,
    user_id: str,
    subject: str,
    saved_paths: dict[str, Path | None],
) -> str:
    """产物文件名：有页面版返回 {task}.html；
    只有文本产物（actions/risks/minutes_styles/minutes_trace）返回 {task}.md；无产物返回空串。"""
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


def _parse_notes_items(notes_text: str) -> list[dict[str, str]]:
    """切分用户笔记。支持 '原话 -> 批注'，清洗前后空格；无箭头整行作为备注。"""
    items = []
    arrow_pattern = re.compile(r"\s*->\s*")
    for line in (notes_text or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        if "->" in raw:
            parts = arrow_pattern.split(raw, maxsplit=1)
            items.append({"quote": parts[0].strip(), "comment": parts[1].strip()})
        else:
            items.append({"quote": "", "comment": raw})
    return items


def _pack_minutes_auxiliary(keypoints: str, notes: str, vision_info: str) -> str:
    """将非空的辅助材料组装为统一的上下文注入块。"""
    blocks = []
    if keypoints.strip():
        blocks.append(f"【用户核心关键点】\n{keypoints.strip()}")
    if notes.strip():
        parsed_notes = _parse_notes_items(notes)
        note_lines = []
        for item in parsed_notes:
            if item["quote"]:
                note_lines.append(f"- 原话：\"{item['quote']}\" | 备注：{item['comment']}")
            else:
                note_lines.append(f"- 笔记：{item['comment']}")
        if note_lines:
            blocks.append("【用户划线原话与笔记】\n" + "\n".join(note_lines))
    if vision_info.strip():
        blocks.append(f"【视觉信息参考(OCR)】\n{vision_info.strip()}")
    return "\n\n".join(blocks).strip()


def _pack_actions_auxiliary(
    actions_text: str,
    keypoints: str,
    notes: str,
    vision_info: str,
) -> str:
    """组装 actions 线专用辅助材料；actions_text 不进入 minutes auxiliary。"""
    blocks = []
    if actions_text.strip():
        blocks.append(f"【用户标记待办原文】\n{actions_text.strip()}")
    minutes_aux = _pack_minutes_auxiliary(keypoints, notes, vision_info)
    if minutes_aux:
        blocks.append(minutes_aux)
    return "\n\n".join(blocks).strip()


def _log_task_payload(
    lang: str,
    transcript: str,
    keypoints: str,
    notes: str,
    vision_info: str,
    aux_text: str = "",
    docs: list[str] | None = None,
) -> None:
    """按工业级规范输出输入载荷关键指标日志 [task:payload]。"""
    # 1. transcript
    if transcript and transcript.strip():
        n = len(transcript.strip())
        t_str = f"{n / 1000:.1f}k_chars" if n >= 1000 else f"{n}_chars"
    else:
        t_str = "none"

    # 2. keypoints
    if keypoints and keypoints.strip():
        kp_lines = [l.strip() for l in keypoints.strip().splitlines() if l.strip()]
        kp_chars = len(keypoints.strip())
        kp_str = f"{len(kp_lines)}_items({kp_chars}_chars)"
    else:
        kp_str = "none"

    # 3. notes
    if notes and notes.strip():
        parsed = _parse_notes_items(notes)
        q_cnt = sum(1 for it in parsed if it.get("quote"))
        c_cnt = len(parsed) - q_cnt
        if q_cnt > 0 and c_cnt > 0:
            notes_str = f"{q_cnt}_quotes/{c_cnt}_comments"
        elif q_cnt > 0:
            notes_str = f"{q_cnt}_quotes"
        elif c_cnt > 0:
            notes_str = f"{c_cnt}_comments"
        else:
            notes_str = f"{len(notes.strip())}_chars"
    else:
        notes_str = "none"

    # 4. vision
    if vision_info and vision_info.strip():
        v_chars = len(vision_info.strip())
        vision_str = f"{v_chars / 1000:.1f}k_chars" if v_chars >= 1000 else f"{v_chars}_chars"
    else:
        vision_str = "none"

    # 5. aux
    if aux_text and aux_text.strip():
        aux_len = len(aux_text.strip())
        aux_str = f"injected({aux_len}_chars)"
    else:
        aux_str = "none"

    docs_str = f" docs={','.join(docs)}" if docs else ""
    logger.info(
        "[task:payload] lang=%s transcript=%s keypoints=%s notes=%s vision=%s aux=%s%s",
        lang or "zh",
        t_str,
        kp_str,
        notes_str,
        vision_str,
        aux_str,
        docs_str,
    )


def _prepare_input_dir(transcript: str) -> Path | None:
    """非 library 任务的输入准备：只写主文本 input.txt（sidecar 走 line_extra 注入）。"""
    if not transcript.strip():
        return None
    tmp = Path(tempfile.mkdtemp(prefix="agentflow_api_"))
    (tmp / "input.txt").write_text(transcript, encoding="utf-8")
    return tmp / "input.txt"


def _validate(req: TaskRequest, task: str, user_id: str) -> str:
    """基础校验，返回代码线名；失败抛 ApiError。"""
    if task not in LINE_NAMES:
        raise ApiError(404, f"任务线不存在：{task}")
    line = task  # 线名即 task 取值（见 app/tasklines.lines_for）

    # 门禁 2：必传字段表校验（前置收集全部缺失项，一次性秒回 400）
    from .requirements import check_required

    missing = check_required(line, req, user_id)
    if missing:
        raise ApiError(400, f"{task} 缺少必填项：" + "、".join(missing))

    # 门禁 3：业务参数合法性校验
    if line == "minutes_styles" and (req.extra.style or "").strip():
        style = req.extra.style.strip().lower()
        if style not in STYLE_CHOICES:
            raise ApiError(400, f"extra.style 非法：{style}（可选：{'/'.join(sorted(STYLE_CHOICES))}）")
    return line


def _template_file(
    domain: str,
    line: str,
    template_value: str,
    profile_value: str = "",
    style_value: str = "",
    is_agenda_enhanced: bool = False,
    lang: str = "zh",
) -> Path | None:
    """extra.template → 临时模板文件；非法抛 400。

    取值只两种：模板 md 英文名（``project_progress``）、模板中文名（``项目进度会``）。

    **纪要线留空 → 自动套用默认模板**：
    - 客观模式（profile 为空或 objective）：始终套用「通用纪要」（``DEFAULT_MINUTES_TEMPLATE``）；
    - 真人模式（profile="user"）：直接套用「个人视角纪要」（``DEFAULT_PERSONAL_MINUTES_TEMPLATE``，即 ``personal_minutes``），不再走历史通用模板剪裁模式。
    - 多样式纪要线（meeting/minutes_styles）：留空时自动套用对应 style 模板（resources/task/styles/{style}.md）。
    """
    value = (template_value or "").strip()
    auto_default = False
    if domain == "meeting" and line == "minutes_styles":
        if not value:
            # 当请求未指定 template 时，根据 extra.style 自动查找 resources/task/styles/ 下的对应模板
            style_mode = (style_value or "topic").strip().lower()
            return style_template_path(style_mode)
    elif domain == "meeting" and line == "minutes":
        is_personal = (profile_value or "").strip().lower() == "user"
        if not value:
            value = DEFAULT_PERSONAL_MINUTES_TEMPLATE if is_personal else DEFAULT_MINUTES_TEMPLATE
            auto_default = True
        elif is_personal and value in {"general_minutes", "通用纪要"}:
            # 个人视角不再走历史通用模板剪裁模式，直接走专属个人视角纪要模板
            value = DEFAULT_PERSONAL_MINUTES_TEMPLATE
    elif domain == "meeting" and line == "consensus_decision":
        if not value:
            value = DEFAULT_CONSENSUS_DECISION_TEMPLATE
            auto_default = True
    elif not value:
        return None
    fmt = resolve_agenda_template_format(value, lang=lang) if is_agenda_enhanced else resolve_template_format(value, lang=lang)
    if not fmt:
        if auto_default:
            logger.warning(
                "默认纪要模板 %s 不在模板注册表，本次退回无模板：domain=%s",
                value,
                domain,
            )
            return None
        raise ApiError(
            400,
            f"extra.template 非法：{template_value}（可填模板 md 英文名或中文名，"
            "如 project_progress、项目进度会）",
        )
    path = Path(tempfile.mkdtemp(prefix="agentflow_tpl_")) / "template.md"
    path.write_text(fmt, encoding="utf-8")
    return path


def _profile_file(domain: str, profile_value: str, user_id: str = "") -> Path:
    """画像文件定位（选档规则见 ``app.config.profile_path``）。"""
    path = profile_path(domain, profile_value, user_id)
    if not path or not path.is_file():
        hint = (
            "空=默认档（客观全员）；user=真人档案 data/{user_id}/user.json；"
            "objective/object=客观全员；或职业模板名（developer 等）"
        )
        raise ApiError(400, f"extra.profile 非法：{profile_value or '(空)'}（可选：{hint}）")
    return path


def _profile_mode_from_file(path: Path) -> str:
    """画像文件 → objective / personal / role_template（与编排层同源）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 画像文件异常交给后续 load_user 报错
        return "objective"
    if not isinstance(data, dict):
        return "objective"
    # user.json 与 load_user 同源清洗：perspective 忽略、persona_type 置空，
    # 避免用户误写 role_template 把真人档误判成职业模板。
    if is_user_profile_file(path):
        data = sanitize_user_profile(data)
    return resolve_profile_mode(data)


def _subject_pinyin(subject: str) -> str:
    """学科统一转拼音（物理 → wuli），与知识库 subject / catalog 目录一致；空值原样。"""
    from infra.storage.config import subject_to_pinyin

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
    time: str = ""
    lang: str = "zh"
    # 议题纪要视角裁决 / 给调用方的提示（role_template 强制客观等）
    minutes_view: str = ""
    prepare_warning: str = ""
    # 场景识别 Agent 的状态（API 层只组装；由 graph 前置节点消费）
    template_auto: bool = False
    template_source: str = ""
    template_id: str = ""
    template_mode: str = "normal"
    transcript: str = ""


def _runner_args(p: _Prepared) -> dict:
    """`prepare_run` / `run` 的公共实参（同步与流式共用一份，避免两处长块漂移）。

    全部走关键字：历史上两处各写 19 个位置实参，其中 6 个是恒 None 的 CLI 时代参数
    （chapter/level/grade/edition/difficulty/qtype，runner 侧仍保留签名以兼容 CLI 用法）。
    """
    return {
        "file": p.input_files,
        "profile": p.profile_file,
        "env_file": PROJECT_ROOT / ".env",
        "templates": p.templates,
        "tasks": [p.line],
        "modes": p.modes,
        "user_id": p.user_id or None,
        "project_id": p.project or None,
        "subject": p.subject or None,
        "compile_natural": True,
        "monitor": False,
        "collect_reports": True,
        "extra_line_inputs": p.extra_line_inputs,
        "memory": p.memory,
        "meeting_time": p.time,
        "lang": p.lang,
        "template_auto": p.template_auto,
        "template_source": p.template_source,
        "template_id": p.template_id,
        "template_mode": p.template_mode,
    }


def _explicit_template_id(value: str, lang: str = "zh") -> str:
    """显式模板取值 → 英文模板 ID（中文显示名 / 带 .md 均可）；无法识别时保留原值。"""
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.lower().endswith(".md"):
        raw = raw[:-3].strip()
    key = template_key(raw, lang=lang)
    item = template_registry(lang=lang).get(key) or {}
    return str(item.get("template") or raw)


def _prepare(domain: str, task: str, req: TaskRequest, user_id: str) -> _Prepared:
    """校验 + 输入组装（run_task / stream_task 共用；失败抛 ApiError）。"""
    load_env()  # 提前加载：docs 的 OCR 引擎分派依赖 OCR_ENGINE
    line = _validate(req, task, user_id)
    extra = req.extra

    transcript, keypoints, notes, vision_info, actions_text = _collect_texts(req)
    if not transcript and notes:
        transcript = notes
    if transcript:
        from core.graph.engine_text import normalize_transcript

        transcript = normalize_transcript(transcript)
    teacher_docs: list[str] = []
    material_docs: list[str] = []
    agenda_from_docs: str = ""
    valid_agenda_count = 0
    if line != "library" and req.docs:
        if line == "checklist":
            # checklist 的 docs：仅支持老师重点文件（.txt），目录文件统一由 extra.catalog 传参
            for name in req.docs:
                if _is_teacher_txt_name(name):
                    teacher_docs.append(name.strip())
                elif _is_catalog_json_name(name):
                    # 容错：若未在 pydantic 阶段被移入 extra.catalog，在此做兼容填充
                    if not (extra.catalog or "").strip():
                        extra.catalog = name.strip()
                    else:
                        raise ApiError(400, f"checklist 目录文件已在 extra.catalog 指定，docs 中不可重复传 .json：{name}")
                else:
                    raise ApiError(
                        400,
                        f"checklist 的 docs 仅支持老师重点文件（.txt）：{name}",
                    )
        elif line == "catalog":
            # catalog 的 docs：.txt 为老师重点文件，其余按资料处理（OCR/解析并入主文本）
            for name in req.docs:
                if _is_teacher_txt_name(name):
                    teacher_docs.append(name.strip())
                else:
                    material_docs.append(name.strip())
        elif line == "agenda_minutes":
            # agenda_minutes 的 docs：既定议程单（文本或图片）。
            # 议程单内容专供 extra_line_inputs，不得并入会议录音转写 transcript
            agenda_parts = []
            image_docs = [n for n in req.docs if _is_image_name(n)]
            text_docs = [n for n in req.docs if not _is_image_name(n)]
            if image_docs:
                from domains.meeting.agenda_vision import extract_agenda_from_image_docs

                image_paths = [_input_file(user_id, "docs", n) for n in image_docs]
                _, ocr_text = extract_agenda_from_image_docs(
                    user_id=user_id,
                    image_docs=image_docs,
                    transcript=transcript,
                    image_paths=image_paths,
                )
                if ocr_text:
                    agenda_parts.append(ocr_text)
            for name in text_docs:
                path = _input_file(user_id, "docs", name)
                try:
                    body = path.read_text(encoding="utf-8").strip()
                except UnicodeDecodeError:
                    body = path.read_text(encoding="gbk", errors="replace").strip()
                if body:
                    agenda_parts.append(body)
            agenda_from_docs = "\n\n".join(agenda_parts).strip()
        elif line == "minutes":
            # minutes 的 docs：优先探测是否为既定议程单（文本或图片）；
            # 若探测出有效实质议题，则提取为 agenda_text 专供议题结构化，不并入 transcript；
            # 若未探测出有效议题（传的是参考资料、财务报表、纯代码等，或现场全未讨论），
            # 必须默认回退！将其纳入 material_docs，正常 OCR/预览并入 transcript，100% 保持 legacy 行为。
            candidate_parts = []
            image_docs = [n for n in req.docs if _is_image_name(n)]
            text_docs = [n for n in req.docs if not _is_image_name(n)]
            if image_docs:
                from domains.meeting.agenda_vision import extract_agenda_from_image_docs

                image_paths = [_input_file(user_id, "docs", n) for n in image_docs]
                _, ocr_text = extract_agenda_from_image_docs(
                    user_id=user_id,
                    image_docs=image_docs,
                    transcript=transcript,
                    image_paths=image_paths,
                    lang=req.lang,
                )
                if ocr_text:
                    candidate_parts.append(ocr_text)
            for name in text_docs:
                path = _input_file(user_id, "docs", name)
                try:
                    body = path.read_text(encoding="utf-8").strip()
                except UnicodeDecodeError:
                    body = path.read_text(encoding="gbk", errors="replace").strip()
                if body:
                    candidate_parts.append(body)
            candidate_agenda_text = "\n\n".join(candidate_parts).strip()

            from domains.meeting.agenda_engine import probe_valid_agendas

            valid_agendas = (
                probe_valid_agendas(
                    transcript,
                    candidate_agenda_text,
                    lang=req.lang,
                )
                if (candidate_agenda_text and transcript)
                else []
            )
            if valid_agendas:
                agenda_from_docs = candidate_agenda_text
                valid_agenda_count = len(valid_agendas)
                logger.info(
                    "minutes 任务检测到 docs 包含 %d 个有效讨论议题，激活议题增强流水线",
                    len(valid_agendas),
                )
            else:
                logger.info(
                    "minutes 任务 docs 未探测到有效讨论议题，静默回退至常规参考资料流程",
                )
                material_docs = [name.strip() for name in req.docs]
        else:
            material_docs = [name.strip() for name in req.docs]
        if material_docs and line == "graph":
            # graph：图片走「OCR + LLM 整理审校」生成 md 后直接解析图谱（不经知识库入库）；
            # 非图片文档仍走正文预览
            image_docs = [n for n in material_docs if _is_image_name(n)]
            other_docs = [n for n in material_docs if not _is_image_name(n)]
            if image_docs:
                from infra.ocr.levels.light import images_to_reviewed_markdown

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

    ctx = load_domain(domain)
    profile_file = _profile_file(domain, extra.profile, (user_id or "").strip())
    # 只有 minutes 需要运行视角裁决；其它线保持原路径，避免额外读盘。
    profile_mode = (
        _profile_mode_from_file(profile_file) if line == "minutes" else "objective"
    )
    effective_profile = extra.profile
    prepare_warning = ""
    minutes_view = profile_mode

    if line == "minutes" and agenda_from_docs:
        from domains.meeting.views import (
            AgendaPersonalUnsupported,
            resolve_minutes_view,
        )

        mode_label = (
            "personal"
            if profile_mode == "personal"
            else ("role" if profile_mode == "role_template" else "objective")
        )
        try:
            minutes_view = resolve_minutes_view(
                has_valid_agenda=True,
                profile_mode=profile_mode,
            )
        except AgendaPersonalUnsupported as exc:
            logger.info(
                "[minutes:view] requested=agenda_%s resolved=rejected "
                "profile_mode=%s valid_agendas=%d action=rejected_personal",
                mode_label,
                profile_mode,
                valid_agenda_count,
            )
            raise ApiError(400, str(exc)) from exc

        action = "agenda_objective"
        if profile_mode == "role_template":
            # 职业模板在议题模式下统一按客观运行：剥离角色画像/姓名。
            effective_profile = "objective"
            profile_file = _profile_file(
                domain, effective_profile, (user_id or "").strip()
            )
            prepare_warning = "职业模板在议题模式下按客观纪要生成（未使用角色画像）。"
            action = "forced_objective_role"
        logger.info(
            "[minutes:view] requested=agenda_%s resolved=%s profile_mode=%s "
            "valid_agendas=%d action=%s",
            mode_label,
            minutes_view,
            profile_mode,
            valid_agenda_count,
            action,
        )
    elif line == "minutes":
        mode_label = (
            "personal"
            if profile_mode == "personal"
            else ("role" if profile_mode == "role_template" else "objective")
        )
        logger.info(
            "[minutes:view] requested=normal_%s resolved=%s profile_mode=%s "
            "valid_agendas=0 action=normal",
            mode_label,
            minutes_view,
            profile_mode,
        )

    template_path = _template_file(
        domain,
        line,
        extra.template,
        profile_value=effective_profile,
        style_value=extra.style,
        is_agenda_enhanced=bool(agenda_from_docs),
        lang=req.lang,
    )

    # 输入文件：library 传原文件路径列表（docs 图片+文档全量入库）；其余传临时文件/目录
    input_files: list[Path] | Path | None
    if line == "library":
        input_files = [_input_file(user_id, "docs", name) for name in req.docs]
    elif line in {"catalog", "checklist"} and not transcript.strip():
        input_files = None
    else:
        input_files = _prepare_input_dir(transcript)
        if input_files is None and line not in {"catalog", "checklist"}:
            raise ApiError(400, "texts / docs 未能产生有效输入")

    modes: dict[str, str] = {}
    if line == "minutes_styles" and (extra.style or "").strip():
        modes["minutes_styles"] = extra.style.strip().lower()
    templates: dict[str, Path] = {}
    if template_path is not None:
        templates[line] = template_path
    extra_line_inputs: dict[str, str] = {}
    aux_text = ""
    if line == "minutes_trace":
        trace_text = _trace_extra(keypoints, notes)
        if trace_text:
            extra_line_inputs["minutes_trace"] = trace_text
            aux_text = trace_text
    if line == "checklist" and (extra.catalog or "").strip():
        _catalog_input_file(user_id, extra.subject, extra.catalog.strip())
        extra_line_inputs["checklist"] = "【目录文件】" + extra.catalog.strip()
    if line in {"catalog", "checklist"} and teacher_docs:
        teacher_block = _load_teacher_texts(user_id, teacher_docs)
        if teacher_block:
            prev = extra_line_inputs.get(line) or ""
            extra_line_inputs[line] = f"{prev}\n\n{teacher_block}".strip()
    if line == "agenda_minutes":
        # 既定议程单汇聚：支持 docs（图片OCR/文档文本）与 extra.agenda_txt（纯文本补充）智能拼接合并
        parts = [p for p in [agenda_from_docs, (extra.agenda_txt or "").strip()] if p]
        agenda_val = "\n\n".join(parts).strip()
        if agenda_val:
            extra_line_inputs["agenda_minutes"] = agenda_val
    if line == "minutes":
        aux_text = _pack_minutes_auxiliary(keypoints, notes, vision_info)
        if aux_text:
            extra_line_inputs["minutes_auxiliary"] = aux_text
        if agenda_from_docs:
            extra_line_inputs["agenda_text"] = agenda_from_docs
    if line == "actions":
        # Phase 1：只准备 actions 专用辅助材料，暂不注入生成上下文。
        actions_aux = _pack_actions_auxiliary(actions_text, keypoints, notes, vision_info)
        if actions_aux:
            extra_line_inputs["actions_auxiliary"] = actions_aux
            aux_text = actions_aux
    if line in {"review", "quiz"}:
        scope_parts = []
        if (user_id or "").strip():
            scope_parts.append(f"【用户ID】{(user_id or '').strip()}")
        if (extra.subject or "").strip():
            scope_parts.append(f"【学科/课程】{(extra.subject or '').strip()}")
        if scope_parts:
            extra_line_inputs[line] = "\n".join(scope_parts)

    # 场景识别状态：API 层只组装并透传，由 graph 前置节点决定是否切换模板。
    template_mode = "agenda" if agenda_from_docs else "normal"
    template_auto = False
    template_source = ""
    template_id = ""
    if line == "minutes":
        requested_template = (extra.template or "").strip()
        if requested_template:
            template_source = "explicit"
            template_id = _explicit_template_id(requested_template, req.lang)
        elif effective_profile == "user":
            template_source = "personal_default"
            template_id = "personal_minutes"
        else:
            template_source = "default"
            template_id = "general_minutes"
            template_auto = minutes_template_auto_mode() != "off"

    _log_task_payload(
        lang=req.lang,
        transcript=transcript,
        keypoints=keypoints,
        notes=notes,
        vision_info=vision_info,
        aux_text=aux_text,
        docs=req.docs,
    )

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
        memory=bool(req.memory),
        time=(extra.time or "").strip(),
        lang=req.lang,
        minutes_view=minutes_view,
        prepare_warning=prepare_warning,
        template_auto=template_auto,
        template_source=template_source,
        template_id=template_id,
        template_mode=template_mode,
        transcript=transcript,
    )


async def _maybe_generate_visual_minutes(p: _Prepared, request_id: str, md_text: str) -> None:
    if (
        p.line == "minutes"
        and os.getenv("VISUAL_MINUTES_ENABLED", "off").strip().lower() == "on"
        and md_text
    ):
        _vm_start = time.time()
        logger.info(
            "[visual_minutes:start] req_id=%s md_len=%d transcript_len=%d",
            request_id,
            len(md_text),
            len(p.transcript),
        )
        try:
            from domains.shared.visual_minutes.pipeline import agenerate_visual_minutes

            visual_html_path = p.ctx.output_dir / "visual.html"
            await agenerate_visual_minutes(
                minutes_markdown=md_text,
                meeting_transcript=p.transcript,
                output_path=str(visual_html_path),
            )
            _vm_dur = round(time.time() - _vm_start, 2)
            logger.info(
                "[visual_minutes:finish] req_id=%s output=%s dur=%.2fs status=success",
                request_id,
                visual_html_path,
                _vm_dur,
            )
        except Exception as exc:
            logger.warning(
                "[visual_minutes:failed] req_id=%s error=%s status=fallback",
                request_id,
                exc,
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
    request_id = (request_id or "").strip() or next_request_id()
    return await _run_task_impl(domain, task, req, user_id, request_id, _start_time)


async def _run_task_impl(
    domain: str,
    task: str,
    req: TaskRequest,
    user_id: str,
    request_id: str,
    _start_time: float,
) -> TaskResponse:
    logger.info(
        "[task:start] domain=%s task=%s req_id=%s user_id=%s lang=%s memory=%s",
        domain,
        task,
        request_id,
        user_id,
        req.lang or "zh",
        str(bool(req.memory)).lower(),
    )
    p = await asyncio.to_thread(_prepare, domain, task, req, user_id)
    # 产物直接写入本次请求目录（data/{user_id}/output/{request_id}/），不再走根目录 output/ 归档
    p.ctx.output_dir = output_dir(user_id, request_id)

    from core.runner.runner import run

    try:
        result = await run(p.ctx, **_runner_args(p))
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001 - 运行失败统一转 500
        cost_time = round((time.time() - _start_time), 2)
        logger.exception(
            "[task:failed] req_id=%s dur=%.2fs error=%s status=failed",
            request_id,
            cost_time,
            exc,
        )
        raise ApiError(500, f"任务运行失败：{exc}") from exc

    saved = (result or {}).get("saved") or {}
    saved_paths = save_task_outputs(user_id, request_id, saved)
    reports = (result or {}).get("reports") or {}
    usage = (result or {}).get("usage") or {}

    md_text = ""
    if p.line == "checklist" and p.line in reports:
        # checklist 以 HTML 交互页为主：data.text 返回精简摘要（统计 + 卡片列表），
        # 全量 Markdown 仍落盘 result.md 存档
        from domains.notes.tasks.checklist.display import build_checklist_summary

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
        from infra.exporters.outputs import report_text

        md_text = report_text(reports[p.line])
    from .schemas import Monitor, ResponseData

    response = TaskResponse(
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
    # 仅降级时有值：把质量信号放在**字段**里（正文不再写免责声明），与异步任务接口口径一致。
    # 未赋值时该字段不出现在响应里（app 配了 response_model_exclude_unset）。
    warning = str((result or {}).get("quality_warning") or "").strip()
    if not warning:
        warning = str(getattr(p, "prepare_warning", "") or "").strip()
    if warning:
        response.quality_warning = warning
    # 自动扩展生成图文纪要 HTML（VISUAL_MINUTES_ENABLED=on 时生效）
    await _maybe_generate_visual_minutes(p, request_id, response.data.text)

    logger.info(
        "[task:finish] req_id=%s dur=%.2fs total_tokens=%d status=success",
        request_id,
        response.monitor.cost_time,
        response.monitor.token_usage,
    )
    return response


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
    - {"type": "error", "code": int, "message": str}  运行失败；code 为 4xx 表示输入类错误
      （重试无意义），5xx 表示可重试的运行错误。
    域名/任务线白名单校验仍在路由层直接返回 HTTP 错误；`_prepare` 阶段的输入
    错误（缺必填、文件不存在、personal×agenda 400 等）通过 error 事件返回，
    避免流已建立后抛异常导致客户端只看到断流。
    """
    request_id = (request_id or "").strip() or next_request_id()
    return await _stream_task_impl(domain, task, req, user_id, request_id)


async def iter_task_events(
    domain: str,
    task: str,
    req: TaskRequest,
    *,
    user_id: str = "",
    request_id: str = "",
) -> AsyncIterator[dict]:
    """核心事件流生成器：纯 Python 字典事件流，不依赖任何 HTTP/Web 响应对象。"""
    request_id = (request_id or "").strip() or next_request_id()
    logger.info(
        "[stream:start] domain=%s task=%s req_id=%s user_id=%s lang=%s memory=%s",
        domain,
        task,
        request_id,
        user_id,
        req.lang or "zh",
        str(bool(req.memory)).lower(),
    )
    try:
        p = await asyncio.to_thread(_prepare, domain, task, req, user_id)
    except ApiError as exc:
        logger.warning(
            "[stream:error] domain=%s task=%s request_id=%s code=%s message=%s",
            domain,
            task,
            request_id,
            exc.status,
            exc.message,
        )
        yield {"type": "error", "code": exc.status, "message": exc.message}
        return
    except Exception as exc:  # noqa: BLE001 - 准备失败推 error 事件
        logger.exception(
            "[stream:failed] domain=%s task=%s request_id=%s error=%s",
            domain,
            task,
            request_id,
            exc,
        )
        yield {"type": "error", "code": 500, "message": f"任务准备失败：{exc}"}
        return
    # 产物直接写入本次请求目录（data/{user_id}/output/{request_id}/），不再走根目录 output/ 归档
    p.ctx.output_dir = output_dir(user_id, request_id)

    from core.runner.runner import _handle_done, prepare_run

    _start_time = time.time()
    try:
        prep = await prepare_run(p.ctx, **_runner_args(p))
    except ApiError as exc:
        # 输入类错误（缺必填/文件不存在）：带上真实状态码，异步端据此不重试
        logger.warning(
            "[stream:error] req_id=%s code=%s message=%s",
            request_id,
            exc.status,
            exc.message,
        )
        yield {"type": "error", "code": exc.status, "message": exc.message}
        return
    except Exception as exc:  # noqa: BLE001 - 准备失败推 error 事件
        cost_time = round((time.time() - _start_time), 2)
        logger.exception(
            "[stream:failed] req_id=%s dur=%.2fs error=%s status=failed",
            request_id,
            cost_time,
            exc,
        )
        yield {"type": "error", "code": 500, "message": f"任务准备失败：{exc}"}
        return

    system = prep.system
    last_done = None
    try:
        streaming_kwargs = {
            "templates": prep.template_texts,
            "lines": prep.line_names,
            "line_modes": p.modes,
            "line_extra": prep.line_extra,
        }
        sig = inspect.signature(system.run_streaming)
        if "lang" in sig.parameters or any(param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()):
            streaming_kwargs["lang"] = prep.lang
        accepts_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in sig.parameters.values()
        )
        if "meeting_time" in sig.parameters or accepts_kwargs:
            streaming_kwargs["meeting_time"] = p.time
        for name, value in (
            ("template_auto", prep.template_auto),
            ("template_source", prep.template_source),
            ("template_id", prep.template_id),
            ("template_mode", prep.template_mode),
        ):
            if accepts_kwargs or name in sig.parameters:
                streaming_kwargs[name] = value

        async for event in system.run_streaming(
            prep.transcript,
            prep.user,
            **streaming_kwargs,
        ):
            if event["type"] == "phase":
                yield {"type": "phase", "node": event["node"]}
            elif event["type"] == "chunk":
                yield {
                    "type": "chunk",
                    "line": event["line"],
                    "title": event["title"],
                    "text": event["text"],
                }
            elif event["type"] == "done":
                last_done = event
                saved = await _handle_done(
                    prep.ctx,
                    event,
                    memory_on=bool((prep.line_extra or {}).get("__meeting_memory__")),
                ) or {}
                saved_paths = save_task_outputs(user_id, request_id, saved)
                md_text = ""
                if saved_paths.get("md"):
                    md_text = Path(saved_paths["md"]).read_text(encoding="utf-8")
                if p.line == "checklist" and p.line in (event.get("reports") or {}):
                    from domains.notes.tasks.checklist.display import build_checklist_summary
                    from infra.exporters.outputs import report_to_dict

                    _report = report_to_dict((event.get("reports") or {})[p.line])
                    _cards = _report.get("cards") or []
                    if _cards:
                        md_text = build_checklist_summary(
                            course=str(_report.get("course") or ""),
                            catalog_version=str(_report.get("catalog_version") or ""),
                            cards=_cards,
                        )
                if not md_text and p.line in (event.get("reports") or {}):
                    from infra.exporters.outputs import report_text, report_to_dict

                    md_text = report_text(
                        report_to_dict((event.get("reports") or {})[p.line])
                    )
                meeting_meta = (prep.line_extra or {}).get("__meeting_memory__")
                if meeting_meta:
                    from domains.meeting.memory.runtime import persist_after_run

                    persist_after_run(
                        prep.ctx.project_root,
                        user_id,
                        p.project or "",
                        request_id,
                        prep.transcript,
                        event.get("reports") or {},
                        event.get("understanding") or {},
                        meeting_time=p.time,
                        bind=event.get("memory_bind"),
                        drafts=event.get("drafts") or {},
                        degraded_by_line=event.get("degraded_by_line") or {},
                        has_valid_agenda=bool(event.get("has_valid_agenda")),
                        agenda_titles=event.get("agenda_titles") or [],
                    )
                elif prep.memory_enabled and prep.memory_bind is not None:
                    from domains.notes.memory.runtime import persist

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
                out_file = _output_file_name(p.line, user_id, p.subject, saved_paths)
                cost_seconds = round((time.time() - _start_time), 2)
                tokens = int(usage.get("total_tokens", 0) or 0)
                done_warning = (
                    str(event.get("quality_warning") or "").strip()
                    or str(getattr(p, "prepare_warning", "") or "").strip()
                    or None
                )
                logger.info(
                    "[stream:done] req_id=%s dur=%.2fs total_tokens=%d status=success",
                    request_id,
                    cost_seconds,
                    tokens,
                )
                await _maybe_generate_visual_minutes(p, request_id, md_text)
                yield {
                    "type": "done",
                    "code": 0,
                    "request_id": request_id,
                    "message": "success",
                    "quality_warning": done_warning,
                    "monitor": {
                        "token_usage": tokens,
                        "cache_hit": int(usage.get("cache_hit_tokens", 0) or 0),
                        "cost_time": cost_seconds,
                        **_catalog_quality_monitor(p.line, user_id, p.subject),
                    },
                    "data": {
                        "text": md_text,
                        "file_name": out_file,
                    },
                }
    except ApiError as exc:
        logger.warning(
            "[stream:error] domain=%s task=%s request_id=%s code=%s message=%s",
            domain,
            task,
            request_id,
            exc.status,
            exc.message,
        )
        yield {"type": "error", "code": exc.status, "message": exc.message}
    except Exception as exc:  # noqa: BLE001 - 运行失败推 error 事件
        logger.exception(
            "[stream:failed] domain=%s task=%s request_id=%s error=%s",
            domain,
            task,
            request_id,
            exc,
        )
        yield {"type": "error", "code": 500, "message": f"任务运行失败：{exc}"}
    finally:
        if prep.task_monitor is not None:
            try:
                prep.task_monitor.finish(
                    done_event=last_done,
                    extra={"ok": last_done is not None, "error": ""},
                )
            except Exception:  # noqa: BLE001 - 监控落盘失败不影响主流程
                pass


async def _stream_task_impl(
    domain: str,
    task: str,
    req: TaskRequest,
    user_id: str,
    request_id: str,
) -> StreamingResponse:
    async def event_stream():
        async for event in iter_task_events(
            domain, task, req, user_id=user_id, request_id=request_id
        ):
            yield _ndjson(event)

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


__all__ = ["ApiError", "LINE_NAMES", "iter_task_events", "run_task", "stream_task"]
