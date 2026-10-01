"""info_sync.py -- 5. 信息同步型幕后导师。

核心目的：例行同步进展与暴露风险阻碍。
典型场景：周会、站会、项目例会、双周同步会。
"""
from __future__ import annotations

from .base import BaseAgendaTypeSpec, PillarGuide


class InfoSyncTypeSpec(BaseAgendaTypeSpec):
    type_id = "info_sync"
    type_name = "信息同步型"
    core_purpose = "例行同步进展与暴露风险阻碍"
    core_output = "知会结论、阻塞排障、需决策项"
    keywords = (
        "例会",
        "周会",
        "站会",
        "同步会",
        "进度同步",
        "双周会",
        "晨会",
        "月度例会",
        "项目同步",
    )

    guide = PillarGuide(
        background_and_goals=(
            "1~2 句话说明本周期计划交付的里程碑目标，以及本次例会复盘与同步的重点。"
        ),
        core_content=(
            "分点列出实际完成情况（达成率、关键成果数据），以及延期事项的客观卡点原因（依赖阻塞、驱动适配慢等）。"
        ),
        core_insights=(
            "写明主管/负责人对当前进展的定调评价（大盘状态判定），以及现场协调资源支持的裁决。"
        ),
        action_items=(
            "表格列出下周期必保的攻坚任务、责任人与完成时间。"
        ),
    )
