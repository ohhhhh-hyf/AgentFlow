# 个性化会议纪要多 Agent 系统

输入一份会议文本和一份用户画像，由五个 Agent 在后台协作，最终只展示该用户视角的会议纪要和本人待办。

完整的工作流、内存状态和输出校验设计见
[ARCHITECTURE.md](ARCHITECTURE.md)。

## 项目结构

```text
meeting_summary/
├── app.py                          # 唯一运行入口
├── examples/
│   ├── community_meeting.txt          # 小区活动会议
│   ├── property_manager_profile.json  # 物业负责人画像
│   └── volunteer_profile.json         # 居民志愿者画像
├── src/meeting_agent/
│   ├── agents/
│   │   ├── meeting_understanding_agent.py
│   │   ├── perspective_modeling_agent.py
│   │   ├── minutes_generation_agent.py
│   │   ├── action_items_agent.py
│   │   ├── final_integration_agent.py
│   │   └── schema_repair_agent.py
│   ├── client.py                  # DeepSeek API
│   ├── config.py                  # .env 配置加载
│   ├── models.py                  # 数据模型
│   ├── orchestrator.py            # LangGraph 内存图编排
│   ├── presenter.py               # 分析结果展示
│   ├── state.py                   # LangGraph 共享状态
│   └── validation.py              # 严格输出校验
├── .env                           # 本地 API Key
├── .env.example
└── pyproject.toml
```

## 配置

需要 Python 3.10 或更高版本。首次运行先安装项目：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

当前工作区已经创建 `.venv` 并安装好依赖。根目录 `app.py` 会自动切换到该虚拟环境，
日常运行不需要手动激活。

如果以后需要重建环境，而当前网络无法访问 PyPI 官方源，可使用：

```powershell
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

在 `.env` 中填写：

```text
DEEPSEEK_API_KEY=你的API-Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

## 运行

```powershell
python app.py
```

程序默认读取：

- `examples/community_meeting.txt`
- `examples/property_manager_profile.json`
- `examples/volunteer_profile.json`
- `.env`

同一份会议会分别以物业负责人和居民志愿者视角生成结果。如需更换输入，
修改根目录 `app.py` 顶部的 `MEETING_FILE`、
`PROFILE_FILES` 和 `ENV_FILE`。

程序最终只展示：

1. 一段完整的用户视角会议纪要
2. 按 `1. 2. 3.` 逐行编号的用户待办事项

每个 Agent 文件内都包含自己的 `SYSTEM_PROMPT` 和 `OUTPUT_CONTRACT`。
输出必须经过严格字段与类型校验；
不合规时原 Agent 自动重试，多次失败后由 `SchemaRepairAgent` 只修复格式。
未通过最终校验的数据不会进入下一个 Agent。

## LangGraph 状态

五个 Agent 通过 `MeetingState` 共享上下文。两层并行和最终汇合由
LangGraph `StateGraph` 管理。状态只存在于本次运行的内存中，程序结束后释放，
不会创建数据库或保存会议内容。

用户画像格式：

```json
{
  "name": "陈伟",
  "role": "开发工程师",
  "department": "研发部",
  "responsibilities": ["后端接口开发", "测试版本部署"],
  "interests": ["技术依赖", "开发排期"],
  "context": "重点关注上线风险"
}
```
