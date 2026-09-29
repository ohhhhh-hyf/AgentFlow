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
        target_and_audience=(
            "交代向团队成员或项目干系人例行同步进展、暴露风险并协调资源的意图；"
            "指明本次同步涵盖的项目模块或子业务线。"
        ),
        content_and_evidence=(
            "提炼本周期量化交付进展：已完成任务数、关键指标达标情况；"
            "指出延期任务偏差、外部依赖卡点与客观资源短板事实。"
        ),
        process_and_interaction=(
            "记录针对延期或阻塞问题的简明质询与澄清问答；"
            "提炼跨模块资源协助请求与现场调度安排。"
        ),
        conclusion_and_status=(
            "用自然语言说明团队已知晓的关键态势；"
            "明确指出是否存在阻塞性重大隐患或项目整体进度偏差状态。"
        ),
        action_items=(
            "输出清除具体阻碍问题、拉平进度的责任人、具体攻关动作与截止时限；"
            "若整体顺利推进无新增待办，注明暂无额外待办。"
        ),
    )
