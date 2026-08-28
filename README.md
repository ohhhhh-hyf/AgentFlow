# AgentFlow · 多 Agent 后端服务

会议纪要 / 知识点多 Agent 系统：多任务线并行流水线
（会议纪要 / 待办 / 风险分析 / 多样式纪要 / 溯源纪要 / 思维导图 / 知识图谱 / 笔记审查 / 自测题 / 资料入库 / 知识目录 / 复习清单），
每条线独立执行「生成 → 领域审核（+全局标准注入）→ 渲染」，互不阻塞；
支持客观视角与个人视角；可扩展任意新任务线。

纯后端服务：唯一入口为 **FastAPI**（`uvicorn app.main:app`），全部任务线通过 HTTP 接口调用
（接口文档见 [API.md](API.md)）。

LLM 支持 **HTTP（如 DeepSeek）**、**WebSocket OpenAI 兼容接口** 与 **vLLM** 三种后端（见 `.env`）。

## 项目结构

```
app/                          # FastAPI 后端服务（唯一入口）
  main.py                     # 应用入口：路由挂载 + /api/v1/health
  routes/{meeting,notes}.py   # 9 个业务接口路由
  tasks.py                    # 任务执行核心：请求 → 输入组装 → run() → 统一响应
  schemas.py                  # 请求/响应模型（通用 TaskRequest / TaskResponse）
  outputs.py                  # API 产物落盘 data/{user_id}/output/{request_id}/
  requirements.py             # 各接口必填字段声明表
domain/
  meeting/                    # 会议域
    domain_config.py          # 领域配置：STATE_CLASS / LINE_CN_NAMES / LINE_KINDS
    models.py                 # 数据模型 + 各线生成模型/审核模型（生成区）
    reports.py                # 全部任务线最终输出 Report 类（手写区）
    orchestrator.py           # 多线并行图 + 节点 + run/run_streaming
    meeting_factory.py        # Agent 依赖组装工厂
    meeting_core/             # 核心层：会议理解（客观事实底座）
    tasks/{minutes,actions,risks,mindmap,minutes_styles,minutes_trace}/
      contracts.py / prompts.py / steps/{agent,supervisor,render}
  notes/                      # 笔记域：graph/review/quiz/library/catalog/checklist
client/                       # LLM 客户端（HTTP / WebSocket / vLLM）+ 配置（.env）
perspective/                  # 跨 domain 公共视角建模 + profiles/（客观画像 + 职业模板）
supervisor/                   # 全局监督标准（prompt 注入，不单独调 LLM）
tools/
  core/                       # 共享编排内核：domain_engine（图节点 mixin）/ runner（run）/ io
  runtime/                    # 渲染运行时：render / context / kinds / supervisor_slice
  template_router/            # 模板路由：判型 / 占位填充 / 门禁 / 可读化
  exports/                    # 产物落盘：outputs / knowledge_graph / mindmap
  memory/                     # 跨会话记忆：记录累积 / 语义检索 / 引用标注 / 图谱增量
  knowledge/                  # 知识库：PPT/PDF/docx/xlsx 入库 + 向量检索 + 出处（RAG）
  ocr/                        # OCR 引擎适配（serverocr / rapidocr / paddleocr）
  monitor/                    # 任务监控：token / 缓存命中 / 按层耗时
  exercise_search/            # 高中题库检索（notes.quiz 用）
  scripts/                    # 开发工具：sync_domain / register_task 代码生成器
  contracts.py 等             # 契约 DSL / 校验 / fallback 规则 / prompt 构建（兼容入口）
samples/                      # 样例输入：samples/{domain}/file/、profile/、{task}_template/
template/                     # 模板注册表（cm_template_v2_changed_0722.yaml 的可读副本）
```

## 快速开始

### 1. 环境准备

```bash
# Python >= 3.10，安装依赖
pip install -r requirements.txt
```

> 开发/测试请优先使用 **Python 3.10** 环境（项目部分语法在 ≤3.11 下才能被完整校验）。

Linux 推荐配置：

