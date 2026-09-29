"""alignment_consensus.py -- 4. 对齐共识型幕后导师。

核心目的：跨团队拉齐认知与敲定协同边界。
典型场景：跨团队拉通会、接口契约对齐、业务边界划分、联合方案拉通。
"""
from __future__ import annotations

from .base import BaseAgendaTypeSpec, PillarGuide


class AlignmentConsensusTypeSpec(BaseAgendaTypeSpec):
    type_id = "alignment_consensus"
    type_name = "对齐共识型"
    core_purpose = "跨团队拉齐认知与敲定协同边界"
    core_output = "共识边界、未决分歧、升级事项"
    keywords = (
        "对齐",
        "拉通",
        "接口对齐",
        "协同会",
        "跨团队",
        "跨部门",
        "职责边界",
        "边界划分",
        "边界",
        "协作",
        "业务对齐",
        "契约",
        "联合会议",
    )

    guide = PillarGuide(
        target_and_audience=(
            "交代跨团队拉齐认知、消除职责盲区与敲定协作边界的核心诉求；"
            "指明协同参与的各业务线与团队范围，明确不在此次对齐范围的事项。"
        ),
        content_and_evidence=(
            "提炼各方系统交互的数据流向、接口参数与协议规范；"
            "交代上下游交付时限、异常容灾责任分摊与客观技术约束。"
        ),
        process_and_interaction=(
            "提炼在职责边界、接口变更成本、错误兜底分摊与交付排期上的各方分歧与协商过程；"
            "记录代表性争议点以及最终相互妥协靠拢的论据。"
        ),
        conclusion_and_status=(
            "用自然语言说明双方/多方最终达成的统一口径、接口契约与责任边界；"
            "如仍有未决分歧，明确说明分歧症结以及需提请更高层裁决的具体议题。"
        ),
        action_items=(
            "输出接口契约文档归档、双方联合联调排期、测试环境准备的具体对接人与时间节点；"
            "若认知已完全拉齐无新待办，注明暂无额外待办。"
        ),
    )
