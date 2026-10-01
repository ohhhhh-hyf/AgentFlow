"""跨子系统文本小工具（唯一定义处）。

2026-09-22 收拢：``clean_text`` 的实现曾在 8 个模块各写一份（会议记忆四处、notes 记忆与
题库、perspective、runtime/supervisor_slice），逐字相同；域侧另有 ``domain/_shared/text.py``
（从这里转导出，并额外提供 ``as_dict_list``）。
"""
from __future__ import annotations


def clean_text(value: object) -> str:
    """折叠所有空白并去首尾（展示/比对前的统一清洗）。"""
    return " ".join(str(value or "").split()).strip()


__all__ = ["clean_text"]
