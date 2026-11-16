# Meeting Agent Service (Lightweight)

自包含、零旧依赖的现代极简会议智能体服务（v2.0）。

---

## 核心特性

### 1. 接口职责严格对齐与极速体验
- **纪要任务**：`POST /api/agent/v1/stream`，NDJSON 极速流式事件直出，首字到达时延（TTFT）压入 1.5 秒内；
- **待办任务**：`POST /api/agent/v1`，阻塞式返回带绝对时间的标准 JSON 数组；
- **双态待办推导**：
  - 传入会议时间 $\rightarrow$ 经过 Calendar 模块推导，产出并保存 `actions` 与 `actions_update`；
  - 未传会议时间 $\rightarrow$ 完全跳过 Calendar 推导（0ms），快速产出并保存 `actions`。

### 2. 高精度议题对齐系统（Agenda Alignment 2.0）
- **开场防抢跑双重守卫**：开场前 3 分钟或前 4 个文本块内有效拦截“念菜单/议程播报”导致的假切题；前序议题实质讨论字数积累不足 60 字时，强制抑制切题；
- **转折路标与双向回溯状态机**：支持正向中英文自然过渡路标（`下面看`、`首先看`、`接下来讨论`、`moving on to` 等）与反向回溯路标识别；支持跨阶段多块归集与动态最小未访问游标（`current_idx`）控制；
- **关键词 Grep 隐式过渡**：当讨论块长度 $\ge 30$ 字且匹配完整标题或 $\ge 2$ 个特征词时触发智能捕获，有效弥补口语化汇报中缺失显式路标的场景。

### 3. 全新 2.0 纪要模板体系与排版规范
- **视觉纯净化直出**：彻底禁绝行首 Markdown 无序列表符号（`- `、`* `、`+ `），杜绝全篇圆点 Bullet 点堆叠；
- **行内小标题与行形态层级**：规范要求主干行以加粗小标题（`**主项/事项名称**：核心事实`）领起，分支支撑细节换行独立成行，彻底消除二级标题（`##`）后单段黏连与大长句；
- **双轨议题纪要布局体系**：
  - **议题优先（`topic_major`）**：外层以现场审定议题为主线（`## 一. 议题全称`），内部固定输出三子栏（如 `### 工作进展`、`### 落实安排`、`### 未决风险`），内部细分小节自适应使用四级标题 `####`；
  - **列优先（`column_major`）**：栏目为一级标题（`# 核心政策`），内部按议题 1:1 展开二级大项（`## 一. 议题全称`），内部小节自适应执行 `+1 Level-Shift` 层级偏移（`###`）；
- **全场景中英 1:1 严格对齐**：覆盖政务报告、课堂实录、法庭庭审、专题讲座、团队例会、家校沟通、敏捷复盘等业务场景，普通纪要（`resources/templates/`）与议题纪要（`resources/agenda_templates/`）中英文双语 100% 镜像对齐。

### 4. 视觉议程智能识别与前置分类
- **纯 VLM 视觉议程抽取**：支持传入白板/屏幕议程图片（`docs`），自动抽取结构化议程单；识别失败或无有效议题时自动平滑降级为普通纪要；
- **智能模板内建必选（无开关）**：`template` 留空时自动检测；若识别出有效议题则候选集收敛为 20 个议题模板，否则为全量 29 个普通模板。

### 5. 健壮的工程基建与隔离安全
- **轻量后处理防护**：纯正则轻量后处理，强力防御大模型 Markdown 围栏代码块外溢与方括号指令残留；
- **用户级目录沙箱隔离**：产物按用户严格隔离至 `data/{user_id}/output/{request_id}/`，纪要仅保存 `minutes.md`，待办仅保存 `actions.json`；
- **隔离式英文日志系统**：外挂非侵入式 `LoggingMiddleware`，全量 `logs/service.log` 与核心诊断 `logs/diag.log` 双文件自动轮转；
- **全量自动化测试套件**：内置 65 个覆盖端到端、议题对齐、模板渲染、分类器与遥测监控的自动化用例，秒级快速回归。

---

## 快速开始

