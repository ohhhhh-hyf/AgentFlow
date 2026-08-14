"""模板层：判型、编译、填充、评测。"""
from tools.template_eval import parse_document_char_budget
from tools.template_router import (
    LINE_SCHEMA_HINTS,
    detect_template_kind,
    maybe_compile_natural_template,
)

__all__ = [
    "LINE_SCHEMA_HINTS",
    "detect_template_kind",
    "maybe_compile_natural_template",
    "parse_document_char_budget",
]
