"""任务线中文名注册表 —— 脚本与运行时共享的唯一来源。

新增任务线时在此加一行即可：``"线名": "中文名"``。
``cn_name``（中文名）供 supervisor 上下文与日志使用，
``draft_title``（草稿标题）自动推导为 ``{中文名}草稿``。
"""

LINE_CN_NAMES: dict[str, str] = {
    "minutes_generation": "纪要",
    "action_items": "待办",
}
