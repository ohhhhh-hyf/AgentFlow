"""{{DOMAIN}} 领域配置 —— sync_domain.py 生成骨架/文案的领域专属数据。"""
# state 类型注解类名（生成骨架用）
STATE_CLASS = "{{STATE_CLASS}}"

# 渲染上下文骨架里"已批准{中文名}草稿"之前的 state 上下文行
# （完整代码行，缩进 12 空格；内容与 orchestrator.py 生成区逐字节一致）
RENDER_CONTEXT_STATE_LINES = [
    '            f"原文：\\n{state[\'transcript\']}\\n\\n"',
    '            f"用户画像：\\n{_json(state[\'user\'])}\\n\\n"',
    '            f"已审核用户视角：\\n{_json(state.get(\'perspective_profile\'))}\\n\\n"',
]

# ── 任务线中文名注册表（脚本与运行时共享的唯一来源）──────────────
LINE_CN_NAMES: dict[str, str] = {}
