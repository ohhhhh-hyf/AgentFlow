from __future__ import annotations

from .models import FinalReport


def _print_action(item) -> None:
    task = item["task"]
    details = []
    if item.get("owner"):
        details.append(f"负责人：{item['owner']}")
    if item.get("deadline"):
        details.append(f"截止时间：{item['deadline']}")
    suffix = f"（{'；'.join(details)}）" if details else ""
    print(f"- {task}{suffix}")


def print_result(result: FinalReport) -> None:
    """只展示最终用户视角纪要和本人待办。"""
    print("\n【用户视角会议纪要】")
    for item in result.personalized_minutes:
        print(f"- {item}")

    print("\n【待办事项】")
    if not result.action_items:
        print("- 暂无明确待办")
        return
    for item in result.action_items:
        _print_action(item)
