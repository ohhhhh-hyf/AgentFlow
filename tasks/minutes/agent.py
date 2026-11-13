"""纪要端到端流式直出 Agent：
自包含、零旧 AST 契约、零 Supervisor 审查，大模型直接面向模板与实录生成 Markdown，
通过异步生成器产生 NDJSON 流式事件（chunk 与 done），后处理清洗并落盘至 data/{user_id}/output/{request_id}/minutes.md。
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from core.templates import load_template
from infra.llm.client import LLMClient
from tasks.minutes.agenda.alignment import ValidAgendaItem, process_agenda_for_minutes
from tasks.minutes.classifier.classifier import classify_template
from tasks.minutes.multi_source import build_aux_rules_for_prompt, build_multi_source_context
from tasks.minutes.postprocess import clean_markdown_fence, postprocess_minutes_markdown
from tasks.minutes.prompts import select_minutes_prompt

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _build_agenda_top_anchor(valid_agendas: list[ValidAgendaItem]) -> str:
    """构建头部锚定：现场审定的有效议题清单。"""
    lines: list[str] = ["【现场审定的有效议题清单】（头部锚定：提供全局议题索引与发言人）"]
    for idx, item in enumerate(valid_agendas, 1):
        spk_str = "、".join(item.presenters) if item.presenters else ""
        spk = f"（汇报人：{spk_str}）" if spk_str else ""
        lines.append(f"{idx}. 议题{idx}：{item.title}{spk}")
    return "\n".join(lines)


def _build_agenda_tail_anchor(valid_agendas: list[ValidAgendaItem]) -> str:
    """构建尾部重申：临门一脚二次锁定 N 个议题名称与顺序。"""
    lines: list[str] = [
        f"【核心议程约束与执行指令】（尾部重申：临门一脚锁定 {len(valid_agendas)} 个议题名称与顺序）",
        f"本次会议共有以下 {len(valid_agendas)} 个审定有效议题，在正文中必须 1:1 顺序生成对应小节，严禁增删、改名、拆分或合并：",
    ]
    for idx, item in enumerate(valid_agendas, 1):
        lines.append(f"{idx}. {item.title}")
    lines.extend([
        "",
        "请严格按照上方【输出模板规范】的结构逐个议题闭环展开；",
        "严禁使用任何 ```markdown 等代码围栏包裹，严禁输出任何多余寒暄、说明或前言后语，从首个 `#` 标题开始直接输出 Markdown 正文：",
    ])
    return "\n".join(lines)


def build_minutes_user_message(
    *,
    is_agenda: bool,
    formatted_transcript: str,
    valid_agendas: list[ValidAgendaItem],
    template_content: str,
    aux_context: str = "",
) -> str:
    """按“三明治架构 + 议程前后双锚定”标准装配 User Message。

    结构：
    - 普通模式：实录原材料 -> 辅助材料 -> 动态模板正文 -> 执行指令
    - 议程模式：头部议程清单 -> 实录切片 -> 辅助材料 -> 动态模板正文 -> 尾部重申与执行指令
    """
    parts: list[str] = []

    if is_agenda and valid_agendas:
        # 1. 头部锚定
        parts.append(_build_agenda_top_anchor(valid_agendas))
        # 2. 实录原材料
        parts.append(f"【会议打标转写实录】\n{formatted_transcript}")
    else:
        # 普通模式实录原材料
        parts.append(f"【会议原文转写实录】\n{formatted_transcript}")

    # 3. 辅助参考材料（可选）
    if aux_context:
        parts.append(aux_context)

    # 4. 动态模板规范（绝非硬编码，从模板引擎动态读取）
    template_block = (
        "【输出模板规范】\n"
        "以下是本次会议必须严格遵守的排版结构与写作栏目，请按此模板格式直接输出：\n"
        "```markdown\n"
        f"{template_content}\n"
        "```"
    )
    parts.append(template_block)

    # 5. 尾部指令区
    if is_agenda and valid_agendas:
        parts.append(_build_agenda_tail_anchor(valid_agendas))
    else:
        normal_cmd = (
            "【执行指令】\n"
            "请严格按照上方【输出模板规范】的栏目与结构，从上方实录中提炼客观事实，直接撰写并输出最终 Markdown 正文。\n"
            "严禁使用 ```markdown 等任何代码围栏包裹，严禁输出任何多余寒暄、说明或前言后语，从首个 `#` 标题开始直接输出："
        )
        parts.append(normal_cmd)

    return "\n\n".join(parts)


def resolve_image_doc_path(user_id: str, name: str) -> Path | None:
    """根据 user_id 和文件名解析 data/{user_id}/docs 目录下图片的物理路径.

    严格对齐根项目 domains/meeting/agenda_vision.py:39-49 标准实现。
    """
    raw = (name or "").strip()
    if not raw:
        return None
    raw_path = Path(raw)
    # 1. 尝试直接作为完整有效物理路径
    if raw_path.is_file():
        return raw_path.resolve()

    # 2. 核心规范：data/{user_id}/docs/{name}
    uid = (user_id or "").strip()
    if uid:
        user_p = (DEFAULT_DATA_DIR / uid / "docs" / raw).resolve()
        if user_p.is_file():
            return user_p

    # 3. 兜底全局 docs 目录：data/docs/{name}
    fallback_p = (DEFAULT_DATA_DIR / "docs" / raw).resolve()
    if fallback_p.is_file():
        return fallback_p

    # 4. 容错用户传 "1/docs/xxx.png" 或 "demo/data/1/docs/xxx.png"
    parts = list(raw_path.parts)
    if parts and parts[0] in ("demo", "data"):
        sub_p = Path(*parts[1:])
        demo_root = DEFAULT_DATA_DIR.parent
        if (demo_root / sub_p).is_file():
            return (demo_root / sub_p).resolve()
        if (DEFAULT_DATA_DIR / sub_p).is_file():
            return (DEFAULT_DATA_DIR / sub_p).resolve()

    return None


async def stream_minutes_agent(
    *,
    transcript: str,
    template_id: str = "",
    docs: list[str] | None = None,
    texts: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    user_id: str = "default",
    request_id: str = "",
    lang: str = "zh",
    output_path: Path | str | None = None,
    llm_client: LLMClient | None = None,
) -> AsyncGenerator[str, None]:
    """纪要端到端流式直出 Agent 入口。

    执行步骤：
    1. 议程判定与打标对齐（Phase 3 纯算法，毫秒级完成）；
    2. 智能模板分类（若未指定模板，强制前置匹配，议程候选 20 vs 普通候选 29）；
    3. 自包含模板引擎加载纯净模板与元数据（Phase 1）；
    4. 路由选择最优 System Prompt 与三明治 User Message 拼装；
    5. 调用 LLMClient.stream_text() 实时产出 NDJSON 数据流；
    6. 执行 postprocess_minutes_markdown 后处理清洗；
    7. 用户级隔离落盘至 data/{user_id}/output/{request_id}/minutes.md，产出最终 type: done 事件。

    Yields:
        NDJSON 格式字符串（包含末尾 \\n）
    """
    start_time = time.perf_counter()
    req_id = request_id or uuid.uuid4().hex
    uid = user_id or "default"
    client = llm_client or LLMClient()
    extra_params = extra or {}
    texts_params = texts or {}

    # 1. 议程判定与打标 (docs 图片走 VLM 提取，或从 extra/texts 中直接读取结构化/文本议题)
    agenda_source = (
        extra_params.get("agenda_plan")
        or extra_params.get("agenda")
        or texts_params.get("agenda")
        or ""
    )
    if not agenda_source and docs:
        logger.info(f"[AGENDA:INPUT] received docs_count={len(docs)} user_id={uid} docs={docs}")
        for doc_item in docs:
            resolved_doc = resolve_image_doc_path(user_id=uid, name=doc_item)
            if not resolved_doc:
                logger.warning(f"[AGENDA:DOC:NOT_FOUND] Cannot find doc file on disk: user_id={uid} name={doc_item}")
                continue
            if resolved_doc.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                logger.info(f"[VLM:REQ] file={resolved_doc.name} path={resolved_doc} size={resolved_doc.stat().st_size}B")
                try:
                    from infra.vlm.agenda_client import extract_agenda_from_image
                    vlm_res = extract_agenda_from_image(resolved_doc)
                    if vlm_res and vlm_res.get("agenda_items"):
                        items = vlm_res["agenda_items"]
                        titles = [str(it.get("title", "")) for it in items]
                        logger.info(f"[VLM:RES] status=success items={len(items)} titles={titles}")
                        agenda_source = vlm_res
                        break
                    else:
                        logger.warning(f"[VLM:RES] status=empty_or_failed file={resolved_doc.name}")
                except Exception as vlm_err:
                    logger.warning(f"[VLM:RES:ERROR] file={resolved_doc.name} err={vlm_err}")
    elif agenda_source:
        logger.info(f"[AGENDA:INPUT] source=text_or_plan len={len(str(agenda_source))}")
    else:
        logger.info("[AGENDA:INPUT] source=none mode=normal")

    agenda_result = process_agenda_for_minutes(
        transcript=transcript,
        agenda=agenda_source,
    )
    is_agenda = agenda_result.has_valid_agenda
    valid_agendas = agenda_result.valid_agendas
    formatted_transcript = agenda_result.tagged_transcript if is_agenda else transcript

    logger.info(
        f"[AGENDA:DECISION] is_agenda={is_agenda} valid_count={len(valid_agendas)} "
        f"mode={'topic_major' if is_agenda else 'normal'} "
        f"reason={'aligned ' + str(len(valid_agendas)) + ' discussion topics' if is_agenda else 'no valid discussion aligned, fallback normal'}"
    )

    # 2. 智能模板匹配（无开关，未指定则强制自动触发）
    chosen_template = (template_id or extra_params.get("template") or "").strip()
    if not chosen_template or chosen_template.lower() in ("auto", "none", ""):
        matched_tid, _ = await classify_template(
            transcript=transcript,
            is_agenda=is_agenda,
            llm_client=client,
        )
        chosen_template = matched_tid or "general_minutes"

    # 3. 动态加载模板正文与元数据 (支持多语言)
    template_content, metadata = load_template(chosen_template, is_agenda=is_agenda, lang=lang)
    layout_mode = metadata.get("layout", {}).get("mode", "column_major")

    # 4. 选择 System Prompt 并注入辅助材料规约
    system_prompt = select_minutes_prompt(is_agenda=is_agenda, layout_mode=layout_mode, lang=lang)
    aux_context, active_labels = build_multi_source_context(texts_params)
    aux_rules = build_aux_rules_for_prompt(active_labels)
    if aux_rules:
        system_prompt = f"{system_prompt}\n\n{aux_rules}"

    # 5. 拼装黄金三明治 User Message（原文在前，模板规范与指令殿后）
    user_message = build_minutes_user_message(
        is_agenda=is_agenda,
        formatted_transcript=formatted_transcript,
        valid_agendas=valid_agendas,
        template_content=template_content,
        aux_context=aux_context,
    )

    # 6. 流式调用 LLMClient 并封装 NDJSON Chunk
    full_chunks: list[str] = []
    try:
        async for token in client.stream_text(prompt=user_message, system=system_prompt):
            full_chunks.append(token)
            chunk_event = {
                "type": "chunk",
                "line": "minutes",
                "title": "",
                "text": token,
            }
            yield json.dumps(chunk_event, ensure_ascii=False) + "\n"
    except Exception as exc:
        logger.error(f"LLM stream_text error: {exc}", exc_info=True)
        # 异常时下发错误帧
        err_event = {
            "type": "done",
            "code": 500,
            "request_id": req_id,
            "message": f"LLM stream generation failed: {exc}",
            "monitor": {"cost_time": round(time.perf_counter() - start_time, 2)},
            "data": {},
        }
        yield json.dumps(err_event, ensure_ascii=False) + "\n"
        return

    # 7. 全量内容后处理清洗与用户隔离落盘
    raw_markdown = "".join(full_chunks)
    cleaned_markdown = postprocess_minutes_markdown(raw_markdown, lang=lang)

    if output_path:
        target_path = Path(output_path)
    else:
        target_path = DEFAULT_DATA_DIR / uid / "output" / req_id / "minutes.md"

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(cleaned_markdown, encoding="utf-8")
        logger.info(f"[ARTIFACT:SAVE] type=minutes path={target_path}")
    except Exception as io_err:
        logger.warning(f"[ARTIFACT:SAVE:ERROR] type=minutes path={target_path} err={io_err}")

    cost_time = round(time.perf_counter() - start_time, 2)
    logger.info(f"[MINUTES:DONE] req_id={req_id} dur={cost_time:.2f}s file={target_path}")
    done_event = {
        "type": "done",
        "code": 0,
        "request_id": req_id,
        "message": "success",
        "monitor": {"cost_time": cost_time},
        "data": {
            "content": cleaned_markdown,
            "text": cleaned_markdown,
            "file_name": target_path.name,
        },
    }
    yield json.dumps(done_event, ensure_ascii=False) + "\n"


async def generate_minutes(
    *,
    transcript: str,
    template_id: str = "",
    docs: list[str] | None = None,
    texts: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    user_id: str = "default",
    request_id: str = "",
    lang: str = "zh",
    output_path: Path | str | None = None,
    llm_client: LLMClient | None = None,
) -> tuple[str, dict[str, Any]]:
    """便捷同步聚合函数（非流式读取全部流式事件），返回 (完整纪要Markdown, done事件dict)。"""
    content_chunks: list[str] = []
    last_done: dict[str, Any] = {}

    async for line in stream_minutes_agent(
        transcript=transcript,
        template_id=template_id,
        docs=docs,
        texts=texts,
        extra=extra,
        user_id=user_id,
        request_id=request_id,
        lang=lang,
        output_path=output_path,
        llm_client=llm_client,
    ):
        event = json.loads(line)
        if event.get("type") == "chunk":
            content_chunks.append(event.get("text", ""))
        elif event.get("type") == "done":
            last_done = event

    return postprocess_minutes_markdown("".join(content_chunks), lang=lang), last_done
