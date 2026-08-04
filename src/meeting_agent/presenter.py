from __future__ import annotations

import logging

from .models import FinalReport

logger = logging.getLogger(__name__)


def _friendly_label(label: str) -> str:
    """把 'AgentName｜中文说明' 收成更易读的中文标题。"""
    if "｜" in label:
        return label.split("｜", 1)[1].strip()
    if "|" in label:
        return label.split("|", 1)[1].strip()
    return label.strip()


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


class ProgressPrinter:
    """终端进度：简洁图标 + 中文步骤名。

    实现 ProgressHandler 协议，注入到 MeetingAgentSystem。
    """

    def __init__(self) -> None:
        self.index = 0
        self.active: dict[str, int] = {}

    def __call__(self, event: str, label: str) -> None:
        title = _friendly_label(label)
        if event == "start":
            self.index += 1
            self.active[label] = self.index
            logger.info("· %02d %s", self.index, title)
            return

        number = self.active.get(label, self.index)
        logger.info("✓ %02d %s", number, title)


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
