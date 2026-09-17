"""{{DOMAIN}} 领域配置 —— 脚本与运行时共享的领域专属数据。

渲染上下文由 DomainNodes 钩子拼装。LINE_KINDS 决定渲染/CLI/sidecar/结构抽取。
"""
# state 类型注解类名（生成骨架用）
STATE_CLASS = "{{STATE_CLASS}}"

# ── 任务线中文名注册表（脚本与运行时共享的唯一来源）──────────────
LINE_CN_NAMES: dict[str, str] = {}

# 任务线种类（手写）。取值见 tools.runtime.kinds。
LINE_KINDS: dict[str, object] = {}
