"""给调试台/终端的进度日志（INFO），标明当前 Agent。"""
from __future__ import annotations

import logging

logger = logging.getLogger("agentflow")

_NODE_CN = {
    "meeting_understanding": "会议理解 Agent",
    "perspective_modeling": "视角建模 Agent",
    "notes_understanding": "笔记理解 Agent",
}
_SUFFIX = (
    ("_supervisor", "审核 Agent"),
    ("_revision", "返工"),
    ("_fallback", "降级拼装"),
    ("_render", "渲染"),
    ("_agent", "生成 Agent"),
)


def progress(msg: str, *args) -> None:
    logger.info(msg, *args)


def node_label(node_name: str, line_cn_names: dict | None = None) -> str:
    raw = (node_name or "").strip()
    if raw in _NODE_CN:
        return _NODE_CN[raw]
    names = line_cn_names or {}
    for suffix, title in _SUFFIX:
        if raw.endswith(suffix):
            line = raw[: -len(suffix)]
            return f"{names.get(line, line)}{title}"
    return names.get(raw, raw) or "未知节点"
