"""last_class 的契约定义（prompt 文本见 prompts.py）。

「期末划重点复习文档」：从老师最后一课文本抽全可考知识
（程度、原话、公式要点、方法、例题），渲染时挂老师原话与知识库出处。
"""
from __future__ import annotations

from tools.contracts import (
    Check,
    Decision,
    EnumField,
    Feedback,
    GenerationContract,
    ObjListField,
    StrField,
    StrListField,
    SupervisorContract,
)
from tools.fallback_rules import FallbackRules, Lines, Raw


class LastClassGenerationContract(GenerationContract):
    """把老师划重点文本抽成重点知识点，供复习文档挂载。"""

    fields = [
        ObjListField(
            "focus_points",
            [
                EnumField(
                    "degree",
                    ["必考", "重点", "了解"],
                    "必考=老师明说一定考/必考/重点中的重点；重点=着重看/要会/重点看；"
                    "了解=了解一下/有印象/简单看看；按语气推断时宁高勿低",
                ),
                StrField(
                    "name",
                    "知识点名称，尽量与教材/笔记术语一致（口语名可括注正式名）",
                ),
                StrListField(
                    "quotes",
                    "老师原话 1–3 条，逐字截取连续片段：第一条最能定位该考点，"
                    "其余补变形/流程/易错原话；找不到则空数组，禁止改写拼接",
                ),
                StrField(
                    "note",
                    "一句话考法（出大题/选择辨析/证明书写）；老师没说清就按通行考法补一句",
                ),
                StrField(
                    "chapter",
                    "所属章节或模块，优先用老师原话中的章名；无法判断填空串",
                ),
                StrField(
                    "priority_reason",
                    "优先级依据，必须来自老师原话关键词、提及频次、题型或分值",
                ),
                EnumField(
                    "difficulty",
                    ["简单", "中等", "较难"],
                    "按老师要求和考法判断：概念识别=简单，常规计算/证明=中等，变形/综合/易错=较难",
                ),
                StrListField(
                    "prerequisites",
                    "理解该考点必须先会的一层前置知识，1-3 个；不要追溯前置的前置",
                ),
                StrListField(
                    "question_types",
                    "可能题型，从「选择 / 填空 / 计算 / 证明 / 应用」中选 1-3 个；"
                    "老师明说按老师说的，没明说按知识点性质推断",
                ),
                StrListField(
                    "keywords",
                    "检索关键词 2–5 个：正式术语 + 口语别名 + 老师点过的变形"
                    "（如 sin3x/x、加减慎换），用于知识库检索",
                ),
                StrListField(
                    "key_facts",
                    "该考点硬知识 2–6 条：公式、等价关系、判断标准、老师给的题量/题型；"
                    "写成可默写短句，不要「要认真掌握」",
                ),
                StrListField(
                    "methods",
                    "老师教的解题/判断步骤 1–4 条（凑形结构、0/0 套路、间断点流程等）",
                ),
                StrField(
                    "mastery",
                    "掌握要求：会背定义 / 会套公式计算 / 会推导证明 / 会应用，"
                    "按 degree 与老师语气推断（必考要求最高）",
                ),
                StrListField(
                    "practice",
                    "可执行练习动作 2-3 条；老师给了题量就用老师的，没给按程度补默认量",
                ),
                StrListField(
                    "related_names",
                    "与该考点有前提/对比/递进/互补关系的其他考点名称，0-3 个",
                ),
                StrListField(
                    "check_points",
                    "针对本考点的自测检验点 2 条，必须具体可自查："
                    "如「默写九个等价无穷小并说出加减慎换的原因」「说出 sin x/x 与 sin(1/x) 极限的区别」；"
                    "不要用「讲清楚/会做典型题」这类空话，不要加「能否」套话",
                ),
                StrListField(
                    "examples",
                    "典型例题 1–3 道（必考/重点必须有，了解空数组）："
                    "老师口头/PPT 点过的题优先；每道写「题干 → 关键 2–3 步 → 答案」",
                ),
                StrListField(
                    "assignment_refs",
                    "老师指定的作业/题号/教材出处（如「课后 3.2」「讲义第 5 题」「往年卷第二题」），"
                    "0-2 个；老师没提就空数组",
                ),
                StrField(
                    "explain_what",
                    "「是什么」正文：定义/公式 + 适用边界 + 老师点到的变形；"
                    "必考/重点 160-280 字，了解 60-100 字；不要复述 quotes",
                ),
                StrField(
                    "explain_why",
                    "「为什么」70-130 字：老师为何盯它、落在哪类题、不抓会丢什么",
                ),
                StrField(
                    "explain_trap",
                    "「易错与变形」80-150 字：至少一个具体坑或老师点过的反例",
                ),
                StrField(
                    "explain_how",
                    "「怎么办」80-140 字：默写→按 methods 练哪类题（带题量）→核对→回看",
                ),
            ],
        ),
        StrListField(
            "exam_hints",
            "老师说过的卷面事实 2–5 条：分值占比、计算题大约几道、选择/证明考什么；"
            "没提开闭卷就不要编；禁止空数组",
        ),
        StrListField(
            "classroom_notes",
            "老师真实叮嘱 2–5 条（对照笔记、每块十道、过错题本、默写公式）；"
            "去掉人称；禁止无信息量的催促，禁止编造制度；禁止空数组",
        ),
        StrField(
            "strategy",
            "整体复习策略 3-5 句：按必考→重点→了解给时间比例和验收标准",
        ),
    ]


class LastClassSupervisorContract(SupervisorContract):
    """期末划重点审核契约。"""

    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行、有原文依据")
    checks = [
        Check(
            "last_class_check",
            "仅拦截严重问题：quotes 对不上原文、编造老师未点的知识点、"
            "必考缺少 quotes/key_facts、程度明显错判、focus_points 全空或漏掉整块必考",
        ),
    ]


LAST_CLASS_GENERATION_OUTPUT_CONTRACT = LastClassGenerationContract.to_output_contract()
LAST_CLASS_SUPERVISOR_OUTPUT_CONTRACT = LastClassSupervisorContract.to_output_contract()


class LastClassFallbackRules(FallbackRules):
    """期末划重点降级拼装：保留重点列表。"""

    sections = [
        Raw("title"),
        Lines("focus_points"),
        Raw("strategy"),
    ]
    empty_text = "暂未提取到重点知识点"
    structured = {"field": "focus_points"}


LAST_CLASS_FALLBACK_RULES = LastClassFallbackRules()

__all__ = [
    "LAST_CLASS_FALLBACK_RULES",
    "LAST_CLASS_GENERATION_OUTPUT_CONTRACT",
    "LAST_CLASS_SUPERVISOR_OUTPUT_CONTRACT",
]