| 目的 | Ubuntu / Debian | CentOS / RHEL / Fedora | 验证命令 |
|---|---|---|---|
| Python 运行环境 | `sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv` | `sudo dnf install -y python3 python3-pip` | `python3 --version` |
| 思维导图 HTML | `sudo apt-get install -y nodejs npm` | `sudo dnf install -y nodejs npm` | `node -v && npx -v` |
| 思维导图 PNG | `python3 -m playwright install --with-deps chromium` | `python3 -m playwright install chromium` | `python3 -m playwright --version` |

可选前置（按需）：

```bash
# 思维导图 HTML 导出需要 Node.js（npx 首次自动下载 markmap-cli，无需全局安装）
# 思维导图 PNG 导出还需要浏览器内核：
python -m playwright install chromium
```

### 2. 配置 LLM（`.env`）

在项目根目录创建 `.env`，三选一后端：

#### 方式 A：HTTP（DeepSeek 等）

```
LLM_BACKEND=http
DEEPSEEK_API_KEY=sk-你的Key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEMPERATURE=0.0
```

#### 方式 B：WebSocket（OpenAI Chat Completions 兼容）

```
LLM_BACKEND=websocket
LLM_WS_URL=ws://host:port/llm/websocket/openai/chat/completions
LLM_WS_API_KEY=你的Key
LLM_WS_MODEL=你的模型名
# 可选：LLM_WS_SENDER / LLM_WS_USER / LLM_WS_TEMPERATURE / LLM_WS_MAX_TOKENS 等
```

依赖 `websockets`（已在 `requirements.txt` 中）。内网请保证机器能访问 `LLM_WS_URL`（`ws://` 或 `wss://`）。

#### 方式 C：本地 vLLM（OpenAI 兼容 HTTP）

```
LLM_BACKEND=vllm
LLM_VLLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_VLLM_API_KEY=你的BearerToken
LLM_VLLM_MODEL=deepseek-v4-flash-0731
```

### 3. 启动服务

```bash
cd /path/to/AgentFlow
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# 可选：思维导图 PNG
python -m playwright install chromium
```

启动：

| 场景 | 命令 |
|---|---|
| 本机测试 | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| 交互文档 | `http://127.0.0.1:8000/docs`（Swagger UI）/ `/redoc` |
| 后台运行 | `nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > app.log 2>&1 &` |

OCR 引擎（`.env` 的 ``OCR_ENGINE``，三种互不兜底）：

```env
# serverocr | rapidocr | paddleocr
OCR_ENGINE=paddleocr
PADDLE_OCR_DEVICE=gpu:0
PADDLE_OCR_DET_MODEL=PP-OCRv5_server_det
PADDLE_OCR_REC_MODEL=PP-OCRv5_server_rec
# PADDLE_OCR_CUDA_VISIBLE_DEVICES=2
```

```bash
# RapidOCR（CPU 本地）
pip install "numpy<2" onnxruntime==1.16.3 rapidocr_onnxruntime==1.4.4

# PaddleOCR 3.x / PP-OCRv5
# 按 Paddle 官方安装 GPU/CPU 版 paddleocr
```

| 项目 | 说明 |
|---|---|
| `.env` | HTTP 至少配置 `DEEPSEEK_API_KEY`；WebSocket 配置 `LLM_BACKEND=websocket` + `LLM_WS_*` |
| 端口 | 云服务器需开放安全组 / 防火墙（如 `8000`） |
| 反代 | 若用 Nginx，需放行 WebSocket（`Upgrade` / `Connection`） |
| 产物 | API 产物写入 `data/{user_id}/output/{request_id}/`；CLI 归档写入 `output/{domain}/{task}/` |
| 知识图谱 | HTML 可交互演示 |
| 思维导图 | HTML 需 Node.js/npx；PNG 需 Playwright Chromium |

样例与数据目录：

