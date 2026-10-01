"""agenda_extractor.py -- 议程专用轻量 OCR 结构化提纯器。

核心职责：
1. 替代通用的“笔记整理器”提示词，提供议程专用的 Prompt，将 OCR 原始文字碎片重构为标准 Markdown 会议议程单。
2. 完整性铁律：100% 完整保留每一个实质性技术/业务/学术议题，严禁合并或截断遗漏。
3. 杂质降噪：自动识别并剔除集合乘车、签到领资料、开幕致辞/合影、茶歇用餐、漫步参观、会务通知与联系电话等非研讨环节。
4. 广义角色归一化：将“组织主席”、“大会主席”、“执行主席”、“会议主持”、“评委”、“Session Chair”等归一化为全程与会人/主持人。
5. 姓名清洗：自动剥离教授、研究员、博士、主任、专家、老师等职称尊称头衔。
6. 版面感知预处理：识别侧边栏装饰，水平聚类保留列间距，杜绝单元格粘连。
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from infra.ocr.engines import get_llm_client
from .agenda_parser import extract_speakers_from_transcript

logger = logging.getLogger("agentflow.agenda_extractor")

AGENDA_RECONSTRUCT_SYSTEM_PROMPT = """你是「会议日程与议程结构化提纯专家」。你的任务是将从图片 OCR 识别出的文字碎片，整理为一份高保真、结构标准的 Markdown 会议议程单。

【必须遵循的核心准则】：
1. 【100% 完整性铁律（严禁遗漏任何议题，特别是末尾议题）】：
   - 必须按图片出现的顺序，逐一完整保留所有实质性的技术审议、方案汇报、学术报告或产品发布议题。
   - 【时间段/技术主题驱动】：表格中的议题通常按时间段（如 09:00-09:30、09:30-10:00 等）或技术/学术/业务主题逐行排列。
   - ★【严禁因缺少序号而丢弃】：即使某些行没有 OCR 出开头的序号数字（如只有 1，缺少 2、3、4），或者排在表格最末尾，只要出现独立的时间段或技术审议主题，就必须严格输出对应的独立表格行！
   - ★【严格对齐行数】：文本中有多少个独立的研讨/汇报时间段或技术主题，表格就必须输出多少行，绝对不准提前截断！
   - 严禁合并议题！严禁删减议题！严禁输出省略号“...”或“等”！

2. 【过滤纯事务性后勤杂质（降噪），保留核心研讨/仪式议题】：
   - 必须自动剔除纯事务性、后勤类环节，不得将它们列入议题表格：
     * 集合、乘车、签到、领取资料；
     * 茶歇交流 (Tea Break)、午餐、晚餐、宴会；
     * 漫步、参观走访；
     * 会务组联系方式、电话、邮箱、腾讯会议链接、扫码关注公众号/二维码。
   - 【核心议程保留铁律】：在领导座谈会、专题交流会、表彰仪式等会议中，若「领导致辞/主旨讲话」、「互动交流/自由交流/问答环节」、「任务令签署与授予/签约仪式」、「全员合影/合影留念」作为独立议程项列出，属于该会议的核心实质性内容，必须 100% 完整保留在表格中，严禁将其视为后勤杂质而随意丢弃！

3. 【广义角色归一化与人员隔离（杜绝混淆与吞并）】：
   - 识别全局角色：将会议组织者与主持人（如“组织主席”、“大会主席”、“执行主席”、“会议主持”、“评委”、“Session Chair”等）统一列入元数据中，格式：
     - **全程与会人/主持人**：张三；李四；王五
     （姓名之间用中文分号“；”分隔）
   - 识别分段列席人，若有则单独换行输出：
     - **分段列席人**：赵六；孙七
   - ★【严禁将末尾议题的主讲人当做分段列席人吞并】：每个议题行对应的汇报人/主讲人必须严格填入表格对应行的「汇报人/主讲人」列！严禁因为这些名字出现在了前文或与会人员名单中，就跳过该议题！必须先完整输出所有表格行，再在表格下方输出与会/列席人！
   - ★ 绝对禁止将“全程与会人”和“分段列席人”连在同一行！必须严格独立换行！

4. 【主讲人/汇报人姓名清洗】：
   - 从议题中提取纯净的真实姓名，剥离“教授”、“副教授”、“研究员”、“博士”、“院士”、“主任”、“专家”、“老师”、“总”、“工程师”等职称与头衔。
     例如：“张三教授” -> “张三”；“李四研究员” -> “李四”；“王五博士” -> “王五”。
   - 若某议题有多个汇报人，用中文分号“；”分隔。

5. 【标准 Markdown 表格输出】：
   必须使用标准 Markdown 管道表格输出议程，包含表头：
   | 序号 | 议题名称 | 汇报人/主讲人 | 预计时长 |
   | :--- | :--- | :--- | :--- |
   | 01 | ... | ... | ... |
   - 序号统一补零格式（01, 02, 03...），按顺序递增；
   - 议题名称保留完整的系统名、版本号或报告主题；
   - 预计时长提取如 "25min"、"09:30-10:00" 等，未知可写 "-"。

