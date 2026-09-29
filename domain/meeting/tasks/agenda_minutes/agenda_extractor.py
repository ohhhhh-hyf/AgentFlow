"""agenda_extractor.py -- 议程专用轻量 OCR 结构化提纯器。

核心职责：
1. 替代通用的“笔记整理器”提示词，提供议程专用的 Prompt，将 OCR 原始文字碎片重构为标准 Markdown 会议议程单。
2. 完整性铁律：100% 完整保留每一个实质性技术/业务/学术议题，严禁合并或截断遗漏。
3. 杂质降噪：自动识别并剔除集合乘车、签到领资料、开幕致辞/合影、茶歇用餐、漫步参观、会务通知与联系电话等非研讨环节。
4. 广义角色归一化：将“组织主席”、“大会主席”、“执行主席”、“会议主持”、“评委”、“Session Chair”等归一化为全程与会人/主持人。
5. 姓名清洗：自动剥离教授、研究员、博士、主任、专家、老师等职称尊称头衔。
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from tools.ocr.engines import get_llm_client

logger = logging.getLogger("agentflow.agenda_extractor")

AGENDA_RECONSTRUCT_SYSTEM_PROMPT = """你是「会议日程与议程结构化提纯专家」。你的任务是将从图片 OCR 识别出的文字碎片，整理为一份高保真、结构标准的 Markdown 会议议程单。

【必须遵循的核心准则】：
1. 【100% 完整性铁律（严禁遗漏任何议题）】：
   - 必须按图片出现的顺序，逐一完整保留所有实质性的技术审议、方案汇报、学术报告或产品发布议题。
   - 严禁合并议题！严禁删减议题！严禁输出省略号“...”或“等”！
   - 图片中有多少个研讨/汇报议题，表格就必须输出多少行。

2. 【过滤事务性非研讨杂质（降噪）】：
   - 必须自动剔除事务性、后勤类环节，不得将它们列入议题表格：
     * 集合、乘车、签到、领取资料；
     * 开幕致辞、领导致辞、合影留念；
     * 茶歇交流 (Tea Break)、午餐、晚餐、宴会；
     * 漫步、参观走访、闭幕颁奖；
     * 会务组联系方式、电话、邮箱、腾讯会议链接、扫码关注公众号/二维码。
   - 表格中只保留真正有汇报人、有具体技术/业务研讨主题的议题（如“特邀报告”、“版本发布评审”、“专项进度汇报”等）。

3. 【广义角色归一化与人员隔离（杜绝混淆）】：
   - 识别全局角色：将会议组织者与主持人（如“组织主席”、“大会主席”、“执行主席”、“会议主持”、“评委”、“Session Chair”等）统一列入元数据中，格式：
     - **全程与会人/主持人**：张三；李四；王五
     （姓名之间用中文分号“；”分隔）
   - 识别分段列席人，若有则单独换行输出：
     - **分段列席人**：赵六；孙七
   - ★ 绝对禁止将“全程与会人”和“分段列席人”连在同一行！必须严格独立换行！

4. 【主讲人/汇报人姓名清洗】：
   - 从议题中提取纯净的真实姓名，剥离“教授”、“副教授”、“研究员”、“博士”、“院士”、“主任”、“专家”、“老师”、“总”、“工程师”等职称与头衔。
     例如：“陈景东教授” -> “陈景东”；“陶建华研究员” -> “陶建华”；“贾磊博士” -> “贾磊”。
   - 若某议题有多个汇报人，用中文分号“；”分隔。

5. 【标准 Markdown 表格输出】：
   必须使用标准 Markdown 管道表格输出议程，包含表头：
   | 序号 | 议题名称 | 汇报人/主讲人 | 预计时长 |
   | :--- | :--- | :--- | :--- |
   | 01 | ... | ... | ... |
   - 序号统一补零格式（01, 02, 03...）；
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


def reconstruct_agenda_markdown(lines: list[dict[str, Any]], raw_text: str = "") -> str:
    """同步入口：调用 LLM 将 OCR 识别行结构化重构为标准化 Markdown 议程单。"""
    if not lines and not raw_text:
        return ""

    if lines:
        content_lines = [str(l.get("text") or "").strip() for l in lines if str(l.get("text") or "").strip()]
        user_content = "\n".join(content_lines)
    else:
        user_content = raw_text.strip()

    if not user_content:
        return ""

    client = get_llm_client()
    if client is None:
        logger.warning("LLM client 不可用，降级直接拼接 OCR 文本")
        return user_content

    async def _call() -> str:
        return await client.text(
            AGENDA_RECONSTRUCT_SYSTEM_PROMPT,
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


__all__ = ["AGENDA_RECONSTRUCT_SYSTEM_PROMPT", "reconstruct_agenda_markdown"]
