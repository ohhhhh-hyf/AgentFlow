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
        background_and_goals=(
            "1~2 句话说明跨团队协作卡点与痛点（如接口时延超标、数据不一致），以及本次要敲定的对齐目标与契约。"
        ),
        core_content=(
            "分点陈述各方提出的方案与分歧点（如算法追求低时延 vs 客户端担心发热），以及现场讨论的权衡与折中过程。"
        ),
        core_insights=(
            "写明最终各方确认的技术口径、接口协议或预算拆解；若仍有未决分歧，客观记录争议点。"
        ),
        action_items=(
            "表格列出联调测试环境准备、接口文档提交等责任人、交付事项与时间；若无会后派工则留空。"
        ),
    )
