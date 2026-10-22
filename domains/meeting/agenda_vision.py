"""domains.meeting.agenda_vision -- 会议域通用视觉议程抽取与双轨高可用调度器。

核心职责：
1. 主通道：优先调用内部视觉多模态大模型服务（AgendaVisionClient），最多重试 3 次；
2. 兜底通道：若视觉接口 3 次重试仍失败，平滑降级至传统 OCR（边缘填充 + OCR + LLM Markdown重构）兜底流水线；
3. 数据适配：将视觉大模型返回的高保真 JSON（或 OCR 识别结果）统一转换为强类型 AgendaPlan 与标准 Markdown 表格文本；
4. 全局收拢：为 minutes（议题增强模式）与 agenda_minutes 任务提供统一公共能力，彻底解耦跨任务依赖。
"""
from __future__ import annotations

import copy
from datetime import datetime
import logging
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from infra.vlm import AgendaVisionClient
from domains.meeting.tasks.agenda_minutes.agenda_parser import (
    AgendaItemParsed,
    AgendaMeta,
    AgendaPlan,
    extract_speakers_from_transcript,
    parse_agenda_text,
    reconcile_presenter_names,
    _PARSED_AGENDA_CACHE,
    _PARSED_AGENDA_RAW_CACHE,
)
from domains.meeting.tasks.agenda_minutes.agenda_extractor import reconstruct_agenda_markdown
from infra.ocr.engines import ocr_engine_label
from infra.ocr.layout import ocr_image_lines
from infra.ocr.levels.light import ocr_log

logger = logging.getLogger("agentflow.meeting.agenda_vision")


def resolve_image_doc_path(user_id: str, name: str) -> Path:
    """根据 user_id 和文件名解析 docs 目录下图片的实际物理路径。"""
    raw = (name or "").strip()
    data_root = Path("data").resolve()
    uid = (user_id or "").strip()
    if uid:
        user_p = (data_root / uid / "docs" / raw).resolve()
        if user_p.exists():
            return user_p
    fallback_p = (data_root / "docs" / raw).resolve()
    return fallback_p


def pad_image_bottom(image_path: str, pad_px: int = 100) -> str | None:
    """在图片底部添加白色填充，防止传统 OCR 检测模型边缘截断导致末尾行丢失。

    返回填充后图片的临时路径。失败时返回 None（调用方退回原图）。
    """
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            w, h = img.size
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            new_img = Image.new("RGB", (w, h + pad_px), (255, 255, 255))
            new_img.paste(img, (0, 0))

            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            new_img.save(tmp_path)
            return tmp_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("pad_image_bottom failed for %s: %s", image_path, exc)
        return None


def clean_person_names(raw_val: Any) -> list[str]:
    """清洗提取纯净的人名列表。"""
    if isinstance(raw_val, list):
        names = []
        for x in raw_val:
            s = str(x).strip()
            if s:
                names.append(s)
        return names
    if isinstance(raw_val, str) and raw_val.strip():
        parts = re.split(r"[;；,，、\s]+", raw_val.strip())
        return [p.strip() for p in parts if p.strip()]
    return []


def vision_json_to_agenda_plan(
    data: dict[str, Any],
    transcript: str = "",
    candidate_speakers: list[str] | set[str] | None = None,
) -> AgendaPlan:
    """将视觉大模型输出的结构化字典转换为领域标准 AgendaPlan。"""
    meta = AgendaMeta()
    meta.theme = str(data.get("theme") or "").strip()
    meta.date_time = str(data.get("date_time") or "").strip()

    raw_attendees = data.get("attendees")
    cleaned_attendees = clean_person_names(raw_attendees)
    meta.attendees = "；".join(cleaned_attendees)

    items: list[AgendaItemParsed] = []
    raw_items = data.get("agenda_items") or []
    if isinstance(raw_items, list):
        for idx, it in enumerate(raw_items, 1):
            if not isinstance(it, dict):
                continue
            title = str(it.get("title") or it.get("name") or "").strip()
            if not title:
                continue

            seq_raw = it.get("seq")
            seq = str(seq_raw).strip() if seq_raw is not None else f"{idx:02d}"
            if seq.isdigit() and len(seq) == 1:
                seq = f"0{seq}"

            # 汇报人键名防御性兼容：支持 presenters / attendees / reporter
            pres_raw = it.get("presenters") or it.get("attendees") or it.get("reporter")
            presenters = clean_person_names(pres_raw)
            raw_presenter = "；".join(presenters)

            time_range = str(it.get("time_range") or it.get("time") or "").strip()
            duration = str(it.get("duration") or "").strip()

            items.append(
                AgendaItemParsed(
                    seq=seq,
                    title=title,
                    presenters=presenters,
                    raw_presenter=raw_presenter,
                    time_range=time_range,
                    duration=duration,
                )
            )

    plan = AgendaPlan(meta=meta, items=items)

    # 发言人错别字/同音字校对对齐
    if items and (transcript or candidate_speakers):
        plan = reconcile_presenter_names(
            plan,
            transcript=transcript,
            candidate_speakers=candidate_speakers,
        )

    return plan


