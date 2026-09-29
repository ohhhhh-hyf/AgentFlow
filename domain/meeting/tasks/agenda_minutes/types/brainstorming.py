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
        target_and_audience=(
            "交代本次发散研讨要攻坚的创新命题、业务挑战与探索边界；"
            "指明参与研讨的跨领域专家团队与工作坊目标。"
        ),
        content_and_evidence=(
            "提炼启发构想的行业标杆案例、前沿技术动态、用户深层诉求与既有尝试教训；"
            "指出创新方案需满足的基本约束边界。"
        ),
        process_and_interaction=(
            "记录多元观点的自由碰撞、思路延伸、技术可行性辩驳；"
            "提炼构想分类聚合、打分评估与优劣势横评的过程。"
        ),
        conclusion_and_status=(
            "用自然语言明确总结现场最终收敛出来的 2~3 个最具潜力的创新构想或核心突破方向；"
            "阐明为何优先聚焦该方向及淘汰其他构想的考量。"
        ),
        action_items=(
            "输出开展轻量原型开发（Demo）、用户调研或可行性深度预研的具体责任人与产出时限；"
            "若本次仅作探索认知沉淀无下阶段动作，注明暂无额外待办。"
        ),
    )
