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
        target_and_audience=(
            "交代向业务方与高管层汇报中长期规划、争取关键资源与确定产品方向的核心诉求；"
            "指明规划覆盖的时间窗口与服务的目标群体。"
        ),
        content_and_evidence=(
            "提炼支撑规划制定的事实依据：业务现状问题、竞品动向、目标量化数据、预期ROI测算；"
            "交代关键交付窗口与前置资源/人力预算依赖。"
        ),
        process_and_interaction=(
            "记录围绕目标可行性、优先级先后次序、投入产出比与资源短板的深入研讨与利益博弈；"
            "记录各部门管理层对排期延后或功能裁剪的讨论与协调。"
        ),
        conclusion_and_status=(
            "用自然语言清晰说明本次规划最终敲定的核心方向与关键里程碑节点；"
            "明确指出经权衡后决定放弃、暂缓或裁剪的非核心诉求；说明战略共识是否达成。"
        ),
        action_items=(
            "输出各模块牵头人分阶段推进的里程碑任务、资源落实计划与定期复盘节点；"
            "若规划已定调且按既定节奏执行无额外待办，注明暂无额外待办。"
        ),
    )
