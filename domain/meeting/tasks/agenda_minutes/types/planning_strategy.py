"""planning_strategy.py -- 3. 规划策略型幕后导师。

核心目的：定方向、排优先级与资源取舍。
典型场景：业务战略会、季度规划、年度研发计划、产品路线图排期。
"""
from __future__ import annotations

from .base import BaseAgendaTypeSpec, PillarGuide


class PlanningStrategyTypeSpec(BaseAgendaTypeSpec):
    type_id = "planning_strategy"
    type_name = "规划策略型"
    core_purpose = "定方向、排优先级与资源取舍"
    core_output = "路线图、目标、预算、优先级"
    keywords = (
        "规划",
        "战略",
        "季度规划",
        "年度规划",
        "路线图",
        "roadmap",
        "业务规划",
        "战略会",
        "规划会",
        "计划排期",
    )

    guide = PillarGuide(
        background_and_goals=(
            "1~2 句话说明本阶段战略规划背景，以及要敲定的战略定位、关键战役与目标范围。"
        ),
        core_content=(
            "分点陈述业务现状事实、竞品与目标测算数据、关键战役路径规划，以及关于资源投入产出比、实施优先级的讨论。"
        ),
        core_insights=(
            "提炼战略规划核心方向定调、资源分配原则与风险防控底线。"
        ),
        action_items=(
            "表格列出责任团队承接战役拆解的责任人、工作项与阶段里程碑时间。"
        ),
    )
