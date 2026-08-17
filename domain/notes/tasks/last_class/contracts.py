"""last_class 的契约定义（prompt 文本见 prompts.py）。

「期末划重点复习文档」：输入老师最后一课划重点文本，抽取重点知识点
（程度分级：必考/重点/了解），后续在 render 阶段按学科检索学生知识库，
生成带「老师原话 + 库中来源」的复习文档。
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
                StrField(
                    "quote",
                    "老师原话片段，逐字引用用于锚定；找不到原话则不填",
                ),
                StrField(
                    "note",
                    "考察要求/考法提示/易错提醒；老师没说清就按该考点通行考法补一句，不要空着",
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
                    "检索关键词 2-4 个：正式术语 + 别名/常见说法，"
                    "用于在学生知识库中检索该知识点的对应内容",
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
                StrField(
                    "example",
                    "典型例题 1 道（必考/重点必须给，60-150 字）："
                    "该考点考试时最可能出现的具体题——老师原话/PPT 点过的题优先，"
                    "没有就给该考点通行标准题；写清「题干 → 关键解法 2-3 步 → 答案」，"
                    "让学生能直接照做；禁止只写「如：练习相关例题」这类空话",
                ),
                StrListField(
                    "assignment_refs",
                    "老师指定的作业/题号/教材出处（如「课后 3.2」「讲义第 5 题」「往年卷第二题」），"
                    "0-2 个；老师没提就空数组",
                ),
                StrField(
                    "explain_what",
                    "「是什么」正文：定义/公式 + 适用边界 + 老师点到的变形，"
                    "必考/重点 150-240 字，了解 80-140 字；可展开通行内容，但不要写成老师原话",
                ),
                StrField(
                    "explain_why",
                    "「为什么」正文 80-150 字：老师如何强调、落在哪类题、不抓会丢什么分",
                ),
                StrField(
                    "explain_trap",
                    "「易错与变形」70-140 字：至少一个具体坑、对比或反例，不要空泛说容易错",
                ),
                StrField(
                    "explain_how",
                    "「怎么办」90-160 字：4-5 个连续动作（默写→练哪类题→核对标准→回看错因）",
                ),
            ],
        ),
        StrListField(
            "exam_hints",
            "考试形式/题型数量/分值占比 2-4 条；老师没提开闭卷就不要编；禁止空数组",
        ),
        StrListField(
            "classroom_notes",
            "老师课堂上的建议、强调、提醒、口头叮嘱 2-4 条（只收老师真实说过的内容）；"
            "禁止写「还有 N 天就考试」「复习时间紧迫」这类无信息量的话，也禁止编造开闭卷等制度；禁止空数组",
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
            "仅拦截严重问题：quote 对不上原文、编造老师未说的知识点、"
            "程度明显错判（必考写成了解或反之）、focus_points 全空",
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
