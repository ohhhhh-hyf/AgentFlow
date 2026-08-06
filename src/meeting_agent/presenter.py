from __future__ import annotations

import logging

from .models import FinalReport

logger = logging.getLogger(__name__)


def _section(title: str) -> None:
    logger.info("── %s ──", title)


def _format_action(index: int, item: dict) -> str:
    details = []
    if item.get("owner"):
        details.append(f"负责人：{item['owner']}")
    if item.get("deadline"):
        details.append(f"截止时间：{item['deadline']}")
    suffix = f"（{'；'.join(details)}）" if details else ""
    return f"{index}. {item['task']}{suffix}"




def print_result(result: FinalReport, *, objective_perspective: bool = False) -> None:
    """展示最终纪要和待办；客观模式使用全员口径标题。"""
    logger.info("")  # 空行分隔
    if objective_perspective:
        _section("客观会议纪要")
    else:
        _section("用户视角会议纪要")
    minutes = (result.personalized_minutes or "").strip()
    logger.info(minutes if minutes else "（暂无内容）")

    if objective_perspective:
        _section("客观待办事项（全员）")
    else:
        _section("待办事项")
    if not result.action_items:
        logger.info("暂无明确待办")
    else:
        for index, item in enumerate(result.action_items, start=1):
            logger.info(_format_action(index, item))

    if result.quality_warning:
        logger.warning("⚠ %s", result.quality_warning)
