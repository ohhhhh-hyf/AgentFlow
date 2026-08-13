"""notes_core 的契约定义（prompt 文本见 prompts.py）。"""
from __future__ import annotations

from tools.contracts import (
    GenerationContract, ObjListField, StrField, StrListField,
)


class NotesUnderstandingGenerationContract(GenerationContract):
    """笔记理解输出契约。"""

    fields = [
        StrField("note_purpose", "一句话概括这份笔记的用途或主题"),
        ObjListField("sections", [
            StrField("title", "章节或段落标题"),
            StrField("summary", "该章节的核心内容概述"),
        ]),
        StrListField("key_terms", "原文中明确出现的重要术语、概念或关键词"),
        StrListField("open_questions", "笔记中仍不清楚、需要后续补充或确认的问题"),
    ]


NOTES_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT = (
    NotesUnderstandingGenerationContract.to_output_contract()
)

__all__ = [
    "NOTES_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT",
]