"""base.py -- 9 大会议类型幕后导师规范基类与栏目完成判据定义。

核心原则：
- 议题纪要的 1~4 栏骨架对全会议永远统一（背景与目标、核心内容、核心认知、后续行动）；
- 会议类型退居幕后，作为指挥大模型提炼专业事实的静默导师；
- 语言朴实自然，不堆砌华丽辞藻，直接给出清晰实用的各栏完成判据（DoD）。
"""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass


@dataclass(frozen=True)
class PillarGuide:
    """单个会议类型下 1~4 栏的专属完成判据与指导内容（Definition of Done）。"""

    background_and_goals: str
    """1. 背景与目标 指导要求（1~2 句话直接说清为什么开/汇报、要达成什么目的或展示什么内容，有排除项顺带说明）。"""

    core_content: str
    """2. 核心内容 指导要求（分点讲清技术方案细节、量化数据对比、现场质询与问答交锋）。"""

    core_insights: str
    """3. 核心认知 指导要求（提炼 2~3 条高价值启发、落地避坑经验、或审批裁决与生效前置约束）。"""

    action_items: str
    """4. 后续行动 指导要求（责任人、具体交付物、时限节点；纯分享交流无派工则留空，不渲染）。"""

    # 兼容旧属性访问
    @property
    def target_and_audience(self) -> str:
        return self.background_and_goals

    @property
    def content_and_evidence(self) -> str:
        return self.core_content

    @property
    def process_and_interaction(self) -> str:
        return self.core_content

    @property
    def conclusion_and_status(self) -> str:
        return self.core_insights


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
    """1~4 栏的专属提取与完成判据。"""

    keywords: tuple[str, ...]
    """用于标题/主题/实录特征识别的关键词元组。"""

    @property
    def pillars(self) -> tuple[str, ...]:
        """标准 1~4 栏字段元组。"""
        return (
            "background_and_goals",
            "core_content",
            "core_insights",
            "action_items",
        )

    def format_prompt_guidance(self) -> str:
        """生成注入到单议题抽取 System Prompt 中的导师指引块。"""
        return f"""【当前会议类型指引（幕后导师规范 - {self.type_name}）】：
- 核心定位：{self.core_purpose}
- 核心输出：{self.core_output}
- 各栏完成判据（DoD）：
  1. 背景与目标：{self.guide.background_and_goals}
  2. 核心内容：{self.guide.core_content}
  3. 核心认知：{self.guide.core_insights}
  4. 后续行动：{self.guide.action_items}"""
