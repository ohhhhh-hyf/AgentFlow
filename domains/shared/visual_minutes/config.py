"""Visual Minutes 独立配置。

LLM 连接统一由 infra.llm 读取项目根目录 .env；
本模块只保存视觉生成策略参数，不保存 API Key。
"""
from __future__ import annotations

from pathlib import Path

# 与 infra.llm 监控 label 对齐
VISUAL_LLM_LABEL = "visual_minutes"

# Visual Minutes 专用温度；未配置时默认 0.2，可由 .env 覆盖
VISUAL_LLM_TEMPERATURE_ENV = "VISUAL_LLM_TEMPERATURE"
DEFAULT_VISUAL_TEMPERATURE = 0.2

# 单个 section 送给 Extractor 的原文预算
TRANSCRIPT_CHAR_BUDGET = 5000

# 并发抽取上限
MAX_EXTRACT_CONCURRENCY = 4

# 全局正文视觉密度软上限；超过时按 necessity 排序，不静默截断
MAX_SECTION_VISUALS = 8

# 允许的最小视觉数据阈值
MIN_TIMELINE_EVENTS = 3
MIN_TABLE_ROWS = 2
MIN_TABLE_COLUMNS = 2
MIN_FLOW_NODES = 3
MIN_FLOW_EDGES = 2
MIN_TREE_NODES = 3
MIN_STATS_METRICS = 2


def _find_project_root(start: Path) -> Path:
    """从当前包向上寻找项目根，兼容 visual_minutes 被移动到 domains/shared。

    优先用 infra/llm 目录定位项目根，避免子目录里的 .env 抢先命中。
    """
    for parent in (start, *start.parents):
        if (parent / "infra" / "llm").is_dir():
            return parent
    for parent in (start, *start.parents):
        if (parent / ".env").exists():
            return parent
    return start.parents[1] if len(start.parents) > 1 else start


# 项目根：根目录 .env 与 infra.llm 所在位置
PROJECT_ROOT = _find_project_root(Path(__file__).resolve().parent)
ENV_FILE = PROJECT_ROOT / ".env"


__all__ = [
    "DEFAULT_VISUAL_TEMPERATURE",
    "ENV_FILE",
    "MAX_EXTRACT_CONCURRENCY",
    "MAX_SECTION_VISUALS",
    "MIN_FLOW_EDGES",
    "MIN_FLOW_NODES",
    "MIN_STATS_METRICS",
    "MIN_TABLE_COLUMNS",
    "MIN_TABLE_ROWS",
    "MIN_TIMELINE_EVENTS",
    "MIN_TREE_NODES",
    "PROJECT_ROOT",
    "TRANSCRIPT_CHAR_BUDGET",
    "VISUAL_LLM_LABEL",
    "VISUAL_LLM_TEMPERATURE_ENV",
]
