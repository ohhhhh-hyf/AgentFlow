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
        target_and_audience=(
            "交代提请技术委员会或专家评审组进行方案评估与路线推荐的意图；"
            "指明评估所面向的业务背景与技术边界（如限定在微服务网关选型或离线推理引擎选型）。"
        ),
        content_and_evidence=(
            "列出各备选方案（方案A vs 方案B）的架构差异与核心机制；"
            "提炼硬核评测对比数据：实测POC性能指标（吞吐量、CPU/内存占用、端到端时延）、改造成本、运维成熟度与团队技能储备。"
        ),
        process_and_interaction=(
            "提炼评审专家关于方案长期扩展性、技术债务、迁移复杂度与高可用保障的核心质询；"
            "记录各方专家观点的交锋辩论与各自主张支撑理由。"
        ),
        conclusion_and_status=(
            "用自然语言说明评审组给出的明确倾向或选型结果（推荐方案、入选方案名单）；"
            "明确指出被淘汰或暂缓方案的核心缺陷与否决原因；交代尚存的技术待决项或附带前提。"
        ),
        action_items=(
            "输出深度POC验证、补充基准压测或采购决策会安排的任务清单，写清责任人、交付物与完成节点；"
            "若方案已直接定型且无待办，注明暂无额外待办。"
        ),
    )