| 目录 | 用途 |
|---|---|
| `data/{user_id}/docs/` | 接口 `docs[]` 的输入文件（图片/文档/笔记） |
| `samples/{domain}/file/` | 样例输入文本 `.txt` |
| `perspective/profiles/` | 跨域公共画像（客观 + 职业模板）`.json` |
| `samples/{domain}/{task}_template/` | 任务模板样例 `.md` |
| `data/{user_id}/output/{request_id}/` | API 每次调用产物（`result.md` / `result.html`） |
| `data/{user_id}/memory/` | 跨会话记忆（records + chromadb 索引） |
| `data/{user_id}/knowledge/` | 知识库向量 + 知识目录 JSON |
| `output/{domain}/{task}/` | CLI 归档产物（时间戳命名） |

## 接口调用

全部 9 个业务接口 + 健康检查，请求/响应结构统一，详见 **[API.md](API.md)**：

| 域 | 接口 | 用途 |
|---|---|---|
| meeting | `POST /api/v1/meeting/minutes` | 会议纪要提取 |
| meeting | `POST /api/v1/meeting/actions` | 待办提取 |
| meeting | `POST /api/v1/meeting/risks` | 风险识别 |
| meeting | `POST /api/v1/meeting/minutes_styles` | 多样式纪要 |
| meeting | `POST /api/v1/meeting/minutes_trace` | 溯源纪要 |
| notes | `POST /api/v1/notes/graph` | 知识图谱（学习地图 + 交互 HTML） |
| notes | `POST /api/v1/notes/library` | 资料入库 |
| notes | `POST /api/v1/notes/catalog` | 知识目录 |
| notes | `POST /api/v1/notes/checklist` | 复习清单 |
| - | `GET /api/v1/health` | 健康检查 + 任务线清单 |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/meeting/minutes \
  -H "Content-Type: application/json" \
  -H "X-User-Id: u1" \
  -d '{"texts": {"transcript": "会议记录全文……"}}'
```

任务线：

| 领域 | 任务线 | 输出内容 | 主要产物 |
|---|---|---|---|
| `meeting` | `minutes` | 会议纪要 | `output/meeting/minutes/result_*.md` / `.html` |
| `meeting` | `actions` | 待办事项 | `output/meeting/actions/result_*.md` |
| `meeting` | `risks` | 风险分析 | `output/meeting/risks/result_*.md` |
| `meeting` | `minutes_styles` | 多样式纪要 | `output/meeting/minutes_styles/result_*.md` |
| `meeting` | `minutes_trace` | 溯源纪要 | `output/meeting/minutes_trace/result_*.md` / `.html` |
| `meeting` | `mindmap` | 思维导图 | `output/meeting/mindmap/mindmap_*.png` / `.html` |
| `notes` | `graph` | 知识图谱 | `output/notes/graph/graph_*.html` / `.md` |
| `notes` | `review` | 笔记审查 | `output/notes/review/result_*.md` / `.html` |
| `notes` | `quiz` | 自测题（推理题 + 高中题库真题） | `output/notes/quiz/result_*.md` / `.html` |
| `notes` | `library` | 资料入库（信息熵报告） | `output/notes/library/result_*.md` |
| `notes` | `catalog` | 知识目录 | `output/notes/catalog/result_*.md` |
| `notes` | `checklist` | 复习清单 | `output/notes/checklist/result_*.md` / `.html` |

输出归档规则：

| 目录 | 内容 | 说明 |
|---|---|---|
| `output/{domain}/{task}/result_时间戳.md` | 最终文本 / 大纲 | 除 `mindmap` / `graph` 外，仅当该任务线有文本正文或 Markdown 大纲时保存；模板门禁失败时改写为 `result_时间戳_rejected.md` |
| `output/{domain}/{task}/result_时间戳.html` | 页面版 | 仅以下线生成：`minutes`（记忆对照页/纯文本页）、`minutes_trace`（同 minutes）、`review` / `quiz` / `checklist`（各自交互页）；`actions` / `risks` / `minutes_styles` / `library` / `catalog` 不生成 |
| `output/meeting/mindmap/mindmap_时间戳.html` | 思维导图 HTML | `mindmap` 目录只保留 HTML/PNG |
| `output/meeting/mindmap/mindmap_时间戳.png` | 思维导图 PNG | `mindmap` 目录只保留 HTML/PNG；Playwright 不可用时跳过 |
| `output/notes/graph/graph_时间戳.html` | 知识图谱交互 HTML | Cytoscape.js 交互演示版 |
| `output/notes/graph/graph_时间戳.md` | 学习地图 | 按主题分组的文本学习路径 |

## 自定义输出模板

接口 `extra.template` 支持 29 个预设模板（见 API.md 4.5），也可通过 `TEMPLATE_ROUTER` 机制处理自定义模板。模板支持三种形式，系统**自动判型**处理：

| 形式 | 示例 | 处理方式 |
|---|---|---|
| **占位符模板** | `# [会议主题]` / `\| [任务] \| [负责人] \|` | 固定文字逐字符保留，LLM 只填占位符 |
| **格式规范模板** | 格式说明 + 输入/输出示例（如 JSON 数组） | 指令/示例分离，示例作 few-shot |
| **自然语言描述** | "第一行是标题，括号里跟时间和人物" | LLM 先编译成占位符模板再填充 |

