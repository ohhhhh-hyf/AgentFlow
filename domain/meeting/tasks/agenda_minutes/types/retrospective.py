"""retrospective.py -- 6. 复盘归因型幕后导师。

核心目的：事故复盘、根因剖析与改进防重发。
典型场景：重大事故复盘会、项目结项复盘、质量复盘、业务运营复盘。
"""
from __future__ import annotations

from .base import BaseAgendaTypeSpec, PillarGuide


class RetrospectiveTypeSpec(BaseAgendaTypeSpec):
    type_id = "retrospective"
    type_name = "复盘归因型"
    core_purpose = "事故复盘、根因剖析与改进防重发"
    core_output = "根因结论、改进主题与防重发规范"
    keywords = (
        "复盘",
        "事故",
        "故障",
        "复盘会",
        "根因分析",
        "5-whys",
        "反思会",
        "复盘总结",
        "复盘研讨",
    )

    guide = PillarGuide(
        target_and_audience=(
            "交代本次复盘的事件或项目背景、预期设想与实际结果的偏差；"
            "指明复盘面向的管理部门、技术委员会与责任团队。"
        ),
        content_and_evidence=(
            "提炼客观还原的事件脉络与精准到分秒的时间线；"
            "列举系统告警数据、指标跳水幅度、受影响业务范围及资损/客诉量化指标。"
        ),
        process_and_interaction=(
            "记录现场深入排查根因时的推导交锋与质询辩论；"
            "提炼排障过程中各节点判断是否合理、监控告警是否及时的实录证据。"
        ),
        conclusion_and_status=(
            "用自然语言明确拆解两层根因：技术直接诱因（触发的具体异常代码/硬件故障/网络抖动）与机制管理根因（测试覆盖盲区/发布流程漏洞/监控缺失）；"
            "交代事故定性定级与责任归属定调。"
        ),
        action_items=(
            "输出防重发技术加固、补全监控告警、修改发布审批SOP的具体落实人、明确交付物与整改验收时限；"
            "若整改措施已在现场完全就绪无额外待办，注明暂无额外待办。"
        ),
    )
