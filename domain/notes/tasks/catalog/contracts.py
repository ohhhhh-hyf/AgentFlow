"""catalog 契约：四层知识目录树。"""
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


class CatalogGenerationContract(GenerationContract):
    """把资料骨架 + 老师重点 + 学生笔记收成一棵目录树。"""

    fields = [
        StrField("course", "课程名，优先用资料/学科名，不要编教材版本"),
        StrField("version", "目录版本号，首次为 1；增量成功后由程序递增，模型可回填当前值"),
        StrField(
            "mode",
            "build=首次生成；incremental_update=基于已有目录更新。有历史目录时必须 incremental_update",
        ),
        ObjListField(
            "chapters",
            [
                StrField("id", "稳定章节 ID，如 ch_001；增量时复用已有 ID"),
                StrField("name", "章节标准名，沿用资料原有章名"),
                EnumField(
                    "change_type",
                    ["unchanged", "added", "updated", "merged", "moved"],
                    "本次变更类型",
                ),
                ObjListField(
                    "topics",
                    [
                        StrField("id", "稳定主题 ID，如 tp_001"),
                        StrField("name", "主题标准名，沿用资料原有节/主题名"),
                        EnumField(
                            "change_type",
                            ["unchanged", "added", "updated", "merged", "moved"],
                            "本次变更类型",
                        ),
                        ObjListField(
                            "knowledge_points",
                            [
                                StrField("id", "稳定唯一 ID，增量时必须复用已有 kp_id，禁止换号"),
                                StrField("name", "可独立学习的知识点标准名"),
                                StrListField("aliases", "同义名称，合并后放这里"),
                                StrField("chapter", "所属章节名，与上层 chapter.name 一致"),
                                StrField("topic", "所属主题名，与上层 topic.name 一致"),
                                EnumField(
                                    "knowledge_type",
                                    ["concept", "formula", "theorem", "method", "application", "mixed"],
                                    "concept概念 formula公式 theorem定理 method方法 application应用 mixed综合",
                                ),
                                StrListField(
                                    "knowledge_items",
                                    "该点下的条件/公式/分类/性质短名，不要升成独立知识点",
                                ),
                                EnumField(
                                    "importance",
                                    ["1", "2", "3", "4", "5"],
                                    "重点程度：1普通 2次重点 3重要 4很重要 5核心；与难度分开",
                                ),
                                EnumField(
                                    "difficulty",
                                    ["1", "2", "3", "4", "5"],
                                    "难度：1简单 2较简单 3中等 4较难 5很难；与重点分开",
                                ),
                                EnumField(
                                    "teacher_emphasis",
                                    ["0", "1", "2", "3"],
                                    "只根据老师文本：0未提及 1提及 2明确强调 3反复/强烈强调",
                                ),
                                EnumField(
                                    "foundational_level",
                                    ["1", "2", "3", "4", "5"],
                                    "对其他点的前置作用：1很少 2较弱 3一般 4重要前置 5核心基础",
                                ),
                                EnumField(
                                    "exam_signal",
                                    ["none", "weak", "medium", "strong"],
                                    "材料里的考试信号强弱；只能依据老师或资料明确说法，不要写必考概率",
                                ),
                                StrListField(
                                    "teacher_focus_items",
                                    "老师点到的具体 Item，必须是 knowledge_items 里已有的短名",
                                ),
                                EnumField(
                                    "note_coverage",
                                    ["none", "mentioned", "partial", "detailed"],
                                    "学生笔记覆盖，不要推断是否掌握",
                                ),
                                StrListField(
                                    "note_covered_items",
                                    "笔记写到了的 Item 短名",
                                ),
                                StrListField(
                                    "note_missing_items",
                                    "该 KP 有、但笔记没写到的 Item 短名",
                                ),
                                StrListField(
                                    "practice_type",
                                    "怎么练，可多选：recall记忆 distinguish辨析 calculate计算 prove证明 apply应用 choose_method选方法 mixed综合。不要因重要就默认 calculate。不要写本次题量",
                                ),
                                StrListField(
                                    "completion_criteria",
                                    "过关能力标签，可多选：can_recall / can_explain / can_distinguish / can_apply / can_choose_method / can_solve_standard / can_solve_variant / can_prove。只选真正符合该点的，不要写完整句子",
                                ),
                                EnumField(
                                    "learning_role",
                                    ["foundation", "core_concept", "core_method", "application", "integration"],
                                    "学习链路中的稳定角色：foundation基础前置 core_concept核心概念 core_method核心方法 application应用 integration综合连接。不要写成第一阶段/补前置",
                                ),
                                StrListField(
                                    "risk_tags",
                                    "知识本身的典型风险，可多选：condition_check条件易漏 concept_confusion概念易混 formula_misuse公式误用 method_selection方法选错 calculation_error计算易错 proof_format证明书写 boundary_case边界遗漏。不代表学生已经犯错",
                                ),
                                StrListField(
                                    "prerequisites",
                                    "前置 KP 的 name，必须是本目录里其他知识点",
                                ),
                                ObjListField(
                                    "related_points",
                                    [
                                        StrField("name", "关联 KP 的标准名"),
                                        EnumField(
                                            "relation",
                                            ["alternative", "used_with", "easily_confused", "derived_from"],
                                            "alternative替代 used_with配合 easily_confused易混 derived_from推导",
                                        ),
                                    ],
                                ),
                                StrListField(
                                    "sources",
                                    "来源角色：课程资料 / 老师重点 / 学生笔记，有才写",
                                ),
                                StrListField(
                                    "evidence",
                                    "短依据：来源类型 + 可核对片段，如「老师重点：……」",
                                ),
                                StrField(
                                    "confidence",
                                    "0-1 置信度，不确定就低一点，不要硬填高分",
                                ),
                                StrListField(
                                    "source_documents",
                                    "支撑该点的资料文件名",
                                ),
                                EnumField(
                                    "node_status",
                                    ["active", "merged", "deprecated", "uncertain"],
                                    "正常用 active",
                                ),
                                EnumField(
                                    "change_type",
                                    ["unchanged", "added", "updated", "merged", "moved"],
                                    "本次对该点做了什么",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
        StrListField(
            "unmatched_content",
            "无法挂到树上但不要丢的内容，各写一条短说明",
        ),
        StrListField(
            "uncertain_nodes",
            "分类没把握的节点，不要强行塞进某章",
        ),
        StrListField("added_chapters", "本次新增的章节名"),
        StrListField("added_topics", "本次新增的主题名"),
        StrListField("added_knowledge_points", "本次新增的知识点名"),
        StrListField("updated_knowledge_points", "本次有补充/修正的已有知识点名"),
        StrListField("merged_nodes", "本次合并记录，如「别名 A → kp_003 标准名」"),
    ]


class CatalogSupervisorContract(SupervisorContract):
    """只拦严重结构问题。"""

    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行")
    checks = [
        Check(
            "catalog_check",
            "仅拦截：目录全空、把例题/条件升成知识点、同义点大量重复、"
            "写成复习建议而不是目录、层级明显错乱",
        ),
    ]


CATALOG_GENERATION_OUTPUT_CONTRACT = CatalogGenerationContract.to_output_contract()
CATALOG_SUPERVISOR_OUTPUT_CONTRACT = CatalogSupervisorContract.to_output_contract()


class CatalogFallbackRules(FallbackRules):
    sections = [
        Raw("course"),
        Lines("chapters"),
    ]
    empty_text = "暂未生成知识目录"
    structured = {"field": "chapters"}


CATALOG_FALLBACK_RULES = CatalogFallbackRules()

__all__ = [
    "CATALOG_FALLBACK_RULES",
    "CATALOG_GENERATION_OUTPUT_CONTRACT",
    "CATALOG_SUPERVISOR_OUTPUT_CONTRACT",
]
