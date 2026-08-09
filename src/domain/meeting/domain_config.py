"""meeting 领域配置 —— sync_contracts.py 生成骨架/文案的领域专属数据。

脚本不再硬编码任何领域：每个领域在 ``src/domain/<name>/domain_config.py``
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
