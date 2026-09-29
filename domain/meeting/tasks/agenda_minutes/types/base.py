"""base.py -- 9 大会议类型幕后导师规范基类与栏目完成判据定义。

核心原则：
- 议题纪要的 1~5 栏骨架对全会议永远绝对固定（目标、依据、过程、结论、行动）；
- 会议类型退居幕后，作为指挥大模型提炼专业事实的静默导师；
- 绝不向前端/输出层抛出任何生造分类标签或黑话术语。
"""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass


@dataclass(frozen=True)
class PillarGuide:
    """单个会议类型下 1~5 栏的专属完成判据与指导内容（Definition of Done）。"""

    target_and_audience: str
    """1. 目标与对象 指导要求（核心诉求、汇报对象、明确排除项）。"""

    content_and_evidence: str
    """2. 内容与依据 指导要求（方案改动、硬核参数/SLA指标/时间线）。"""

    process_and_interaction: str
    """3. 过程与互动 指导要求（争议焦点、评委/各方质询、论证释疑依据）。"""

    conclusion_and_status: str
    """4. 结论与状态 指导要求（终局口径、前置限制红线、未决阻塞说明）。"""

    action_items: str
    """5. 行动与效果 指导要求（责任人、具体交付物、时限节点）。"""


class BaseAgendaTypeSpec(ABC):
    """会议类型幕后导师抽象基类。"""

    type_id: str
    """英文标识（如 decision_approval）。"""

    type_name: str
    """中文名称（如 决策审批型）。"""

    core_purpose: str
    """核心目的定位。"""

    core_output: str
    """核心输出成果。"""

    guide: PillarGuide
    """1~5 栏的专属提取与完成判据。"""

    keywords: tuple[str, ...]
    """用于标题/主题/实录特征识别的关键词元组。"""

    @property
    def pillars(self) -> tuple[str, ...]:
        """标准 1~5 栏字段元组。"""
        return (
            "target_and_audience",
            "content_and_evidence",
            "process_and_interaction",
            "conclusion_and_status",
            "action_items",
        )

    def format_prompt_guidance(self) -> str:
        """生成注入到单议题抽取 System Prompt 中的导师指引块。"""
        return f"""【当前会议类型指引（幕后导师规范 - {self.type_name}）】：
- 核心定位：{self.core_purpose}
- 核心输出：{self.core_output}
- 各栏完成判据（DoD）：
  1. 目标与对象：{self.guide.target_and_audience}
  2. 内容与依据：{self.guide.content_and_evidence}
  3. 过程与互动：{self.guide.process_and_interaction}
  4. 结论与状态：{self.guide.conclusion_and_status}
  5. 行动与效果：{self.guide.action_items}"""

