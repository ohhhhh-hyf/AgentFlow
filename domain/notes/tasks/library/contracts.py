"""library 契约：增量与冲突都是结构化字段。"""
from __future__ import annotations

from tools.contracts import (
    Check,
    Decision,
    Feedback,
    GenerationContract,
    ObjListField,
    StrField,
    SupervisorContract,
)
from tools.fallback_rules import FallbackRules, Lines


class LibraryGenerationContract(GenerationContract):
    fields = [
        StrField("message", "给用户看的一句话"),
        StrField("increment", "新增独立知识点数"),
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
                StrField("count", "该文件贡献的独立知识点"),
            ],
        ),
        ObjListField(
            "conflicts",
            [
                StrField("topic", "冲突主题"),
                StrField("new_file", "新上传文件"),
                StrField("old_file", "库内文件"),
                StrField("ambiguity", "歧义百分比"),
                StrField("new_excerpt", "新文件摘录"),
                StrField("old_excerpt", "库内摘录"),
                StrField("peer", "是否同批文件"),
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


LIBRARY_GENERATION_OUTPUT_CONTRACT = LibraryGenerationContract.to_output_contract()
LIBRARY_SUPERVISOR_OUTPUT_CONTRACT = LibrarySupervisorContract.to_output_contract()


class LibraryFallbackRules(FallbackRules):
    sections = [Lines("items")]
    empty_text = "没有写入知识库"
    structured = {"field": "items"}


LIBRARY_FALLBACK_RULES = LibraryFallbackRules()
