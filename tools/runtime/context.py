"""领域无关的理解钩子与渲染上下文拼装。

渲染上下文不再按任务线生成 N 份同构方法。标签、理解字段由领域钩子提供。
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

from tools.domain_engine_text import json_dumps


def understanding_of(state: dict, key: str) -> dict:
    """只读取领域声明的理解字段；空 key 或非 dict 一律返回 {}。"""
    if not key:
        return {}
    value = state.get(key)
    return value if isinstance(value, dict) else {}


def build_render_context(
    *,
    mode: str,
    objective: bool,
    blocks: Sequence[tuple[str, object, str]],
    draft: object,
    review: object,
    line_cn: str,
    extra: str = "",
    dumps: Callable[[object], str] | None = None,
) -> str:
    """拼装与历史生成区一致的渲染上下文。

    ``blocks`` 为 ``(标签, 值, "raw"|"json")``。草稿/审核标签由 ``line_cn``
    推导为「已批准{中文名}草稿」/「{中文名}审核结论」，以保持
    minutes_trace 等按标签抠 JSON 的 render 兼容。
    ``extra``（如记忆注入）对所有线生效，不再特判 minutes_generation。
    """
    serialize = dumps or json_dumps
    head = (
        f"视角模式：{mode}\n"
        f"objective_perspective：{bool(objective)}"
    )
    parts = [head]
    for label, value, kind in blocks:
        body = value if kind == "raw" else serialize(value)
        parts.append(f"{label}：\n{body}")
    parts.append(f"已批准{line_cn}草稿：\n{serialize(draft)}")
    parts.append(f"{line_cn}审核结论：\n{serialize(review)}")
    text = "\n\n".join(parts)
    extra_text = (extra or "").strip()
    if extra_text:
        text = f"{text}\n\n{extra_text}"
    return text


__all__ = ["build_render_context", "understanding_of"]
