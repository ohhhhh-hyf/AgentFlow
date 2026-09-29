"""release_broadcast.py -- 8. 发布传播型幕后导师。

核心目的：统一对外口径与明确宣发节奏。
典型场景：新产品发布会、对外通气会、政策宣贯会、媒体公关说明会。
"""
from __future__ import annotations

from .base import BaseAgendaTypeSpec, PillarGuide


class ReleaseBroadcastTypeSpec(BaseAgendaTypeSpec):
    type_id = "release_broadcast"
    type_name = "发布传播型"
    core_purpose = "统一对外口径与明确宣发节奏"
    core_output = "标准发布口径、关键核心信息、外发排期"
    keywords = (
        "发布会",
        "宣讲",
        "媒体沟通",
        "对外公告",
        "宣贯",
        "通气会",
        "产品发布",
        "新闻通气",
    )

    guide = PillarGuide(
        target_and_audience=(
            "交代产品或重大事项对外/全员宣贯的核心主旨、目标传播受众（客户、媒体、全员）与发布场合；"
            "明确本次对外传播的范围边界。"
        ),
        content_and_evidence=(
            "提炼产品或政策的核心卖点与价值主张；"
            "列举对外公布的权威数据支撑、技术创新点与关键时间表。"
        ),
        process_and_interaction=(
            "记录内部针对外部可能关注的敏感点、尖锐质疑进行的问答推敲与口径推演；"
            "提炼针对市场与公关风险的防范研讨。"
        ),
        conclusion_and_status=(
            "逐条梳理明确的标准对外公开宣传口径；"
            "明确写出严禁对外透露的涉密信息红线与统一应答话术标准。"
        ),
        action_items=(
            "列出新闻通稿审定、宣发物料制作、投放渠道排期及各渠道对接责任人与截稿节点；"
            "若通稿已统一签发无额外待办，注明暂无额外待办。"
        ),
    )