def agenda_plan_to_markdown(plan: AgendaPlan) -> str:
    """将 AgendaPlan 序列化为规范的标准 Markdown 议程文本（含元数据与标准管道表格）。"""
    if not plan or not plan.items:
        return ""

    lines: list[str] = []
    if plan.meta.theme:
        lines.append(f"**会议主题**：{plan.meta.theme}")
    if plan.meta.date_time:
        lines.append(f"**会议时间**：{plan.meta.date_time}")
    if plan.meta.attendees:
        lines.append(f"**全程与会人/主持人**：{plan.meta.attendees}")

    if lines:
        lines.append("")

    lines.append("| 序号 | 议题名称 | 汇报人/主讲人 | 预计时长 |")
    lines.append("| :--- | :--- | :--- | :--- |")

    for it in plan.items:
        pres_str = "；".join(it.presenters) if it.presenters else (it.raw_presenter or "")
        dur_str = it.duration or it.time_range or ""
        lines.append(f"| {it.seq} | {it.title} | {pres_str} | {dur_str} |")

    return "\n".join(lines).strip()


def save_agenda_ocr_debug_snapshot(content: str, prefix: str = "agenda_ocr") -> None:
    """保存议程提取快照到 logs/agenda_ocr/latest_agenda_ocr.md 供排查追踪。"""
    try:
        log_dir = Path("logs/agenda_ocr")
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        (log_dir / "latest_agenda_ocr.md").write_text(content, encoding="utf-8")
        (log_dir / f"{prefix}_{stamp}.md").write_text(content, encoding="utf-8")
        logger.info(
            "Saved agenda snapshot to logs/agenda_ocr/latest_agenda_ocr.md (%d chars)",
            len(content),
        )
    except Exception as err:  # noqa: BLE001
        logger.warning("Failed to save agenda debug snapshot: %s", err)


def ocr_fallback_single_agenda_doc(
    image_paths: list[Path | str],
    candidate_speakers: list[str] | set[str] | None = None,
) -> tuple[AgendaPlan | None, str]:
    """传统 OCR 兜底流水线：对每张图片进行底部安全填充、OCR 文本行提取与 LLM 整理重构。"""
    engine = ocr_engine_label()
    total = len(image_paths)
    ocr_log(f"agenda_ocr_fallback start engine={engine} images={total}")
    parts: list[str] = []

    for idx, img_p in enumerate(image_paths, 1):
        path_str = str(img_p)
        padded_path: str | None = None
        try:
            padded_path = pad_image_bottom(path_str, pad_px=100)
            actual_path = padded_path or path_str
            lines = ocr_image_lines(actual_path, enable_page_chrome=False, for_agenda=True) or []
            ocr_log(f"agenda_ocr_fallback item ok {idx}/{total} lines={len(lines)} file={Path(path_str).name}")
            if lines:
                md = reconstruct_agenda_markdown(lines, candidate_speakers=candidate_speakers).strip()
                if md:
                    parts.append(md)
        except Exception as exc:  # noqa: BLE001
            ocr_log(f"agenda_ocr_fallback item fail {idx}/{total} file={Path(path_str).name} err={exc}")
            parts.append(f"（议程单图片 {Path(path_str).name} OCR 失败：{exc}）")
        finally:
            if padded_path:
                try:
                    os.unlink(padded_path)
                except OSError:
                    pass

    ocr_text = "\n\n".join(part for part in parts if part).strip()
    ocr_log(f"agenda_ocr_fallback done total={total} chars={len(ocr_text)}")

    plan = parse_agenda_text(ocr_text, candidate_speakers=candidate_speakers) if ocr_text else None
    return plan, ocr_text


