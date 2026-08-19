"""meeting 领域配置 —— 脚本与运行时共享的领域专属数据。

字段说明：
- ``STATE_CLASS``：生成骨架的 state 类型注解类名。
- ``LINE_CN_NAMES``：任务线中文名。
- ``LINE_KINDS``：任务线种类（手写）。渲染/CLI/sidecar/结构抽取由种类决定。
"""
from tools.runtime.kinds import DETERMINISTIC_PIPELINE, LLM_DOCUMENT, LLM_EXTRACT

# state 类型注解类名（生成骨架用）
STATE_CLASS = "MeetingState"

# ── 任务线中文名注册表（脚本与运行时共享的唯一来源）──────────────
# 新增任务线时 register_task.py 会自动在此追加一行（也可手动加）：
# "线名": "中文名"。中文名供 supervisor 上下文与日志使用，
# 草稿标题自动推导为 {中文名}草稿。
LINE_CN_NAMES: dict[str, str] = {
    "minutes_generation": "纪要",
    "action_items": "待办",
    "risk": "风险分析",
    "mindmap": "思维导图",
    "multi_styles": "多样式纪要",
    "minutes_trace": "溯源纪要",
}

# 任务线种类（手写，不进 sync_domain 生成区）。
# minutes_trace 是 deterministic_pipeline + sidecar，不是和 risk 对等的 3-step 线。
LINE_KINDS: dict[str, object] = {
    "minutes_generation": LLM_DOCUMENT,
    "action_items": {"kind": LLM_EXTRACT, "llm_render": "if_template"},
    "risk": {"kind": LLM_EXTRACT, "llm_render": "if_template"},
    "mindmap": LLM_DOCUMENT,
    "multi_styles": {"kind": LLM_DOCUMENT, "cli_mode": True},
    "minutes_trace": {"kind": DETERMINISTIC_PIPELINE, "sidecar": True},
}
