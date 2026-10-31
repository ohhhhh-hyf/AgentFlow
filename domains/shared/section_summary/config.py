"""Section Summary 独立配置。

LLM 连接统一由项目根目录 .env 与 infra.llm.LLMClient 决定；
本模块只保存分段速览自己的策略参数。
"""
from __future__ import annotations

from pathlib import Path

# 与 infra.llm 监控 label 对齐
LLM_LABEL = "shared/section_summary"

# 分段任务默认低温，保证切分稳定
DEFAULT_TEMPERATURE = 0.0

# Prompt 中给模型的用户消息（原始 Prompt 已作为 system prompt）
USER_PROMPT = "请按上述规则输出 JSON 数组。"

# 输出字段上限（与 Prompt 中的硬约束一致）
MAX_TITLE_CHARS = 20
MAX_KEYWORDS = 4
MAX_KEYWORD_CHARS = 10
MAX_SUMMARY_CHARS = 200

# 规则兜底：相邻发言间隔超过该秒数，或单段跨度超过该秒数，就切一段
FALLBACK_GAP_SECONDS = 90
FALLBACK_WINDOW_SECONDS = 300


def _find_project_root(start: Path) -> Path:
    """从当前包向上寻找项目根，兼容 section_summary 位于 domains/shared 下。"""
    for parent in (start, *start.parents):
        if (parent / "infra" / "llm").is_dir():
            return parent
    for parent in (start, *start.parents):
        if (parent / ".env").exists():
            return parent
    return start.parents[3] if len(start.parents) > 3 else start


PROJECT_ROOT = _find_project_root(Path(__file__).resolve().parent)
ENV_FILE = PROJECT_ROOT / ".env"


__all__ = [
    "DEFAULT_TEMPERATURE",
    "ENV_FILE",
    "FALLBACK_GAP_SECONDS",
    "FALLBACK_WINDOW_SECONDS",
    "LLM_LABEL",
    "MAX_KEYWORDS",
    "MAX_KEYWORD_CHARS",
    "MAX_SUMMARY_CHARS",
    "MAX_TITLE_CHARS",
    "PROJECT_ROOT",
    "USER_PROMPT",
]