直接输出 Markdown 文本，不要用 ```markdown ``` 代码块包裹，不要添加任何开场白或结束语。
"""


def _clean_md_fences(text: str) -> str:
    """去除 Markdown 代码块包裹。"""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:markdown|md|json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _bbox_rect(bbox: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in bbox]
    ys = [float(p[1]) for p in bbox]
    return min(xs), min(ys), max(xs), max(ys)


def prepare_agenda_ocr_prompt_text(
    lines: list[dict[str, Any]],
    raw_text: str = "",
) -> str:
    """前置版面优化：剔除左侧装饰性侧栏标签，按行水平聚类保留列间距，杜绝单元格粘连。"""
    if not lines:
        return (raw_text or "").strip()

    usable = [item for item in lines if item.get("text") and str(item.get("text")).strip()]
    if not usable:
        return (raw_text or "").strip()

    # 1. 如果有 bbox，检测是否包含表格区域并执行侧栏清洗与水平分列排版
    has_bbox = any(it.get("bbox") for it in usable)
    if not has_bbox:
        return "\n".join(str(it["text"]).strip() for it in usable)

    # 过滤左侧（x < 150）且内容为侧栏装饰性标题的碎片，防止其插入数据行中间
    sidebar_noise = {
        "会议议题",
        "agenda",
        "agendas",
        "议题(agendas)",
        "材料(materials)",
    }
    filtered: list[dict[str, Any]] = []
    for it in usable:
        bbox = it.get("bbox")
        txt = str(it.get("text") or "").strip()
        if bbox:
            l, t, r, b = _bbox_rect(bbox)
            if l < 150 and txt.lower() in sidebar_noise:
                continue
        filtered.append(it)

    # 2. 计算中位行高
    heights = []
    for it in filtered:
        if it.get("bbox"):
            l, t, r, b = _bbox_rect(it["bbox"])
            heights.append(b - t)
    heights.sort()
    median_h = heights[len(heights) // 2] if heights else 20.0

    # 3. 按垂直中心 y 排序并做同水平行聚类
    sorted_items = sorted(
        filtered,
        key=lambda it: (
            ((_bbox_rect(it["bbox"])[1] + _bbox_rect(it["bbox"])[3]) / 2, _bbox_rect(it["bbox"])[0])
            if it.get("bbox")
            else (0, 0)
        ),
    )

    rows: list[list[dict[str, Any]]] = []
    for it in sorted_items:
        if not it.get("bbox"):
            rows.append([it])
            continue
        l, t, r, b = _bbox_rect(it["bbox"])
        cy = (t + b) / 2
        if rows and rows[-1][0].get("bbox"):
            prev_l, prev_t, prev_r, prev_b = _bbox_rect(rows[-1][-1]["bbox"])
            prev_cy = (prev_t + prev_b) / 2
            if abs(cy - prev_cy) <= median_h * 0.55:
                rows[-1].append(it)
                continue
        rows.append([it])

    # 4. 组装行文本：同一行内多个单元格按从左到右排序，用 "  |  " 明确列分隔
    formatted_lines: list[str] = []
    for row in rows:
        if len(row) == 1:
            formatted_lines.append(str(row[0].get("text") or "").strip())
        else:
            row.sort(key=lambda it: _bbox_rect(it["bbox"])[0] if it.get("bbox") else 0)
            row_str = "  |  ".join(str(it.get("text") or "").strip() for it in row if it.get("text"))
            formatted_lines.append(row_str)

    return "\n".join(formatted_lines).strip()


def reconstruct_agenda_markdown(
    lines: list[dict[str, Any]],
    raw_text: str = "",
    candidate_speakers: list[str] | set[str] | None = None,
) -> str:
    """同步入口：调用 LLM 将 OCR 识别行结构化重构为标准化 Markdown 议程单。"""
    if not lines and not raw_text:
        return ""

    user_content = prepare_agenda_ocr_prompt_text(lines, raw_text)

    if not user_content:
        return ""

    client = get_llm_client()
    if client is None:
        logger.warning("LLM client 不可用，降级直接拼接 OCR 文本")
        return user_content

    system_prompt = AGENDA_RECONSTRUCT_SYSTEM_PROMPT
    if candidate_speakers:
        cand_list = [str(s).strip() for s in candidate_speakers if str(s).strip()]
        if cand_list:
            speaker_list_str = "、".join(cand_list[:60])
            system_prompt += (
                f"\n\n【参考与会/发言人名单（用于校验和校对 OCR 识别文本中的形似错别字、异体字）】：\n"
                f"{speaker_list_str}\n"
                f"★ 请在输出的议程表格「汇报人/主讲人」及「全程与会人/主持人」中，优先以本参考名单中的准确姓名对 OCR 识别文本中的形似错别字、异体字进行校正对齐！"
            )

    async def _call() -> str:
        return await client.text(
            system_prompt,
            user_content,
            label="agenda_minutes/ocr_reconstruct",
            max_tokens=2500,
        )

    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(lambda: asyncio.run(_call())).result()
            else:
                result = loop.run_until_complete(_call())
        except RuntimeError:
            result = asyncio.run(_call())

        cleaned = _clean_md_fences(result)
        if cleaned:
            logger.info("reconstruct_agenda_markdown succeeded, length=%d", len(cleaned))
            return cleaned
    except Exception as exc:  # noqa: BLE001
        logger.warning("reconstruct_agenda_markdown failed: %s, fallback to raw lines", exc)

    return user_content


__all__ = [
    "AGENDA_RECONSTRUCT_SYSTEM_PROMPT",
    "extract_speakers_from_transcript",
    "prepare_agenda_ocr_prompt_text",
    "reconstruct_agenda_markdown",
]
