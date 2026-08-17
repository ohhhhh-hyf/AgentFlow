"""notes 领域配置 —— 脚本与运行时共享的领域专属数据。

渲染上下文由 DomainNodes 钩子拼装。LINE_KINDS 决定渲染/CLI/结构抽取。
"""
from tools.runtime.kinds import DETERMINISTIC_PIPELINE, LLM_EXTRACT

# state 类型注解类名（生成骨架用）
STATE_CLASS = "NotesState"

# ── 任务线中文名注册表（脚本与运行时共享的唯一来源）──────────────
LINE_CN_NAMES: dict[str, str] = {
    "knowledge_graph": "知识图谱",
    "review": "笔记审查",
    "quiz": "自测题",
    "library": "资料入库",
    "last_class": "last_class",
}

# 任务线种类（手写，不进 sync_domain 生成区）。
LINE_KINDS: dict[str, object] = {
    "knowledge_graph": {
        "kind": DETERMINISTIC_PIPELINE,
        "llm_render": "if_template",
        "cli_template": True,
    },
    "review": {
        "kind": LLM_EXTRACT,
        "cli_template": False,
        "llm_render": "if_template",
    },
    "quiz": {
        "kind": LLM_EXTRACT,
        "cli_template": False,
        "llm_render": "if_template",
    },
    "library": {
        "kind": DETERMINISTIC_PIPELINE,
        "cli_template": False,
        "llm_render": "never",
    },
    "last_class": {
        "kind": LLM_EXTRACT,
        "cli_template": False,
        "llm_render": "if_template",
    },
}
