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
        background_and_goals=(
            "1~2 句话说明本次全员宣导发布的新政策、战略调整或组织制度背景与面向对象。"
        ),
        core_content=(
            "分点讲清政策核心条款、关键变化点、执行生效时间以及现场针对答疑解惑的要点。"
        ),
        core_insights=(
            "强调管理层对新政策推行的核心要求与执行底线。"
        ),
        action_items=(
            "列出各部门配套细则落地、培训宣贯或对接责任人与时限。"
        ),
    )
