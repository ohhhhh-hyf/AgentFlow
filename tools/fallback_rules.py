"""fallback_rules.py —— 降级拼装规则的声明式构件类。

开发者用这些类在 ``contracts.py`` 里声明"降级时如何把草稿拼成文本"，
替代裸 dict（语义自明、与 GenerationContract/SupervisorContract 同风格）：

    class MinutesFallbackRules(FallbackRules):
        sections = [
            Raw("headline"),
            Join("executive_summary", "会议要点"),
        ]
        empty_text = "请直接参考会议原文"
        disclaimer = True

    MINUTES_FALLBACK_RULES = MinutesFallbackRules()

工厂脚本检测到 ``FallbackRules`` 子类后，自动生成完整的 fallback 节点
（调用 orchestrator 的 ``_fallback_text(state, "minutes_generation", MINUTES_FALLBACK_RULES)``）。
"""
from __future__ import annotations


class Section:
    """降级拼装段基类：从草稿取一个字段并按 kind 规则输出。"""

    kind = "raw"

    def __init__(
        self,
        field: str,
        label: str | dict | None = None,
        merge: list[str] | None = None,
    ) -> None:
        self.field = field
        self.label = label
        self.merge = merge


class Raw(Section):
    """单值原样输出（如纪要 headline）。"""

    kind = "raw"



class Join(Section):
    """字符串列表带标签输出：``{label}：{v1；v2}``（空段跳过）。"""

    kind = "join"


class Lines(Section):
    """字典列表逐行输出：``{n}. {format_action}``（负责人/截止/优先级）。"""

    kind = "lines"



class FallbackRules:
    """降级拼装规则基类。

    子类声明：
    - ``sections``：有序段列表（Section 子类实例）
    - ``empty_text`` / ``empty_prefix`` / ``empty_purpose``：全空时兜底文案
    - ``disclaimer``：是否追加（生成可能有误）
    - ``structured``：``{"merge": [字段...]}`` 客观合并的结构化列表（items）
    """

    sections: list[Section] = []
    empty_text: str = ""
    empty_prefix: str = ""
    empty_purpose: bool = False
    disclaimer: bool = False
    structured: dict | None = None
