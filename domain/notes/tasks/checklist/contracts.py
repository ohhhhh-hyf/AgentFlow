"""checklist 契约：只给已激活的 Catalog KP 写复习卡片，禁止新建知识点。"""
from __future__ import annotations

from tools.schema.contracts import (
    Check,
    Decision,
    Feedback,
    GenerationContract,
    ObjListField,
    StrField,
    StrListField,
    SupervisorContract,
)
from tools.schema.fallback_rules import FallbackRules, Lines, Raw


class ChecklistGenerationContract(GenerationContract):
    """卡片正文；KP 范围由程序从 Catalog 匹配，模型不得扩点。"""

    fields = [
        StrField("course", "沿用 Catalog 课程名"),
        StrField("catalog_version", "抄输入里的目录版本，不要改"),
        StrListField(
            "uncertain_quotes",
            "程序统计，输出 []（老师原话与目录的匹配由程序判定）",
        ),
        StrListField("strategy", "程序生成，输出 []"),
        ObjListField(
            "phases",
            [
                StrField("title", "阶段名"),
                StrField("goal", "阶段目标"),
                StrListField("kp_ids", "本阶段 KP id"),
                StrListField("names", "本阶段 KP 名"),
                StrField("check", "完成标准"),
            ],
            desc="程序生成，输出 []",
        ),
        # cards 放最后：输出超限被截断时，截断点落在 cards 内部——程序修复删掉
        # 残卡后补全括号即可通过校验（缺的卡由 assemble 按目录补齐）；若 cards 在前，
        # 截断会丢掉其后置的顶层字段，修复回退到哪都缺字段、必然失败。
        ObjListField(
            "cards",
            [
                StrField("kp_id", "必须是 Catalog 里已列出的 kp id"),
                StrField(
                    "exam_preview",
                    "考法预判：S 2-3 句、A 2 句；B/C 不进 LLM（程序合成）。写清题型与老师点到的变形/流程；无依据不要写必考或具体概率",
                ),
                StrListField(
                    "key_facts",
                    "必须会的硬知识：S 4-6 条、A 3-5 条。公式或判断标准写完整；不要写成「老师说了」",
                ),
                StrField(
                    "explain",
                    "讲解：S 200-260 字、A 120-180 字（档位见输入中每张卡；B/C 不进 LLM、由程序按目录条目合成）。定义或公式 + 适用边界 + 老师点到的变形 + 笔记缺项补什么；禁止空话，写满上限不奖励、超出会被裁剪",
                ),
                StrListField(
                    "method_steps",
                    "可执行步骤：S 4-6 步、A 3-4 步。method/application=解题；theorem/concept=判断流程；formula=使用与条件检查。每步写具体操作，不要「按方法做」",
                ),
                StrListField(
                    "pitfalls",
                    "易错：S 2-4 条、A 2-3 条。优先老师原话限制，并给具体反例或使用边界；无依据不要编",
                ),
            ],
        ),
    ]


class ChecklistSupervisorContract(SupervisorContract):
    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行")
    checks = [
        Check(
            "checklist_check",
            "仅拦截：cards 里出现 Catalog 没有的 kp_id、编造新知识点、"
            "无老师依据却写必考/具体概率、输出与目录无关的复习鸡汤",
        ),
    ]


CHECKLIST_GENERATION_OUTPUT_CONTRACT = ChecklistGenerationContract.to_output_contract()
CHECKLIST_SUPERVISOR_OUTPUT_CONTRACT = ChecklistSupervisorContract.to_output_contract()


class ChecklistFallbackRules(FallbackRules):
    sections = [Raw("course"), Lines("cards")]
    empty_text = "没有可用的知识目录，请先运行 catalog"
    structured = {"field": "cards"}


CHECKLIST_FALLBACK_RULES = ChecklistFallbackRules()

__all__ = [
    "CHECKLIST_FALLBACK_RULES",
    "CHECKLIST_GENERATION_OUTPUT_CONTRACT",
    "CHECKLIST_SUPERVISOR_OUTPUT_CONTRACT",
]