### 1. 安装依赖
```bash
pip install fastapi uvicorn requests openpyxl pydantic pytest
```

### 2. 配置环境
复制 `.env.example` 为 `.env` 并填写对应后端配置：
```bash
cp .env.example .env
```
配置示例（公网 API）：
```env
LLM_BACKEND=http
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```
若使用私有化 vLLM 服务器：
```env
LLM_BACKEND=vllm
LLM_VLLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_VLLM_API_KEY=EMPTY
LLM_VLLM_MODEL=deepseek-v4-flash-0731
```

### 3. 启动服务
```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. 运行全套测试
```bash
pytest tests/ -v
```

---

## 目录结构

```text
demo/
├── api_test/                     # 批量自动化跑测与时延评测脚本
│   ├── test.py                   # 同步阻塞接口评测
│   └── test_stream.py            # NDJSON 流式接口评测与 Excel 写回
├── resources/                    # 场景模板资产库
│   ├── templates/                # 普通纪要模板（zh / en 双语 1:1 镜像）
│   └── agenda_templates/         # 议题纪要模板（topic_major 与 column_major 布局）
├── tasks/                        # 核心智能体任务实现
│   ├── actions/                  # 待办任务流与 Calendar 推导流水线
│   ├── minutes/                  # 纪要任务流、提示词与后处理引擎
│   │   ├── agenda/               # 议题流水线（抽取、规划、对齐与渲染）
│   │   │   ├── alignment.py      # 议题对齐 2.0 核心状态机与路标匹配
│   │   │   ├── planner.py        # 议程规范化与编排规划
│   │   │   └── vision.py         # 视觉议程 VLM 识别
│   │   ├── prompts.py            # 纪要系统规则与排版约束
│   │   └── postprocess.py        # 纯净 Markdown 直出后处理
│   └── classifier.py             # 场景模板智能分类器
├── tests/                        # 单元测试与集成测试套件（65+ 用例）
├── main.py                       # FastAPI 入口与路由分发
└── pytest.ini                    # 自动化测试配置
```

---

## 接口调用契约（TaskRequest 标准格式）

### 请求体字段说明

```json
{
  "task": "minutes",
  "texts": {
    "transcript": "会议语音转写全文...",
    "keypoints": "",
    "notes": "",
    "vision_info": "",
    "actions_text": ""
  },
  "docs": [
    "议程板书.png"
  ],
  "extra": {
    "template": "general_minutes",
    "time": "2026/11/16 14:00",
    "agenda_plan": null
  },
  "lang": "zh"
}
```

* **Headers 约定**：
  * `X-User-Id`：用户标识（如 `1`）。`docs` 中的文件名会自动映射至 `data/{user_id}/docs/{filename}`；产物落盘至 `data/{user_id}/output/{request_id}/`。
  * `X-Request-Id`：全局链路追踪唯一 ID。
* **`texts` 字段说明**：
  * `transcript`：会议语音转写全文（纪要或待办的核心输入）；
  * `actions_text`：仅待办（`task="actions"`）消费的用户候选待办，纪要任务自动物理隔离；
  * `keypoints` / `notes` / `vision_info`：辅助线索与术语参考材料。
* **`extra` 字段说明**：
  * `template`：模板名称（留空自动触发智能分类器）；
  * `time`：会议召开时间（待办任务传时间自动走 Calendar 推导回填绝对日期，未传则跳过 Calendar）；
  * `agenda_plan`：直接注入结构化议程（强类型 `AgendaPlan` 契约，支持字典或 JSON 字符串）：
    - `meta`（选填）：`theme`（会议主题）、`attendees`（主持人/与会人）；
    - `items`（对象数组）：既定议程项列表。**仅 `title`（议题全称）为唯一核心必填**；`seq`（序号）、`presenters`（汇报人列表）、`time_range`（起止时段）均为选填，缺省自动编排补齐；
    - 兼容 VLM 团队直传扁平格式（`theme`, `attendees`, `agenda_items`）。
* **`lang` 字段说明**：
  * 语言选项：`"zh"`（默认）或 `"en"`，全链路自动选用对应语种提示词约束与双语模板资产。
