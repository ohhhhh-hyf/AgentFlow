"""跨域文本小工具：各任务线反复自抄的那几个一行函数（2026-09-21 收拢）。

为什么放这里而不是 tools/：它们是**领域实现层**的小工具（显示/组装用），
放进 tools 会让 tools 反向依赖领域语义；notes 域已验证逐字相同后先在这里合并，
meeting 域若出现同款可一并复用。
"""
from __future__ import annotations

from typing import Any

from tools.core.text import clean_text  # 唯一实现（domains 侧转导出）




def as_dict_list(value: object) -> list[dict[str, Any]]:
    """只保留列表里的 dict 项（非列表返回空）。"""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


__all__ = ["as_dict_list", "clean_text"]
