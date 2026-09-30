"""decision_approval.py -- 1. 决策审批型幕后导师。

核心目的：拍板放行与准入决策。
典型场景：商用版本发布、预算审批、采购立项、上线准入。
"""
from __future__ import annotations

from .base import BaseAgendaTypeSpec, PillarGuide


class DecisionApprovalTypeSpec(BaseAgendaTypeSpec):
    type_id = "decision_approval"
    type_name = "决策审批型"
    core_purpose = "拍板放行与准入决策"
    core_output = "批准/拒绝/有条件批准"
    keywords = (
        "商用发布评审",
        "商用评审",
        "商评会",
        "发布评审",
        "上线评审",
        "准入审批",
        "准入评审",
        "预算审批",
        "决策会",
        "立项审批",
        "放行",
        "商用版本发布",
        "版本发布",
        "上线发布",
    )

    guide = PillarGuide(
        background_and_goals=(
            "1~2 句话说明本次申请过会的事项（如商用准入许可、发版资格、预算批复），"
            "以及本次审查范围与明确排除项（如明确本次不涉及云端底座或历史遗留问题）。"
        ),
        core_content=(
            "分点说明方案演进细节、硬核量化达标数据（通过率、时延降低幅度、并发与SLA指标），"
            "以及把关评委提了什么疑虑（稳定性、合规、弱网表现）、汇报团队如何解答。"
        ),
        core_insights=(
            "写明委员会的最终裁决（如审议通过/有条件通过/未通过），"
            "并逐条列出上线生效的前置约束条件（如补充弱网压测报告、现网监控指标要求）。"
        ),
        action_items=(
            "表格列出落实上述约束条件的整改责任人、具体交付物与完成时限；若现场决议且无会后待办则留空。"
        ),
    )
