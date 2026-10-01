"""review_selection.py -- 2. 评审选型型幕后导师。

核心目的：方案评估与技术选型。
典型场景：架构方案比选、技术栈选型、供应商评选、原型评测。
"""
from __future__ import annotations

from .base import BaseAgendaTypeSpec, PillarGuide


class ReviewSelectionTypeSpec(BaseAgendaTypeSpec):
    type_id = "review_selection"
    type_name = "评审选型型"
    core_purpose = "方案评估与技术选型"
    core_output = "评审意见、短名单、推荐方案"
    keywords = (
        "选型",
        "方案评审",
        "架构评审",
        "供应商评审",
        "比选",
        "技术评估",
        "POC",
        "选型评审",
        "技术路线",
        "方案论证",
    )

    guide = PillarGuide(
        background_and_goals=(
            "1~2 句话说明候选方案选型背景，以及要决定的技术路线或供应商范围。"
        ),
        core_content=(
            "分点陈述各候选方案在核心指标、成本、生态兼容性上的评测对比数据，"
            "以及评委专家针对各方案优劣势的质询与答辩。"
        ),
        core_insights=(
            "明确评审团最终选型的拍板决策与推荐路线，并注明采纳该方案的前提条件。"
        ),
        action_items=(
            "表格列出选型落地推进责任人、试点接入排期与验证节点。"
        ),
    )
