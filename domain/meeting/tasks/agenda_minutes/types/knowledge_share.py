"""knowledge_share.py -- 9. 知识分享型幕后导师。

核心目的：传递专业知识与启发实战应用。
典型场景：技术沙龙、业务培训、专家讲座、最佳实践分享会。
"""
from __future__ import annotations

from .base import BaseAgendaTypeSpec, PillarGuide


class KnowledgeShareTypeSpec(BaseAgendaTypeSpec):
    type_id = "knowledge_share"
    type_name = "知识分享型"
    core_purpose = "传递专业知识与启发实战应用"
    core_output = "核心认知Takeaway、实战Q&A、沉淀归档"
    keywords = (
        "分享",
        "培训",
        "技术沙龙",
        "讲座",
        "公开课",
        "经验分享",
        "研读会",
        "业务分享",
        "最佳实践",
        "交流会",
        "座谈会",
        "年会",
        "学术年会",
        "交流研讨",
        "前沿讲座",
        "专家论坛",
        "致辞",
        "特邀报告",
    )

    guide = PillarGuide(
        background_and_goals=(
            "1~2 句话说明主讲人针对什么技术/业务瓶颈与应用场景，分享什么演进方案与实践。"
        ),
        core_content=(
            "分点讲清底层技术原理推导、代码/配置架构、实测对比数据（如 WER 下降、时延、功耗），"
            "以及现场学者/听众提了什么技术问题、主讲人如何回应。"
        ),
        core_insights=(
            "提炼 2~3 条关键技术启发、工程落地避坑点（Gotchas）或演进趋势，直接朴实表述。"
        ),
        action_items=(
            "纯分享交流现场已闭环、无会后行政派工，直接留空（后续不渲染第四栏）。"
        ),
    )
