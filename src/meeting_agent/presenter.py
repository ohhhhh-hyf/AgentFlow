from __future__ import annotations

from .models import FinalReport


def _friendly_label(label: str) -> str:
    """把 'AgentName｜中文说明' 收成更易读的中文标题。"""
    if "｜" in label:
        return label.split("｜", 1)[1].strip()
    if "|" in label:
        return label.split("|", 1)[1].strip()
    return label.strip()


def _section(title: str) -> None:
    print(f"── {title} ──")


def _format_action(index: int, item: dict) -> str:
    details = []
    if item.get("owner"):
        details.append(f"负责人：{item['owner']}")
    if item.get("deadline"):
        details.append(f"截止时间：{item['deadline']}")
    suffix = f"（{'；'.join(details)}）" if details else ""
    return f"{index}. {item['task']}{suffix}"


class ProgressPrinter:
    """终端进度：简洁图标 + 中文步骤名。"""

    def __init__(self) -> None:
        self.index = 0
        self.active: dict[str, int] = {}

    def __call__(self, event: str, label: str) -> None:
        title = _friendly_label(label)
        if event == "start":
            self.index += 1
            self.active[label] = self.index
            print(f"· {self.index:02d} {title}", flush=True)
            return

        number = self.active.get(label, self.index)
        print(f"✓ {number:02d} {title}", flush=True)


def print_result(result: FinalReport) -> None:
    """只展示最终用户视角纪要和本人待办。"""
    print()
    _section("用户视角会议纪要")
    minutes = (result.personalized_minutes or "").strip()
    print(minutes if minutes else "（暂无内容）")

    _section("待办事项")
    if not result.action_items:
        print("暂无明确待办")
    else:
        for index, item in enumerate(result.action_items, start=1):
            print(_format_action(index, item))

    if result.quality_warning:
        print(f"⚠ {result.quality_warning}")
