"""library 契约：增量与冲突都是结构化字段。"""
from __future__ import annotations

from tools.schema.contracts import (
    Check,
    Decision,
    Feedback,
    GenerationContract,
    ObjListField,
    StrField,
    SupervisorContract,
)
from tools.schema.fallback_rules import FallbackRules, Lines


class LibraryGenerationContract(GenerationContract):
    fields = [
        StrField("message", "给用户看的一句话"),
        StrField("increment", "新增可编目知识单元数"),
        StrField("image_count", "导入图片张数（OCR 失败时为 0）"),
        StrField("doc_count", "导入文档份数（非图片文件均计为文档）"),
        ObjListField(
            "files",
            [
                StrField("name", "文件名"),
                StrField("added", "新增块"),
                StrField("removed", "清理块"),
                StrField("unchanged", "未变块"),
            ],
        ),
        ObjListField(
            "increment_by_file",
            [
                StrField("name", "文件名"),
                StrField("count", "该文件贡献的可编目知识单元"),
            ],
        ),
        ObjListField(
            "items",
            [
                StrField("text", "新增知识摘录"),
                StrField("source", "来源文件"),
            ],
        ),
    ]


class LibrarySupervisorContract(SupervisorContract):
    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写")
    checks = [Check("library_check", "仅记录入库失败")]



# 任务线完备性协议符号（sync_domain readiness 按名称存在性判定；
# library 为程序化任务线，OUTPUT_CONTRACT 不进入运行时 LLM 调用）
LIBRARY_GENERATION_OUTPUT_CONTRACT = LibraryGenerationContract.to_output_contract()
LIBRARY_SUPERVISOR_OUTPUT_CONTRACT = LibrarySupervisorContract.to_output_contract()


class LibraryFallbackRules(FallbackRules):
    sections = [Lines("items")]
    empty_text = "没有写入知识库"
    structured = {"field": "items"}


LIBRARY_FALLBACK_RULES = LibraryFallbackRules()
