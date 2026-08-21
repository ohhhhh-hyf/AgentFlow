"""knowledge_graph 的契约定义（prompt 文本见 prompts.py）。

知识图谱线的草稿 = 任意图数据（nodes + edges）：
- nodes：概念/术语节点（锚定原文定义）
- edges：类型化关系边（source/relation/target/evidence，evidence 必须能定位原文）

图数据可确定性渲染为两种视图：
- 树形大纲（markmap）—— 层级结构，人好懂
- 网状图谱（graphviz）—— 关系全貌，是主产物
"""
from __future__ import annotations

from tools.contracts import (
    Check, Decision, Feedback, GenerationContract, ObjListField, StrField,
    SupervisorContract,
)
from tools.fallback_rules import FallbackRules, Lines


class KnowledgeGraphGenerationContract(GenerationContract):
    """知识图谱生成输出契约。"""

    fields = [
        StrField(
            "title",
            "图谱主题（根节点）：笔记主题，优先逐字沿用 note_purpose",
        ),
        ObjListField(
            "nodes",
            [
                StrField(
                    "name",
                    "概念/术语名，原样引用原文（≤ 15 字）",
                ),
                StrField(
                    "definition",
                    "原文中的定义或首次出现表述（原句截取）；原文无定义则空串",
                ),
                StrField(
                    "section",
                    "所属章节标题（对应 notes_understanding.sections.title）；无则空串",
                ),
            ],
        ),
        ObjListField(
            "edges",
            [
                StrField("source", "关系起点概念名（必须是 nodes 中的 name）"),
                StrField(
                    "relation",
                    "关系类型：包含/属于/导致/缓解/区别于/取决于/用于/定义/"
                    "示例/相关/等价于/前提/转化",
                ),
                StrField("target", "关系终点概念名（必须是 nodes 中的 name）"),
                StrField("evidence", "原文中支撑该关系的具体语句（可定位）"),
            ],
        ),
    ]


class KnowledgeGraphSupervisorContract(SupervisorContract):
    """知识图谱审核契约。"""

    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行、有原文依据")
    checks = [
        Check(
            "graph_check",
            "仅记录严重问题：节点不在原文明确出现、关系无原文依据、"
            "edges 的 source/target 不在 nodes 中、evidence 定位不到原文",
        ),
    ]


KNOWLEDGE_GRAPH_GENERATION_OUTPUT_CONTRACT = (
    KnowledgeGraphGenerationContract.to_output_contract()
)
KNOWLEDGE_GRAPH_SUPERVISOR_OUTPUT_CONTRACT = (
    KnowledgeGraphSupervisorContract.to_output_contract()
)


class KnowledgeGraphFallbackRules(FallbackRules):
    """知识图谱降级拼装：逐条列出节点（结构由 nodes/edges 提供）。"""

    sections = [
        Lines("nodes"),
    ]
    empty_text = "暂无知识图谱"
    structured = {"field": "nodes"}


KNOWLEDGE_GRAPH_FALLBACK_RULES = KnowledgeGraphFallbackRules()

__all__ = [
    "KNOWLEDGE_GRAPH_GENERATION_OUTPUT_CONTRACT",
    "KNOWLEDGE_GRAPH_SUPERVISOR_OUTPUT_CONTRACT",
    "KNOWLEDGE_GRAPH_FALLBACK_RULES",
]
