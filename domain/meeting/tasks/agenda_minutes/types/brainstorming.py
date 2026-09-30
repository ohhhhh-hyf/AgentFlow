"""brainstorming.py -- 7. 创意发散型幕后导师。

核心目的：激发创新思路与收敛可行方案。
典型场景：头脑风暴会、业务工作坊、产品设计创新会、技术破局探索。
"""
from __future__ import annotations

from .base import BaseAgendaTypeSpec, PillarGuide


class BrainstormingTypeSpec(BaseAgendaTypeSpec):
    type_id = "brainstorming"
    type_name = "创意发散型"
    core_purpose = "激发创新思路与收敛可行方案"
    core_output = "短名单、优先级构想、验证假设"
    keywords = (
        "脑暴",
        "头脑风暴",
        "工作坊",
        "创新",
        "创意",
        "探索会",
        "研讨工坊",
        "发散",
        "方案征集",
    )

    guide = PillarGuide(
        background_and_goals=(
            "1~2 句话说明本次头脑风暴探讨的核心业务/技术命题与探索预期。"
        ),
        core_content=(
            "分点陈述现场提出的多元创新思路、方案可行性探讨与现场思想碰撞。"
        ),
        core_insights=(
            "提炼最具价值、最具共识的 2~3 个创新突破点或可行性探索方向。"
        ),
        action_items=(
            "表格列出进入可行性预研或原型验证的牵头人、验证目标与时间；若仅做纯探索无待办则留空。"
        ),
    )
