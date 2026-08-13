"""meeting 领域配置 —— sync_domain.py 生成骨架/文案的领域专属数据。

脚本不再硬编码任何领域：每个领域在 ``domain/<name>/domain_config.py``
提供自己的配置，脚本按配置生成。meeting 是第一个配置实例。

字段说明：
- ``STATE_CLASS``：生成骨架的 state 类型注解类名（如 NotesState）。
- ``RENDER_CONTEXT_STATE_LINES``：渲染上下文骨架里"已批准{中文名}草稿"之前的
  state 上下文行（完整代码行，原样拼入 return 块，缩进为 12 空格）。
"""

# state 类型注解类名（生成骨架用）
STATE_CLASS = "MeetingState"

# 渲染上下文骨架里"已批准{中文名}草稿"之前的 state 上下文行
# （完整代码行，缩进 12 空格；内容与 orchestrator.py 生成区逐字节一致）
RENDER_CONTEXT_STATE_LINES = [
    '            f"会议原文：\\n{state[\'transcript\']}\\n\\n"',
    '            f"用户画像：\\n{_json(state[\'user\'])}\\n\\n"',
    '            f"已审核会议理解：\\n{_json(state.get(\'meeting_understanding\'))}\\n\\n"',
    '            f"已审核用户视角：\\n{_json(state.get(\'perspective_profile\'))}\\n\\n"',
]

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