def extract_agenda_from_image_docs(
    user_id: str = "",
    image_docs: list[str] | None = None,
    transcript: str = "",
    candidate_speakers: list[str] | set[str] | None = None,
    image_paths: list[Path | str] | None = None,
    vlm_client: AgendaVisionClient | None = None,
) -> tuple[AgendaPlan | None, str]:
    """从议程图片中抽取结构化议程（主通道优先 VLM 视觉大模型，重试 3 次失败则降级传统 OCR 兜底）。

    Args:
        user_id: 当前用户 ID（用于解析 data 路径）
        image_docs: 图片文件名列表（如 ["agenda.png"]）
        transcript: 会议语音转写文本（用于人名校对）
        candidate_speakers: 候选发言人列表/集合
        image_paths: 直接传入的图片路径列表（若传入则优先使用）
        vlm_client: 外部注入的视觉客户端（供单元测试 Mock 使用）

    Returns:
        (plan, markdown_text): 返回解析出的强类型 AgendaPlan 对象与规范 Markdown 议程文本。
    """
    # 1. 说话人候选集合提取
    cand_spk = list(candidate_speakers) if candidate_speakers else []
    if not cand_spk and transcript:
        cand_spk = extract_speakers_from_transcript(transcript)

    # 2. 解析图片物理路径
    resolved_paths: list[Path] = []
    if image_paths:
        resolved_paths = [Path(p) for p in image_paths if Path(p).exists()]
    elif image_docs:
        for name in image_docs:
            p = resolve_image_doc_path(user_id, name)
            if p.exists():
                resolved_paths.append(p)

    if not resolved_paths:
        logger.warning("[AGENDA_VISION] 未找到有效的待处理图片文件 (docs=%s)", image_docs)
        return None, ""

    # 3. 【主通道】：优先调用内部视觉多模态大模型服务（内置最多 3 次重试）
    client = vlm_client or AgendaVisionClient()
    vlm_plans: list[AgendaPlan] = []

    for img_p in resolved_paths:
        logger.info("[AGENDA_VISION] 尝试通过视觉大模型抽取议程: %s", img_p.name)
        vlm_res = client.extract_agenda(img_p, max_retries=3)
        if vlm_res and isinstance(vlm_res, dict) and vlm_res.get("agenda_items"):
            single_plan = vision_json_to_agenda_plan(
                vlm_res,
                transcript=transcript,
                candidate_speakers=cand_spk,
            )
            if single_plan.items:
                vlm_plans.append(single_plan)

    # 若视觉接口提取成功（包含有效实质议题）
    if vlm_plans:
        # 合并多图结果
        merged_meta = vlm_plans[0].meta
        merged_items: list[AgendaItemParsed] = []
        all_attendees: list[str] = []
        for p in vlm_plans:
            merged_items.extend(p.items)
            if p.meta.attendees:
                all_attendees.extend(clean_person_names(p.meta.attendees))

        if all_attendees:
            # 去重保留原有顺序
            seen = set()
            dedup_attendees = [a for a in all_attendees if not (a in seen or seen.add(a))]
            merged_meta.attendees = "；".join(dedup_attendees)

        # 重新规整序号
        for idx, it in enumerate(merged_items, 1):
            it.seq = f"{idx:02d}"

        final_plan = AgendaPlan(meta=merged_meta, items=merged_items)
        agenda_md = agenda_plan_to_markdown(final_plan)

        # 写入解析缓存，使得下游调用 parse_agenda_text 时直接命中内存对象
        _PARSED_AGENDA_RAW_CACHE[agenda_md] = copy.deepcopy(final_plan)
        save_agenda_ocr_debug_snapshot(agenda_md, prefix="vlm_agenda")

        logger.info(
            "[AGENDA_VISION] 视觉大模型抽取成功，共解析 %d 项实质议题",
            len(final_plan.items),
        )
        return final_plan, agenda_md

    # 4. 【兜底通道】：视觉模型 3 次重试均失败或无议题返回，平滑降级至传统 OCR 流程
    logger.warning(
        "[AGENDA_VISION] 视觉大模型抽取未产出有效议程，自动无缝降级至传统 OCR 兜底通道..."
    )
    fallback_plan, fallback_md = ocr_fallback_single_agenda_doc(
        image_paths=resolved_paths,
        candidate_speakers=cand_spk,
    )
    if fallback_md:
        save_agenda_ocr_debug_snapshot(fallback_md, prefix="ocr_fallback_agenda")

    return fallback_plan, fallback_md
