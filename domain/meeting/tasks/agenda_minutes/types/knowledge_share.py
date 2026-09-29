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
    )

    guide = PillarGuide(
        target_and_audience=(
            "交代技术或业务分享的主题背景、面向听众对象以及期望听众掌握的技能与认知提升；"
            "指出本次分享聚焦的技术层级与应用场景。"
        ),
        content_and_evidence=(
            "提炼深层技术原理推导、真实生产避坑案例与关键代码/配置架构；"
            "列举最佳实践的对比收益数据与实际运行约束条件。"
        ),
        process_and_interaction=(
            "记录听众在实际项目落地中遇到的疑难提问与主讲专家的权威答疑；"
            "精选体现技术深度的代表性互动实录。"
        ),
        conclusion_and_status=(
            "用清晰凝练的自然语言提炼 3~5 条最硬核的实战指导思想与核心认知要点（Takeaway）；"
            "交代相关技术在团队内的推广建议或适用红线。"
        ),
        action_items=(
            "输出课件代码资料归档、试点项目落地或课后答疑跟进安排；"
            "若本次纯为培训赋能无后继任务，注明暂无额外待办。"
        ),
    )
