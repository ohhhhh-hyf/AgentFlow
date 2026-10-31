"""Section Summary 异常类型。"""
from __future__ import annotations


class SectionSummaryError(Exception):
    """分段速览的基础异常。"""


class SectionSummaryInputError(SectionSummaryError, ValueError):
    """逐字稿格式无法解析（例如没有时间戳）。"""


class SectionSummaryFormatError(SectionSummaryError, ValueError):
    """模型输出无法解析成合法的分段数组。"""


__all__ = [
    "SectionSummaryError",
    "SectionSummaryFormatError",
    "SectionSummaryInputError",
]
