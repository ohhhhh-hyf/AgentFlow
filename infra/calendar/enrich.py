"""待办事项（actions）绝对时间批量解析与回填。

以 1:1 绝对对齐方式，批处理待办列表中的 deadline 字段：
- 严格保持与输入 actions 列表长度 1:1，空项在内存中秒过，零 Token 损耗；
- 杜绝穿插 null 时的下标偏移错位；
- 产出 deadline_raw（事实留存）、deadline_display（人读展示）与 deadline（标准机读时间戳）。
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Sequence

from .agent import CalendarLLMProtocol, run_deadline_agent
from .config import DEFAULT_TIMEZONE

logger = logging.getLogger("agentflow")


_SLOT_TIME_MAP = {
    "上午": "12:00:00",
    "中午": "13:00:00",
    "下午": "18:00:00",
    "下班前": "18:00:00",
    "晚上": "23:59:59",
}


def _format_display(item: Dict[str, Any]) -> Optional[str]:
    """格式化面向人类的友好展示文案。"""
    kind = str(item.get("kind") or "").strip().lower()
    start = item.get("deadline_start")
    end = item.get("deadline_end")
    base = item.get("deadline")
    slot = item.get("time_slot")

    if kind == "range" or (start and end):
        if start and end and start != end:
            return f"{start} ~ {end}"
        return str(start or end or base or "")

    if not base:
        return None

    if slot and " " not in str(base):
        return f"{base} {slot}".strip()
    return str(base)


def _format_iso_deadline(item: Dict[str, Any]) -> Optional[str]:
    """格式化标准机读 ISO 8601 时间戳（如 2026-10-30T18:00:00）。"""
    base = item.get("deadline")
    if not base:
        return None

    base_str = str(base).strip().replace("/", "-")
    slot = item.get("time_slot")

    # 1. 已经是具体日期时间：2026-10-30 15:30
    if " " in base_str:
        date_part, time_part = base_str.split(" ", 1)
        if len(time_part) == 5:  # HH:MM
            time_part = f"{time_part}:00"
        return f"{date_part}T{time_part}"

    # 2. 纯日期：2026-10-30
    if re.fullmatch(r"^\d{4}-\d{2}-\d{2}$", base_str):
        time_part = _SLOT_TIME_MAP.get(str(slot or "").strip(), "18:00:00")
        return f"{base_str}T{time_part}"

    return base_str


async def enrich_actions_deadlines(
    actions: Sequence[Dict[str, Any]],
    meeting_start_time: str,
    timezone: str = DEFAULT_TIMEZONE,
    client: Optional[CalendarLLMProtocol] = None,
    inplace: bool = False,
    use_fast_path: bool = True,
) -> List[Dict[str, Any]]:
    """在 infra/calendar 内部完整闭环实现待办时间的提取、计算与回填。

    参数:
        actions: 待办字典列表（每条含 deadline 字段）
        meeting_start_time: 会议开始时间（如 "2026-10-30 10:00:00"）
        timezone: 时区，默认 Asia/Shanghai
        client: 可选的 CalendarLLM 客户端
        inplace: 是否在原字典上原地修改，默认为 False（浅拷贝字典）
        use_fast_path: 是否开启 Fast-Path 快速规则解析（默认开启）

    返回:
        回填增强后的平铺 actions 列表
    """
    if not isinstance(actions, (list, tuple)) or not actions:
        return []

    # 拷贝生成工作副本，确保原始 actions 字典不被污染
    target_actions: List[Dict[str, Any]] = [
        dict(a) for a in actions
    ] if not inplace else list(actions)

    # 1. 严格 1:1 提取 deadline 字符串，遇到空值提取为空串以保持数组长度恒等
    raw_texts = [str(a.get("deadline") or "").strip() for a in target_actions]

    t0 = time.time()
    # 2. 边界检查：若全场待办全无 deadline，或开会时间为空，0ms 短路返回
    if not any(raw_texts) or not str(meeting_start_time or "").strip():
        for action in target_actions:
            action["deadline_raw"] = action.get("deadline") or None
            action["deadline_display"] = action.get("deadline") or None
            action["deadline"] = None
        return target_actions

    # 3. 批量推导（Calendar Agent 内部对空文本 0ms 秒过，返回结果长度严格等于 len(raw_texts)）
    cal_res = await run_deadline_agent(
        meeting_start_time=meeting_start_time,
        texts=raw_texts,
        timezone=timezone,
        client=client,
        use_fast_path=use_fast_path,
    )
    results = cal_res.get("results") or []

    # 4. 1:1 零偏移回填
    for action, res in zip(target_actions, results):
        raw_val = action.get("deadline") or None
        if res and not res.get("error") and res.get("deadline"):
            action["deadline_raw"] = res.get("raw") or raw_val
            action["deadline_display"] = _format_display(res)
            action["deadline"] = _format_iso_deadline(res)
        else:
            # 解析失败、无法推导或原本为 null
            action["deadline_raw"] = raw_val
            action["deadline_display"] = raw_val
            action["deadline"] = None

    dur = time.time() - t0
    resolved_cnt = sum(1 for a in target_actions if a.get("deadline"))
    logger.info(
        "[calendar:enrich:done] dur=%.2fs resolved=%d raw_kept=%d",
        dur,
        resolved_cnt,
        len(target_actions) - resolved_cnt,
    )
    return target_actions


__all__ = ["enrich_actions_deadlines"]