开关：环境变量 `TEMPLATE_ROUTER=off` 关闭模板路由，恢复旧行为。

## 新增任务线（如"风险管理"）

手写 4 处 + 命令 4 条（以线名 `xxx`、中文名 `xxx` 为例）：

```
① 手写 domain/meeting/tasks/xxx/contracts.py      # 生成/审核契约 + 降级规则
② python tools/scripts/register_task.py --domain meeting --task xxx --name "中文名"
   # 自动：注册中文名 + steps/ 三件套 + 工厂 import + 占位校验类
③ 手写 domain/meeting/tasks/xxx/prompts.py         # 4 个 prompt 常量
④ reports.py 末尾追加 XxxReport 类（继承 ModelMixin, XxxReportValidation）
⑤ python tools/scripts/sync_domain.py --domain meeting   # 全量生成 → SUCCESS!
⑥ python tools/scripts/sync_domain.py --domain meeting --check   # 校验 → SUCCESS!
⑦ 在 app/routes/ 注册对应接口路由（参考现有路由）
```

## 架构要点

- **多线并行**：各任务线监督返工闭环（approve/revise≤1次/reject→降级），互不阻塞
- **契约驱动**：每条任务线的模型/校验/装配由 `contracts.py` 声明，`sync_domain.py` 生成
- **生成区**：`models.py` / `orchestrator.py` / `meeting_factory.py` 的生成区由脚本管理
  （`--write` 重写、`--check` 校验），手写区（contracts/prompts/reports 类）脚本不碰
- **全局标准注入**：`supervisor/` 的全局标准经 `GlobalSupervisor.build_prompt` 注入各线 supervisor
- **占位校验**：register 阶段预生成 `XxxReportValidation: pass`，写 Report 类无 NameError，
  sync_domain 全量后按字段生成真实校验
- **模板路由**：`tools/template_router/` 包自动判型三类模板并分派最优处理，
  任何失败回退旧路径；渲染输出附带只读校验（残留占位符/JSON 合法性）
- **结构化输出加固**：`client/llmclient.py` 的 `structured()` 对截断输出做程序修复
  （括号栈补全保留有效数据），非截断校验错误最多一次针对性重试，不再依赖 repair 兜底
- **思维导图**：mindmap 线产出 Markdown 大纲，经 `tools/mindmap.py` 固定导出
  交互式 HTML（markmap，离线单文件）和 PNG 图片（Playwright 截图）；
  npx/playwright 缺失时自动降级不影响主流程
- **知识图谱**：notes 域 graph 线提取概念节点与关系边（nodes/edges，
  均锚定原文 + evidence），经 `tools/graph.py` 导出 Cytoscape.js 交互式 HTML 和学习地图 Markdown（默认输出到 `output/notes/graph/`）；悬空边自动过滤、HTML 仍尽量生成；
  传 `X-User-Id` + `extra.subject` 时按学科跨会话增量（新增节点高亮，见 API.md 6.6）
- **输出稳定性**：各线 prompt 采用确定性规则（数量由内容决定、措辞锚定原文、
  顺序按原文出现、空字段 null/[]），同一输入重复运行保持内容与篇幅稳定
