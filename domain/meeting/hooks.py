"""meeting 域对引擎暴露的钩子（记忆 v2 / 各线 HTML / 无模板正文收尾压缩）。

为什么在这里（2026-09-22 决策）：引擎（tools/core/runner、tools/runtime/render、
tools/exports/outputs）原先直接 import 本域模块，属于跨层反向依赖。现在引擎只问
``hooks_for("meeting")``，域实现集中在**这一个文件**里，加新域不用碰 tools。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.core.domain_hooks import DomainHooks

from .memory.render import (
    apply_memory_citations,
    render_actions_html,
    render_minutes_html,
    render_risks_html,
)
from .memory.runtime import META_KEY, build_line_extra, encode_meta, persist_after_run
from .tasks.minutes.steps.minutes_render import compact_untemplated_minutes
from .tasks.minutes_trace.html import trace_review_html

# 会记忆的线：会议记忆只在纪要类线上注入/回写
MEMORY_LINES = frozenset({"minutes", "minutes_styles"})
# 无模板正文需要收尾压缩（去空行等）的线
_COMPACT_LINES = frozenset({"minutes", "minutes_trace"})


def _prepare_memory(
    *,
    project_root,
    domain: str,
    user_id: str,
    transcript: str,
    line_names: list[str],
    project_id: str | None = None,
    subject: str | None = None,
    meeting_time: str = "",
    request_id: str = "",
) -> tuple[Any, dict[str, str]]:
    """会议记忆的准备：把"本次归属"编码进 line_extra，渲染前由注入钩子解出来用。"""
    if not str(user_id or "").strip():
        return None, {}
    meta = encode_meta(Path(project_root), user_id, project_id or "", request_id, meeting_time)
    return None, {META_KEY: meta}


def _persist_memory(
    *,
    project_root,
    domain: str,
    user_id: str,
    project_id: str | None = None,
    request_id: str = "",
    subject: str | None = None,
    transcript: str = "",
    reports: dict[str, Any] | None = None,
    understanding: dict[str, Any] | None = None,
    meeting_time: str = "",
    bind: Any = None,
) -> Any:
    """跑完回写：抽取本次会议事实并入 registry / 场次状态 / 向量索引。"""
    if not str(user_id or "").strip():
        return None
    return persist_after_run(
        Path(project_root),
        user_id,
        project_id or "",
        request_id,
        transcript,
        reports or {},
        understanding or {},
        meeting_time=meeting_time,
        bind=bind,
    )


def _html_for(line_name: str, title: str, text: str, data: dict[str, Any] | None = None) -> str | None:
    """本域专属的产物 HTML；其它线返回 None 让引擎走通用 HTML。"""
    if line_name == "minutes":
        return render_minutes_html(title, text)
    if line_name == "risks":
        return render_risks_html(title, text, data)
    if line_name == "actions":
        return render_actions_html(title, text, data)
    if line_name == "minutes_trace":
        return trace_review_html(text, title=title)
    return None


def _compact_plain(line_name: str, text: str) -> str:
    return compact_untemplated_minutes(text) if line_name in _COMPACT_LINES else text


HOOKS = DomainHooks(
    memory_lines=MEMORY_LINES,
    prepare_memory=_prepare_memory,
    persist_memory=_persist_memory,
    inject_line_extra=build_line_extra,
    apply_citations=apply_memory_citations,
    html_for=_html_for,
    compact_plain=_compact_plain,
)

__all__ = ["HOOKS", "MEMORY_LINES"]
