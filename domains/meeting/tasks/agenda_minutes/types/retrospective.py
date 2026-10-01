"""retrospective.py -- 6. 复盘归因型幕后导师。

核心目的：事故复盘、根因剖析与改进防重发。
典型场景：重大事故复盘会、项目结项复盘、质量复盘、业务运营复盘。
"""
from __future__ import annotations

from .base import BaseAgendaTypeSpec, PillarGuide


class RetrospectiveTypeSpec(BaseAgendaTypeSpec):
    type_id = "retrospective"
    type_name = "复盘归因型"
    core_purpose = "事故复盘、根因剖析与改进防重发"
    core_output = "根因结论、改进主题与防重发规范"
    keywords = (
        "复盘",
        "事故",
        "故障",
        "复盘会",
        "根因分析",
        "5-whys",
        "反思会",
        "复盘总结",
        "复盘研讨",
    )

    guide = PillarGuide(
        background_and_goals=(
            "1~2 句话说明本次复盘的事件或项目背景，以及复盘的目标。"
        ),
        core_content=(
            "分点还原关键时间线与客观事实数据，剖析问题产生的根因（技术缺陷、流程漏洞等），"
            "以及责任团队的检讨与讨论。"
        ),
        core_insights=(
            "提炼团队在此次复盘中沉淀的核心教训、工程红线与系统防护机制。"
        ),
        action_items=(
            "表格列出防复发改进措施的责任人、交付物与闭环时间。"
        ),
    )
