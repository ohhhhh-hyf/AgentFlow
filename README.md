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
  tasklines.py                # 任务线声明（域 → 线名 / 产物端点）：接口清单的唯一来源
  routes/agent.py             # 统一入口 /api/agent/v1（同步 / 流式 / 下载；域与线名走请求体）
  routes/_registry.py         # 按声明注册一个域的产物预览路由（唯一仍需域/线名在路径上的形态）
  routes/{meeting,notes}.py   # 两条域的预览路由入口（薄封装，只调用 register_domain）
  routes/tasks.py             # 异步任务接口：提交 / 状态 / 结果 / 事件流（Redis）
  routes/_file_endpoints.py   # 产物文件端点（指定文件名下载 / 预览）
  executor.py                 # 异步任务执行体：inline 与 worker 两种模式共用
  worker.py                   # 独立 worker：队列消费 / 并发槽 / 心跳租约 / 超时回收 / 优雅停机
  job_store.py                # Redis 任务状态、事件流、载荷、队列与租约（TTL 默认 7 天）
  id_worker.py                # request_id / job_id 发号器（Redis 日序号，无 Redis 时进程内降级）
  tasks.py                    # 任务执行核心：请求 → 输入组装 → run() → 统一响应
  schemas.py                  # 请求/响应模型（TaskRequest / DomainTaskRequest / TaskResponse）
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
  meeting/hooks.py            # 会议域钩子（记忆 v2 / 各线产物 HTML / 无模板收尾压缩）
  meeting/memory/             # 会议跨场记忆：registry / 场次状态 / 注入 / 记忆 HTML
  notes/                      # 笔记域：graph/review/quiz/library/catalog/checklist
    hooks.py                  # notes 域钩子（记忆：归属解析 + 图注入/回写）
    memory/                   # notes 记忆实现（graph 线）：resolve / 图合并 / 注入回写
    knowledge/                # notes 知识库门面（RAG）：KnowledgeTool / 出处引用 / rag
    exercise_search/          # 高中题库检索（quiz 线用）
tools/llm/                    # LLM 客户端（HTTP / WebSocket / vLLM）+ 配置（.env）
perspective/                  # 跨 domain 公共视角建模（代码；画像数据见 assets/profiles/）
domain/_shared/               # 全局监督标准（prompt 前缀注入各线 supervisor，不单独调 LLM）
tools/
  schema/                     # 契约 DSL（contracts）/ fallback 规则 / 结构化输出校验
  core/                       # 共享编排内核：domain_engine / runner / io / runtime_context / profiles /
                              #   prompt_utils / domain_hooks（域钩子协议，引擎据此取域能力）
  execution/                  # 硬执行规则：上游对齐 / 表行截断 / 验收门禁
  runtime/                    # 渲染运行时：render / context / kinds / supervisor_slice
  templates/                  # 模板子系统：渲染 prompt / 评测 / 篇幅预算 + router/（判型、占位填充、门禁）
  exports/                    # 产物落盘编排（outputs.py）+ html/（各线 HTML/交互渲染器）
  memory/                     # 记忆/向量共享底座：落盘布局 / 实体抽取 / 记忆向量索引（两个域共用）
  knowledge/                  # 通用知识底座：文件 → 文本 / 向量库封装 / 存储配置 / 资料角色
  ocr/                        # OCR 引擎适配（serverocr / rapidocr / paddleocr）
  monitor/                    # 任务监控：token / 缓存命中 / 按层耗时
  codegen/                    # 代码生成器：sync_domain / register_domain / register_task + domain_template/
  devtools/                   # 手工运维脚本：check_user_profile / purge_kb_source
tests/                        # 零 LLM 自测套件（见「自测」一节；python -m tests）
assets/profiles/              # 画像注册表（客观全员 + 6 个职业模板），运行时直接读 *.json
template_v2/ template_v3/     # 模板注册表（运行时直接读 *.md）：生效目录由 AGENTFLOW_TEMPLATE_DIR 决定
                              # （.env 当前指向 template_v3，30 类）；未配置/目录缺失时回落内置 template_v2
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

#### 日志（落盘 + 诊断专用文件）

服务启动后自动写两份日志（都在仓库根 `logs/` 下，按大小轮转；`.gitignore` 已忽略该目录）：

| 文件 | 内容 | 用途 |
|---|---|---|
| `logs/agentflow.log` | 全部 INFO 及以上 | 常规排查 |
| `logs/diag.log` | **只装诊断行**：LLM 调用/响应（含 `finish_reason`、token 数、输入估算）、审核结论与理由、路由去向、降级汇总、任何 WARNING+ | **排查"生成有误/降级"时直接把这个文件给出去** |

可用环境变量调整（都可省）：

```dotenv
AGENTFLOW_LOG_FILE=logs/agentflow.log     # 设空字符串可关闭文件输出
AGENTFLOW_DIAG_LOG_FILE=logs/diag.log
AGENTFLOW_LOG_LEVEL=INFO                  # DEBUG/INFO/WARNING/ERROR
AGENTFLOW_LOG_MAX_MB=20                   # 单文件上限（超限轮转）
AGENTFLOW_LOG_BACKUPS=5                   # 轮转保留份数
```

#### Redis（异步任务接口依赖，同步接口不需要）

`POST/GET /api/v1/tasks` 系列把任务状态与事件流放在 Redis。容器方式启动（AOF 持久化 +
开机自启；`-p 6379:6379` 对所有网卡开放，只给本机 API 用可改成 `-p 127.0.0.1:6379:6379`）：

```bash
docker run -d --name redis --restart unless-stopped \
  -p 6379:6379 \
  -v /data/redis:/data \
  redis:7.2 \
  redis-server --appendonly yes

docker exec -it redis redis-cli ping      # 期望 PONG
```

> `--name` 的容器名只用于本机 docker 命令（`exec` / `logs` / `stop`），API **不依赖**它：
> 连接只认 `REDIS_URL` 的 host:port/库号，所以本机叫 `agentflow-redis`、服务器叫 `redis`
> 都没问题，只要 `docker exec` 里跟着换成自己的名字即可。
> 只有当 API 也被容器化、和 Redis 处于同一个自定义 Docker 网络时，容器名才会被当作主机名解析
> （那时才写 `REDIS_URL=redis://<容器名>:6379/0`，且容器内的 `127.0.0.1` 不再指向宿主机）。

`.env` 中对应配置（缺省即本机 0 号库；换机 / 换库 / 加密码时改这里）：

```env
REDIS_URL=redis://127.0.0.1:6379/0
# 任务状态与事件流的过期秒数，默认 7 天
#AGENTFLOW_JOB_TTL_SECONDS=604800
```

#### 异步任务的两种执行模式

`POST /api/v1/tasks` 提交的任务由 `.env` 的 `AGENTFLOW_RUN_MODE` 决定在哪执行：`inline`（默认，API 进程内跑）
或 `queue`（推 Redis 队列，由 `python -m app.worker` 消费）：

```bash
# .env: AGENTFLOW_RUN_MODE=queue
uvicorn app.main:app --host 0.0.0.0 --port 8000      # 只负责受理与查询，可多实例
python -m app.worker --concurrency 4 --grace 300     # 执行侧，可多开/多机
```

Redis 不可用时异步接口返回 503（`{"code": 503, "message": "Redis 不可用（<url>）：…"}`），同步接口不受影响。
四个接口（提交 / 状态 / 结果 / 事件流）返回**同一份"任务快照"**（`code` / `job_id` / `request_id` /
`status` / `message` / `text` / `file_name` / `monitor`），字段含义与示例见 [API.md](API.md) 3.2。

> 键结构、队列与租约机制、重试与停机语义、可观测性、调参与运维注意，全部见
> **[异步任务与 Redis（队列 / 租约 / 重试）](#异步任务与-redis队列--租约--重试)** 一节。

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

**日志格式**：统一为 `时间戳 级别 模块 消息`（`tools/core/logging_config.py`），API 与 worker 共用同一套；
uvicorn 自身的日志（含 access log）也并进这套格式，不再出现两种前缀混排。消息统一是**英文短句**、
`key=value` 风格（如 `pipeline start lines=minutes`、`llm call label=minutes/agent mode=structured`、
`job done job=job_… attempt=1 dur=7.4s`），便于 grep 与按字段取值；
面向调用方的报错文案（`ApiError.message`，见 [API.md](API.md)）仍是中文，属接口契约、不随日志变化。

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

**图片 OCR 的并发**：`docs` 里的多张图片会**并发识别**（结果按传入顺序拼接，单张失败只降级跳过），
并发路数复用 OCR 引擎的并发配置 —— Paddle 看 `PADDLE_OCR_POOL_SIZE`（默认 4，GPU 上限 4 / CPU 上限 8），
其他引擎看 `OCR_PARALLEL`（默认 4，上限 8）。每张图通常还要一次 LLM 重构调用（数秒），
所以并发度上调时留意**同时打给模型的请求数**；日志首行会打印实际路数
（`[OCR] 使用引擎 paddleocr，共 N 张，4 路并行`）。

**页眉/页脚剔除（逐图自适应，`tools/ocr/layout.py`）**：笔记照片上的印刷页眉页脚（校名、
地址电话、印刷编号、页号）如果漏进正文，会被下游当标题，进而长成目录里的假章节——所以识别后
按**每张图自己的行高中位数**判定：行高 ≥ 中位行高 1.6 倍（印刷校名实测 1.6–3.5 倍，正文 1.0–1.3 倍）
或命中机构/联系类文本、纯大写拉丁短行、纯数字编号，且落在该图正文范围的上下 12% 边缘带内，
就从边缘向内**连续**丢弃，遇到第一条"明显正文行"立刻停手。整簇里至少要有一条命中上述强特征
才允许丢弃（宁漏不误杀），单侧丢弃还有行数上限。命中行标 `role_hint=boilerplate`，
`reconstruct` 的正文拼接、LLM 输入、OCR 复核窗口、行完整性报告四处都会跳过它。
日志会逐图打印丢弃条数与内容：`page chrome: 12/35 lines dropped as header/footer (...)`。
怀疑误杀可临时设 `OCR_PAGE_CHROME=0` 整体回退（跨页去噪那一道不受影响）。

**OCR / 整理产出的收尾**（`tools/ocr/mathmd.py`）：每次整理或审校输出都会过一遍
`normalize_markdown_math()` —— 先删掉**模型偶发抄进正文的渲染器报错串**（如
`ParseError: KaTeX parse error: Expected '}', got 'EOF' at end of input: …`，模型被要求处理公式定界时偶尔会把报错当说明写出来），
再修 `$`/`$$` 定界与不成对的 `\left`/`\right`。正常内容不受影响（正文里讨论 KaTeX、
编程笔记里的「ParseError: 具体内容」示例都会原样保留）。

| 项目 | 说明 |
|---|---|
| `.env` | HTTP 至少配置 `DEEPSEEK_API_KEY`；WebSocket 配置 `LLM_BACKEND=websocket` + `LLM_WS_*` |
| 端口 | 云服务器需开放安全组 / 防火墙（如 `8000`） |
| 反代 | 若用 Nginx，需放行 WebSocket（`Upgrade` / `Connection`） |
| 产物 | API 产物写入 `data/{user_id}/output/{request_id}/`；CLI 兜底写入 `data/{user_id}/output/cli_*/`（无根目录归档层） |
| 知识图谱 | HTML 可交互演示 |
| 思维导图 | HTML 需 Node.js/npx；PNG 需 Playwright Chromium |

数据目录：

| 目录 | 用途 |
|---|---|
| `data/{user_id}/docs/` | 接口 `docs[]` 的输入文件（图片/文档/笔记） |
| `assets/profiles/` | 跨域公共画像（客观 + 职业模板）`.json` |
| `data/{user_id}/output/{request_id}/` | API 每次调用产物（`result.md` / `{task}.html`） |
| `data/{user_id}/memory/` | 跨会话记忆（records + chromadb 索引） |
| `data/{user_id}/knowledge/` | 知识库向量 + 知识目录 JSON |
| `data/{user_id}/ocr/{学科}/` | OCR 合并稿（**仅 `library` 资料入库落盘**，文件名 `ocr_{时间戳}.md`）；其它任务线的图片 OCR 只在内存里参与本次任务，不落盘 |
| `data/monitor/` | 任务监控 JSON（CLI monitor 开启时） |

## 自测（零 LLM，秒级、不花钱）

`tests/` 下的六个套件只覆盖"程序说了算"的部分——契约不变量、硬执行规则、模板解析与
门禁方向、画像选档、记忆状态机，以及"某条纪律必须出现在发给模型的文本里"这类提示词断言；
凡是需要模型判断的一律不测（所以都叫"零 LLM"）。提示词断言是刻意的：防止有人把纪律误删或改漂。

```bash
python -m tests                        # 全部套件：逐个打印 pass/fail + 汇总一行，失败退出码 1
python -m tests.test_template_router   # 单跑一个套件（排查问题时更省事）
```

| 套件 | 覆盖 |
|---|---|
| `tests/test_core.py` | 画像选档（`profile=user` → `data/{uid}/user.json`）、清洗、职业模板合并 |
| `tests/test_template_router.py` | 模板判型、占位识别、门禁方向、各线提示词的关键不变量（最大的一套） |
| `tests/test_meeting_memory.py` | 会议记忆：身份绑定、跨场状态机、时间与场次 |
| `tests/test_perspective.py` | 视角建模：偏好块 / 称呼表 / 命中表 / 原文按人裁剪 / 人名口径 |
| `tests/test_draft_scrape.py` | 草稿/原文抽取：各线 `*_from_context` 与共享实现的 marker 一致性 |
| `tests/test_engine_smoke.py` | 引擎/app 层冒烟（桩系统、零 LLM）：prepare_run → run → 落盘 → 记忆钩子 |

改完代码至少跑 `python -m tests`；动到生成区（contracts、TASK_LINES）再加
`python tools/codegen/sync_domain.py --domain meeting --check`（notes 域同理）。

## 异步任务与 Redis（队列 / 租约 / 重试）

`POST/GET /api/v1/tasks` 是生产主路径：提交立即返回 `job_id`，任务状态、事件流、输入载荷、待执行队列与
执行租约**全部放在 Redis**（进程重启不丢）。只用同步 / 流式接口时不需要 Redis。
相关代码：[app/job_store.py](app/job_store.py)（Redis 存取）、[app/executor.py](app/executor.py)（执行体）、
[app/worker.py](app/worker.py)（独立 worker）、[app/config.py](app/config.py)（参数）。

### 1. 两种执行模式

| 模式 | 提交后发生什么 | 适用 |
|---|---|---|
| `inline`（默认） | 写状态后交给**本 API 进程**的 BackgroundTasks 执行；不入队、不建租约、失败即终态（无重试） | 本地开发、小文本测试、兼容旧调用 |
| `queue` | 写状态 + 存载荷 + `LPUSH` 入队，**立刻返回**；由独立 worker 进程消费 | 生产主路径：并发可控、失败可重试、重启不丢任务 |

`queue` 模式下必须至少有一个 `python -m app.worker` 在跑，否则任务会一直停在 `queued`（`LLEN agentflow:queue` 能看到）。
当前模式从 `GET /api/v1/health` 的 `run_mode` 读（提交响应里没有这个字段）；`.env` 非法取值一律回落 `inline`。

> 回滚注意：从 `queue` 切回 `inline` 前先让 worker 把队列排空，否则队列里的任务不会有人处理。

### 2. Redis 键一览

| 键 | 类型 | TTL | 作用 |
|---|---|---|---|
| `agentflow:job:{job_id}` | Hash | 7 天 | 任务状态：`status`/`phase`/`message`/`error`/`attempts`/`worker_id`/`heartbeat_at`/`token_usage`/`cache_hit`/`file_name`/`result`（`result` 在状态接口里被剔除） |
| `agentflow:job:{job_id}:events` | List | 7 天 | 事件流，每行一个 JSON：`queued`/`started`/`phase`/`chunk`/`done`/`error`/`requeued`；`GET /stream?cursor=N` 按下标增量读（可断线重连） |
| `agentflow:job:{job_id}:payload` | String | 7 天 | 请求体 JSON。worker 与 API 是不同进程，输入必须能通过 Redis 传递（含 `texts`/`docs`/`extra`/`time`） |
| `agentflow:queue` | List | 随出队消失 | 待执行队列：`LPUSH` 入队 / `BRPOP` 出队 → **先进先出**；只放 `job_id`（不放正文，重投便宜、`LLEN` 语义干净） |
| `agentflow:leases` | ZSet | 无（完成后移除） | 执行租约：member=`job_id`、score=租约到期时间戳；心跳续期、超时回收。`ZCARD` 即当前在跑任务数 |
| `agentflow:id:global:{YYYYMMDD}` | String | 3 天 | `request_id` / `job_id` 的当日序号（Redis `INCR`，跨进程不重号；Redis 不可用时退化为进程内计数） |

`.env` 的 `AGENTFLOW_JOB_TTL_SECONDS` 控制前三个键的过期时间（默认 604800 秒 = 7 天）。

### 3. 一条任务的生命周期

```
提交 ──► queued ──► running ──┬──► succeeded
           ▲                  ├──► failed        （不可重试 / 重试次数用尽）
           │                  └──► requeued ──┐   （可重试失败 / worker 失联）
           └──────────────────────────────────┘
```

| 阶段 | Redis 侧动作 |
|---|---|
| 提交 | `HSET` 状态（`status=queued`、`attempts=0`）+ `SET` 载荷 + `LPUSH` 队列 + `RPUSH` `queued` 事件 |
| 认领 | `BRPOP` 取到 → **状态守卫**（状态不是 `queued` 就跳过，防重复投递）→ `HINCRBY attempts 1` → 状态改 `running` → `ZADD` 登记租约 → `RPUSH` `started` 事件 |
| 执行中 | 每个 `phase`/`chunk` 事件更新 `phase`/`message` 并**追加进事件流**（`/stream` 靠它回放增量文本、断线重连不丢） |
| 成功 | `RPUSH` `done` 事件 → 再翻状态为 `succeeded`（顺序刻意如此：反过来会让 `/stream` 提前退出、客户端拿不到最终结果）→ `ZREM` 释放租约 |
| 失败 | `RPUSH` `error` 事件（带真实 `code`）→ 按重试策略重排或判 `failed` → 释放租约 |

`status` 取值：`queued` / `running` / `succeeded` / `failed`（`cancelled` 已在事件流退出条件里预留，暂无接口设置）。
`message` 取值：`queued` / `running` / `running:{阶段}` / `rendering` / `success` / `failed` / `requeued(attempt N)`。

### 4. 并发上限

`--concurrency N` 表示一个 worker 进程内开 **N 个执行槽**，每个槽是一个 asyncio 协程：空闲时才去 `BRPOP`
取任务，**取到即执行**（不会出现"任务已从队列取走、却在等 CPU"的中间态）。因此：

- **全局并发 = 所有 worker 的槽位之和**，`ZCARD agentflow:leases` 就是它的实时值；
- 超出并发上限的提交不会失败，而是**排队**（`queued` 真的在等，`LLEN agentflow:queue` 即积压量）；
- 单节点建议 4~8 槽：任务以等 LLM 为主（实测一条 minutes 约 10 秒，CPU 时间占比很低），再往上会先撞
  渲染/OCR 的 CPU 上限。多进程（多起几个 worker）与单进程多槽效果等价，多进程能真正并行用多核；
- 队列空时 worker 阻塞在 `BRPOP`（超时 2 秒），**不轮询、不烧 CPU、不占模型额度**；
- 排队时长与并发数是利特尔法则的关系：`所需并发 ≈ 提交速率 × 平均任务时长`。真正的天花板是 LLM 配额，
  不是 Redis —— 一条任务全程约 200~600 条 Redis 命令，60 并发也才 1000 ops/s 量级。

### 5. 心跳与租约（失联回收）

它解决的是"**这条任务当前还有没有人在跑**"—— 因为任务在某个进程的内存里跑，别的节点看不到它，
而 `status=running` 这行字符串自己不会变：进程被 `kill -9` 后没人改状态，任务就永远停在 `running`。

- 谁开始跑一条任务，就在 `agentflow:leases` 里占一行（member = `job_id`，score = 现在 + `AGENTFLOW_LEASE_SECONDS`）；
- 执行期间每 `AGENTFLOW_HEARTBEAT_SECONDS` 把这一行**往后推**（这就是心跳）。所以"过期"不是"任务跑了多久"，
  而是"**多久没听到执行者的消息**"—— 只要心跳在续，任务跑一小时也不会被回收；
- 心跳停了（进程崩溃 / 被 OOM / 断电 / 与 Redis 断连），租约到期，任何活着的 worker 的回收扫描
  （每 10 秒一轮）都会把它捞回来：**重排回队列**（消耗一次 `attempts`，原因写 `worker 失联（心跳超时 Ns）`），
  最坏 `租约 + 扫描间隔`（默认约 60~70 秒）自愈；
- **心跳必须显著小于租约**（默认 10s / 60s，容忍连续 6 次续期失败）：两个值相等时一次网络抖动就会误判，
  导致同一条任务两个进程同时执行 —— 双倍 token，且两个 writer 写同一个产物目录。经验公式 `租约 ≥ 4 × 心跳`；
- 同进程的 N 个槽共享一个 `worker_id`（`hostname-pid`），但租约按**任务**登记，所以槽位之间互不干扰；
- 两个前提：**不要把事件循环阻塞超过租约时长**（否则心跳续不上会被误判，worker 侧 Redis 调用已放 `to_thread`，
  执行体内部的进度写入仍是同步的微秒级调用）；**多机时钟要 NTP 对齐**（租约判定比的是各机本地时间戳，
  漂移远小于租约即可）。

> 换成 Redis Streams（`XREADGROUP` + `XAUTOCLAIM`）可以做同一件事（投递确认 + 崩溃认领，由 Redis 原生维护），
> 代价是可读性下降；当前 List + ZSet 的实现好处是完全可见、好排查。

### 6. 失败重试

| 失败类型 | 判定依据 | 是否重试 |
|---|---|---|
| 输入类错误（缺必填项、文件不存在等） | 错误 `code` 为 4xx | **不重试**，直接终态（重试结果必然一样，白烧一次模型调用） |
| 运行类错误（LLM 超时、依赖异常、未捕获异常） | 错误 `code` 为 5xx | `attempts < AGENTFLOW_JOB_MAX_ATTEMPTS` 时重排重试 |
| worker 失联（租约超时回收） | 回收器判定 | 同上（也算一次尝试） |

- `attempts` 在**认领时** +1，所以崩溃、被杀、租约回收都会计入，异常路径不会无限重跑；
  `GET /api/v1/tasks/{job_id}` 能直接看到它，`>1` 说明发生过重试；
- 重试是**全量重跑**（没有断点续跑），但**复用同一个 `request_id`**：产物目录 `data/{user_id}/output/{request_id}/`
  与会议记忆（meeting_id 由 request_id 派生）都是**覆盖**而非新增，这是重试安全的前提；
- 成本上界 = `AGENTFLOW_JOB_MAX_ATTEMPTS × 单次成本`（默认 2 次）；
- 反例警告：**不要用同一个 `request_id` 并发执行两次**（例如旧 worker 还活着就手工重投），
  两个进程会同时写同一个产物目录。

### 7. 优雅停机

worker 收到 `SIGTERM`/`SIGINT` 后：**停止取新任务 → 手上任务继续跑（心跳照常续租约）→ 跑完退出**。

- `--grace`（默认 300 秒）是"等你的上限"：超过就取消退出，被取消的任务保留 `running` + 租约，
  等租约过期由别的 worker 重排重跑 —— **任务不会丢，但会浪费一次模型调用**；
- 所以 `grace` 取"最长任务耗时的 1.5 倍"即可；K8s 部署时 `terminationGracePeriodSeconds` 必须大于它，
  否则 kubelet 先 SIGKILL，等于 grace 不生效；
- 空转时停机约 2 秒内完成（受 `BRPOP` 超时 2 秒限制）。

### 8. 可观测与排查

```bash
R="docker exec -it redis redis-cli -n 0"
$R llen  agentflow:queue                      # 积压任务数
$R zcard agentflow:leases                     # 当前在跑任务数（= 全局并发占用）
$R zrangebyscore agentflow:leases -inf +inf withscores   # 每条在跑任务的租约到期时间戳
$R lrange agentflow:job:<job_id>:events 0 -1 # 某条任务的完整事件流
$R ttl    agentflow:job:<job_id>              # 状态留存剩余时间
```

| 现象 | 原因 | 处理 |
|---|---|---|
| 任务一直 `queued` | worker 没起，或 `AGENTFLOW_RUN_MODE` 还是 `inline`（没入队） | 起 worker；确认 `.env` 为 `queue` |
| 提交返回 503 `Redis 不可用（<url>）：…` | Redis 挂了 / 地址不对 / 未装 redis 包 | 看括号里的地址，对照 `REDIS_URL`；`pip install -r requirements.txt` |
| 任务卡 `running` 不结束 | 执行它的 worker 还活着但任务很慢；或回收器还没到期 | 看 `heartbeat_at` 与 `zrangebyscore` 的到期时间；租约到期会自动重排 |
| 同一条任务跑了两遍 | 租约被误判（阻塞超过租约 / 时钟漂移大） | 加大租约或减小任务内的同步阻塞；检查 NTP；确认没有手工重投 |
| `attempts` 变 2 但仍失败 | 重试次数用尽 | 看 `error` 字段；输入类错误需修数据而不是重试 |

日志关键字（英文短句，与全仓日志口径一致）：`worker start id=… concurrency=… lease=…s heartbeat=…s max_attempts=…`（启动生效值）、
`reclaim job=…`（租约触发回收）、`draining: N running jobs, grace=…s`（grace 开始）、`grace timeout, slot cancelled …`（grace 到期）。
worker 启动时若 `run_mode != queue` 会打警告（任务不会进队列，worker 只会空转）。

### 9. 参数速查

| 参数 | 默认 | 建议/约束 | 生效进程 |
|---|---|---|---|
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | 换机/换库/加密码改这里；多机部署指向 Sentinel/VIP 而非写死 IP | 全部 |
| `AGENTFLOW_JOB_TTL_SECONDS` | 604800（7 天） | 状态与事件流的留存；重试窗口不要超过它 | API + worker |
| `AGENTFLOW_RUN_MODE` | `inline` | 生产用 `queue`；切换前先排空队列 | API |
| `AGENTFLOW_WORKER_CONCURRENCY` | 1 | 4~8（等模型为主）；命令行 `--concurrency` 优先 | worker |
| `AGENTFLOW_WORKER_GRACE` | 300 | > 最长任务耗时；K8s grace period 要更大 | worker |
| `AGENTFLOW_LEASE_SECONDS` | 60 | ≥ 4 × 心跳；跨机房可放宽到 120~180 | worker |
| `AGENTFLOW_HEARTBEAT_SECONDS` | 10 | 一般不用改 | worker |

优先级：**shell 环境变量 > `.env`**（加载用 `setdefault`），所以可以只给某台机器临时覆盖。
`.env` 每个进程只加载一次，**改完必须重启对应进程**；非法值一律回落默认（不会启动失败）。
启动日志与这行命令都能核对生效值：

```bash
python -c "from app.config import run_mode,job_ttl_seconds,job_max_attempts,lease_seconds,heartbeat_seconds; \
print(run_mode(), job_ttl_seconds(), job_max_attempts(), lease_seconds(), heartbeat_seconds())"
```

### 10. 运维注意

**目录骨架来自原文**：catalog 的**结构与顺序不再由模型发明**——程序先把 OCR 合并稿解析成
"有序骨架"（`domain/notes/tasks/catalog/skeleton.py`：页块内最浅标题 = 主题、更深 = 知识点，
细碎标题如例题/易错/小结**不建节点**而把正文并入父节点，`X（续）` 并入同名主题），把它作为
**权威输入**写进 briefing；旧候选池（入库时的分数/类型/标签）降级为**增强证据**，只用于判
importance、写 knowledge_items、补前置依赖。模型输出后按骨架核对：漏掉的 T/P 自动补回并标
`node_status=program_restore`；顺序按骨架 order 还原（章按其下最早节点）。两条硬指标都能用脚本验收：

- **覆盖 100%**：骨架里每个主题/知识点都在目录里（出现在节点名或某个 KP 的 `knowledge_items` 里都算）；
- **同级顺序单调**：章按其下最早节点的位置、章内主题按 order、主题内 KP 按 order 都非递减。

骨架有两条来源，统一走 `build_source_skeleton()`：**真 Md 优先**（`【原文骨架（权威）】`，
按标题层级逐节解析）；没有 OCR Md 时回退**知识库 metadata 还原的虚拟骨架**
（`【来源结构骨架】`，只把 high/medium 信号升成主题/KP，低分标题留作正文 evidence）。

**P7：checklist 的调用结构（切批并行 + 动态预算，覆盖不动）**

checklist 慢的根因不是"卡多"，而是**调用结构**：契约要求每张 S/A 卡写 explain 200-260 字 +
4-6 条 facts + 4-6 步 + 2-4 条 pitfalls ≈ 450-850 tokens，43 张 ≈ **20k-36k tokens 输出**，
而单轮上限 10000 → 必然截断 → 减半重试 → 串行两轮，端到端 3 分 14 秒。修法**不能**是少写卡
（卡片集合 = 激活集合，是产品承诺），而是：

| 措施 | 做法 | 效果 |
|---|---|---|
| **D1 切批 + 并行** | 待写卡（S/A + 老师点名）按 `CHECKLIST_LLM_BATCH_SIZE`（默认 9）切批，`CHECKLIST_LLM_PARALLEL`（默认 4）并发发起；单批失败**只降级该批**（程序合成），不追加轮次 | 墙钟 ≈ 单批（40-70s）而不是 批数 × 单批；26 张 → 3 批并行 |
| **D2 动态 max_tokens** | 批内按档位累加输出预算（S ~900 / A ~700 tokens/卡）+ 余量，clamp 1.2k-16k | 不再截断 → 不再有"截断→减半→重试"连锁 |
| **D3 字段预算按档位** | S：explain 200-260 字 / facts 4-6 / steps 4-6 / pitfalls 2-4；A：120-180 字 / 3-5 / 3-4 / 2-3；B/C 不进 LLM（程序按目录条目合成） | 每卡 tokens 再降约 30%，批更少；S/A 仍是精写（定义+边界+老师变形+缺项） |

**覆盖承诺（与 LLM 无关）**：`assemble_checklist` 对**每个激活 KP** 逐行出卡，模型没写就用
`_fallback_*` 按目录 `knowledge_items` 合成（实测：模型一张不写时 40 激活 → 40 张卡，
空壳 0 张，explain 中位 158 字）。所以"精写范围"只影响文字厚度，不影响知识点覆盖。

**关系与差异度由程序保底（零 LLM）**

三个下游症状是同一条因果链：**关系全空 → importance 结构分恒定 → 单值占比 96% → checklist
`_quantile_assign` 同分并档吞档 → 43/43 全挤进 S 档（"全是核心"）→ 模型要写 43 张卡 →
10k 输出上限截断 → 分批重试，端到端 3 分 14 秒**；知识图谱孤岛也是同一个上游（关系为 0）。
所以三件事一起收口：

| 步 | 内容 | 效果 |
|---|---|---|
| **A 关系程序保底** | `backfill_catalog_relations`：同主题 KP 两两 `used_with`、章内相邻主题 `prerequisites`、术语共现（复用入库的 `term_cooccurrence`）同章连边；条目带 `origin=program`、有上限、不产自指 | 关系非空 **0/48 → 38/48**（136 条边：同主题 68 / 主题链 22 / 共现 46） |
| **B importance 多信号 + 分布护栏** | 结构分改为"关系密度 + 是否在学习路径上 + 同节并列量 + 公式/定理形态"；单值占比 > 60% 时按结构分上下三等分微调 ±1（不越"items≥3 不得低于 3、空占位不得高于 2"的边界） | 单值占比 **96% → 67%**，取值 3/4/5 |
| **C 分档防退化 + 档位指标** | `_quantile_assign` 的同分并档**幅度受限**（最多越过分位点 5%），同分内用 `_tie_break`（难度→items→层级→原文序）定序；`result.md` 与日志输出**档位分布** | 档位 **43 全 S → S11 / A15 / B14（+DROP 3）**；模型撰写卡量 **43 → 26** |

对账口径：`monitor.catalog` 新增 `relations_ratio`（有关系 KP 占比）与
`importance_single_ratio`（importance 单值占比）；checklist 的 `result.md` 顶部与
服务端日志新增 `checklist grades: 核心 11 · 重点 15 · 简要 14（40 张）`。

**内容词表与形态规则：单一来源 + 可配置（`catalog/taxonomy.py`）**

catalog 的判定分三层，越往上越通用；**任何"具体见过的名字"都不写进逻辑**：

| 层 | 判据 | 例子 | 位置 |
|---|---|---|---|
| 形态规则 | 与学科/语言无关的字面形态 | 序号前缀、圈号、`（续）`、编号标题、页框/联系方式、句末标点 | `source_role` / `skeleton` 前缀正则 |
| 结构判定 | **形状**，不依赖任何词表 | 父子同名、唯一子节点同名、同名同级重复、空壳、顺序单调、覆盖完整 | `skeleton` / `merge` 的形状判定 |
| 内容词表 | 跨学科的学习材料**类别**（半通用） | 辅助性内容（例题/易错/小结…）、知识标题（定义/定理…）、细粒度点（适用条件/常见变形…）、占位名形态 | `taxonomy.py`（唯一来源，`prompt` 的类别说明也由它生成） |

词表只用于**降级与计数**（把辅助内容收进 items、统计占位名），**绝不决定结构或顺序**——结构与顺序永远来自原文骨架。
占位名（`核心知识点` 这类）改为**形态判定**（正则覆盖同类，而不是列举见过的名字），并可用环境变量覆盖：

```bash
CATALOG_ITEM_MARKS=例题,易错,小结       # 追加/覆盖"辅助性内容"词表；给空值 = 关闭该类判定
CATALOG_TITLE_MARKS=定义,定理           # "知识标题形态"词表
CATALOG_PLACEHOLDER_RE=^(核心|其他)$     # 占位名形态正则（整体替换）
CATALOG_FINE_GRAIN_MARKS=适用条件,常见变形  # "细粒度点"词表（降级进父 KP 的 items）
```

**直接使用 Markdown 标题树**

原文的 Markdown 层级本身就是结构——实测这份合并稿的层级分布（`#`×8 / `##`×26 / `###`×28）
相当规整，真正需要修补的只有零头。于是：

- **栈式建树**：按 `#` 数量建父子；跳级（`#` 后直接 `###`）自动挂到最近的更浅祖先；
- **层级映射按文件层级数归一**（用**树深度**而不是标题级别判定，跳级处不会出现"有 KP 无主题"）：

  | 文件层级数 | 章 | 主题 | 知识点 |
  |---|---|---|---|
  | 三级（span ≥ 3） | 原文一级标题 | 二级标题 | 三级及更深（更深层折进 KP 正文） |
  | 两级 | 由模型按语义分组 | 一级标题 | 二级标题 |
  | 一级 | 由模型分组 | 一级标题 | 由模型从正文提炼 |
- **四条确定性修补**：`X（续）` 并入同名节点、同名同级合并（两处「最概然分布求算」）、
  跳级归位、名字去序号（`① 角向方程的求解`→`角向方程的求解`、`3 散度定理`→`散度定理`、`证明：`→`证明`）；
- **LLM 职责不变**（命名规范化 / 合并 / 降级 / 字段填充），不新增固定轮次；
  `monitor.catalog.max_kp_per_topic` 用来盯"一个主题塞太多 KP"的回归。

**目录体检进入响应 monitor**：catalog 跑完时程序读**刚存下的**目录 + 原文骨架算指标（零 LLM），
写进响应体的 `monitor.catalog`，你一眼验收而不用读整棵树：

```jsonc
"monitor": {
  "token_usage": 18234, "cache_hit": 5120, "cost_time": 47.3,
  "catalog": {
    "coverage": "65/65",        // 骨架 T+P 全覆盖
    "order_violations": 0,      // 同级顺序乱序处数（章按最早位置、章内主题、主题内 KP）
    "restored": 0,              // 模型漏掉、由程序按骨架补回的节点数
    "complemented": 0,          // 输出侧补缺补出的节点数
    "demoted": 0, "merged": 0,  // 模型降级为 items / 主题被合并且内容都在（合法操作）
    "llm_added": 1,             // 模型新增的骨架外节点（合同禁止，保留但记账）
    "verified_items": "39/150", // items 能在原文里找到依据的条数
    "label_items": 69,          // 短标签（模型的命名），文本上无法逐字核对，不判对错
    "misplaced_nodes": 0,       // 整节串门：某 KP 多数条目的最佳匹配落在别节
    "unverified_items": 0       // 长条目像引用却全篇找不到依据（疑似编造）
    "generic_nodes": 0,         // 占位名节点数（核心知识点/核心概念/… 应为 0）
    "skeleton_kind": "md",      // 骨架来源：md（原文）或 metadata（知识库还原）
    "fake_heading_chunks": 0,   // 可疑标题块数（长或含标点）：入库标题识别的回归哨兵
    "max_kp_per_topic": 7       // 单主题 KP 数上限（>5 说明层级被压平，需检查骨架映射）
    "relations_ratio": "38/48", // 有关系（前置/相关）的 KP 占比：图谱有边、结构分有区分度的前提
    "importance_single_ratio": 0.67 // importance 单值占比（>0.6 说明结构信号塌陷，分档会退化）
  }
}
```

> `fake_heading_chunks` 是哨兵而非硬指标：md 里**真实的长标题**也会计入（例如
> `宏观分布与宏观态(与 $\mu$ 空间的分布…对应)`）；它要抓的是"正文被误判成标题"
> （例如 `③ …` 经 NFKC 变 `3 …` 那类），正常情况下这类块应为 0。

第三道校验（内容可核）的**精度边界**要如实理解：模型写的是**概述型标签**（`守恒量定义`），
不是原文引用，逐字比对必然误报。所以条目级只判"有没有依据"（逐字命中 / 片段重合 / 短标签不判），
**只有节点级**才判"整节串门"（某 KP 多数条目更像另一节），"疑似编造"只收长条目——
这两类才是高精度、可执行的信号。

**目录顺序与覆盖的位置轴**（入库侧 `tools/knowledge/document_processor.py`）：OCR 合并稿每块前带
`<!-- ocr-pages: lo-hi -->` 页块标记，入库解析成块元数据 `page`/`page_span`，并给每个块补一个
**文件内递增** `chunk_index`——原文位置从此可还原。此前 md 既不写 `page`（只有 PDF 分支写）也不写
`chunk_index`（只有超长块被切分时才写），catalog 于是只能"按标题字符串排序"，目录顺序乱、保序表也
拿不到位置（形同虚设）。同一次修正里，标题层级按**文件内最浅标题**归一为 1 级：OCR 合并稿由逐页
LLM 生成、层级跨页不可比，不归一时"整篇 ###"的文件会整页被折算成低分证据（`_heading_score` 里
3 级只给 2 分）。另外【低可信标题】不再只报数量——列出名字并说明"正经小节名照常建主题/KP"；
输出侧补缺（`complement_catalog_coverage`）也不再要求分数 ≥5，缺的整节会**按候选自己的章名新建**，
并在补缺后重新保序一次。

**目录节点清理规则**

1. **入库不再认错标题**（治本）：数字编号形态必须带标点（`1.` / `1、` / `1)` / `1.2` / `（1）`）
   才算标题。此前 OCR 清洗的 NFKC 会把 `③ 分子在两次碰撞间…` 变成 `3 分子…`，被"数字 + 空格"
   规则当成**章级标题**，顺着候选池长成目录里的空壳假章节。纯文本笔记若确实用"数字 + 空格"写标题，
   可设 `HEADING_NUM_LOOSE=1` 回退。
2. **有骨架时输出侧补缺让位**：`complement_catalog_coverage` 一旦发现骨架就直接返回——
   覆盖由骨架侧的 `restore_from_skeleton` 负责，杜绝"补出骨架外的节点"。
3. **不再生产占位名**：`核心知识点 / 核心概念 / 知识概要 / 补充知识点 / 其他` 一律不再由程序写入
   （章级候选宁可跳过并计数，交给结构修复器用真名回退补点）。`monitor.catalog.generic_nodes`
   统计最终目录里的占位名节点，非 0 时应检查目录合并与重命名路径。

知识库维护工具 `tools/devtools/purge_kb_source.py` 可按来源列出或清除旧知识块。
不传 `--source` 时只展示；删除前应先用 `--list` 核对用户、学科和来源文件。

生产运维注意：

- **Redis 是全局单点**：发号器 + 状态 + 事件流 +（queue 模式）队列与租约都在它身上，它挂了所有节点的
  异步接口一起 503（同步接口不受影响）。规模上来必须配 Sentinel 主从，应用用 Sentinel 地址；
- 连接已改为**进程内单例 + 连接池**（不再每请求新建 + `PING`）；`/api/v1/health` **不检查 Redis**，
  若拿它做 LB 健康检查，建议自行加 Redis 探测，否则 LB 会把异步请求继续分发给"异步全 503"的节点；
- 生产禁用 `KEYS`（用 `SCAN`，上面的排查命令用的是 `--scan` / `zrangebyscore` 这类安全命令）；
- `maxmemory` 建议配 `noeviction`：任务状态被静默淘汰比报错更糟（客户端会看到 job 凭空消失），
  配合 7 天 TTL 即可；
- 上 Redis Cluster 时**只有 db0 可用**，`REDIS_URL` 里的 `/0` 不能改；
- 已知待优化：事件流读取仍是 `LRANGE cursor -1` 全量拉（多客户端高频轮询时是 O(n)，可换 `XREAD` 或分页）、
  每个 `chunk` 会写一次进度 `HSET` + 追加一条事件（可降频合并）、HTTP 处理器里的 Redis 调用仍是同步客户端（可换 `redis.asyncio`）。

## 接口调用

接口分两族：**统一入口的同步 / 流式 / 产物端点**（两族共 10 条任务线，域与任务名由请求体给出），
以及一组**与任务线解耦的异步任务接口**（生产主路径，见上文 Redis 章节，接口契约见 [API.md](API.md)）。

> **接口契约以 [API.md](API.md) 为准**：URL 一览与逐字段说明见其 §0.1 / §2 / §3
> （本节的表只作概览，两处内容若不一致以 API.md 为权威，并请顺手修这里）。

10 条任务线**都走同一个同步 POST 与流式 POST**（`POST /api/agent/v1`、`POST /api/agent/v1/stream`，
请求体带 `domain` + `task`）；产物端点按是否有落盘产物注册，预览仍按域/任务名分路径：

| 域 | task | 用途 | 产物端点 | 产物 |
|---|---|---|---|---|
| meeting | `minutes` | 会议纪要提取 | ✅ | `minutes.html` + `result.md` |
| meeting | `actions` | 待办提取 | ✅ | `actions.html` + `actions.md` |
| meeting | `risks` | 风险识别 | ✅ | `risks.html` + `risks.md` |
| meeting | `minutes_styles` | 多样式纪要 | ✅ | `minutes_styles.html` + `.md` |
| meeting | `minutes_trace` | 溯源纪要 | ✅ | `minutes_trace.html` + `.md` |
| meeting | `consensus_decision` | 共识决策 | ✅ | `consensus_decision.html` + `.md` |
| notes | `graph` | 知识图谱（交互 HTML） | ✅ | `graph.html`（无 md 落盘） |
| notes | `library` | 资料入库 | ❌ 无落盘产物 | 仅响应 `data.text` |
| notes | `catalog` | 知识目录（**章/主题/知识点顺序跟随资料原文**） | ❌ 产物不在 output 目录 | `knowledge/catalogs/{学科拼音}/*.json` |
| notes | `checklist` | 复习清单 | ✅ | `checklist.html` + `result.md` |

> **路由的唯一声明处是 [app/tasklines.py](app/tasklines.py)**（域 → 任务线 → 是否注册产物端点）：
> 统一入口的 `domain`/`task` 校验（[app/routes/agent.py](app/routes/agent.py) 与
> [app/routes/tasks.py](app/routes/tasks.py) 共用一份）、预览路由注册
> （[app/routes/_registry.py](app/routes/_registry.py)）都从它派生，加一条任务线只需在这里加一行。
> 哪些线有产物端点、各自必填什么，见 [API.md](API.md) 第 0.2 节与第 2.2 节；
> notes 域当前对外任务线为 graph / library / catalog / checklist。

```bash
curl -X POST http://127.0.0.1:8000/api/agent/v1 \
  -H "Content-Type: application/json" \
  -H "X-User-Id: u1" \
  -d '{"domain": "meeting", "task": "minutes", "texts": {"transcript": "会议记录全文……"}}'
```

产物落盘规则（均在 `data/{user_id}/output/{request_id}/` 下）：

| 文件 | 内容 | 说明 |
|---|---|---|
| `result.md` | 最终文本 / 大纲 | 不按线命名的任务线用这个文件名 |
| `{task}.md` | 最终文本 | 按线命名的任务线：`actions` / `risks` / `minutes_styles` / `minutes_trace` / `consensus_decision` |
| `{task}.html` | 页面版 | 只有生成线有（`minutes` / `actions` / `risks` / `minutes_styles` / `minutes_trace` / `consensus_decision` / `graph` / `checklist`）；`library` / `catalog` 不生成 |
| `result_rejected.md` | 门禁失败时的备查副本 | 内容与 `result.md` 相同，用于复盘"门禁看到了什么" |
| `result.review.json` | 审核载荷（该线有审核产物时） | 回看审核结论用 |

> 任务线清单与产物端点以 [app/tasklines.py](app/tasklines.py) 为唯一声明处（见本节开头那张表）。
> `mindmap` 不在对外任务线清单里（`app/tasklines.py` 没有它）：它是 meeting 域的线，
> 产物由 `tools/core/runner.py` 走 `tools/exports/html/mindmap.py` 导出 HTML/PNG（见「架构要点」）；
> `notes` 域对外的任务线是 `graph` / `library` / `catalog` / `checklist`。

产物文件可通过配套下载端点获取（`GET /api/agent/v1/file/{request_id}/{file_name}`，强制下载，无需域与任务名），也可直接访问静态路径 `/data/{user_id}/output/{request_id}/{file_name}`（浏览器直接打开，无鉴权）。

## 自定义输出模板

接口 `extra.template` 支持模板注册表里的全部预设模板（生效目录见上「项目结构」，`template_v3` 当前 30 个），也可通过 `TEMPLATE_ROUTER` 机制处理自定义模板。模板支持三种形式，系统**自动判型**处理：

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
② python tools/codegen/register_task.py --domain meeting --task xxx --name "中文名"
   # 自动：注册中文名 + steps/ 三件套 + 工厂 import + 占位校验类
③ 手写 domain/meeting/tasks/xxx/prompts.py         # 4 个 prompt 常量
④ reports.py 末尾追加 XxxReport 类（继承 ModelMixin, XxxReportValidation）
⑤ python tools/codegen/sync_domain.py --domain meeting   # 全量生成 → SUCCESS!
⑥ python tools/codegen/sync_domain.py --domain meeting --check   # 校验 → SUCCESS!
⑦ 在 app/tasklines.py 的 DOMAINS 里加一行声明（域、线名、是否有产物端点）
   # 统一入口 /api/agent/v1 直接可用（domain/task 走请求体，校验从这份声明派生）；
   # files=True 时自动注册产物预览路由；下载端点与域/线名无关，无需逐线注册
⑧ 在 app/requirements.py 的 REQUIRED_FIELDS 里声明必填项（缺必填秒回 400，不触发模型）
```

> 路由声明是**唯一来源**：`app/tasklines.py` 之外不要再写任务线清单（`app/tasks.py` 的 `LINE_NAMES`、
> `app/routes/agent.py` 与 `app/routes/tasks.py` 共用的 `resolve_line` 域校验都从它派生）。

## 变更记录 · 纪要形态（2026-09-22）

一轮**有行为改动**的质量修复，治"末尾三组把十几条压成一两条"（实测同输入两次运行：一次分条正常，
另一次 12 条待确认 + 20 条风险各被「；」压成一条 bullet，233 字 / 519 字，原样落盘）。

- **模板（a）**：`template_v3/general_minutes.md` 的 [要点梳理] 说明补上「末尾三组一律 `- ` 一条一行、
  一条一个事项；**禁止把多条用「；」压成一条**；单条超过两百字就拆成多条或用缩进子条」——
  原先只有第一大栏写了"一条一行"，末尾三组只写了内容范围，给了模型合并的口子。
- **判据与重写（b）**：「单条超长（`- ` 条目 >200 汉字）」判据抽成单点函数
  `tools/execution/hard_execution.py::overlong_items()`（`advisory_issues()` 改调它，报错文本逐字不变）；
  **逐栏填充**把它当硬问题——命中即只重写中招那一栏（一次单栏调用、最多两栏），并下发具体修法
  （`_OVERLONG_ITEM_REVISION`）。**渲染层门禁行为不变**，仍只当 advisory 记账：软问题进 `issues`
  会让几乎每行都触发整篇返工，代价与内容风险都不小（见 `advisory_issues` docstring）。
- **自测**：+7 项（判据单点、只重写那一栏、重写下发修法、重写后无超长条），6 套件 1018 项断言全过；
  真链路复跑 0 超长条、末尾三组逐条分列。
- **`# 栏名` 粘连在上一栏末尾（同轮修掉）**：根因是 `split_overlong_paragraphs_except_first`
  按 `# 栏名` 切段后逐段调 `split_overlong_paragraphs`，后者返回 `"\n".join(行)` —— **段尾换行被丢掉**，
  再用 `"".join(各段)` 拼回，下一段的一级标题就粘到上一段末尾。渲染层对同一份文本跑**两次** enforce
  （逐栏填充内部一次、render 层一次）：第一遍把段间空行削成单换行、第二遍直接粘连，所以每篇必现。
  修法：段边界**按原样补回段尾换行**（保真且幂等）；另加确定性兜底 `hard_execution.fix_glued_column_titles()`
  —— 把粘在正文里的 `# 栏名` 提回独立行（只动模板声明的一级栏名，零 LLM 调用），已粘连的历史文本也能修回。
- **未做（沿用现状）**：审核仍在渲染之前 ⇒ 形态问题审核不到；`render_advisory_issues` 仍只进日志
  （未接响应 `monitor`）；段落级超长仍只记账。

## 变更记录 · 末尾三栏按「人」分块（2026-09-22）

真人（`profile=user`）的**末尾三栏**（结论与决定 / 行动项与分工 / 待确认与风险）都长成"组名行 + 其下条目"：
本人一段 `**与我相关**：`（条目内不写自己姓名）、他人每位一段 `**姓名**：`。**不做后处理**，
靠"可照抄的骨架 + 与骨架一致的口径"一起改：

- **组名统一叫「与我相关」**（`perspective/preferences.py::SELF_GROUP_ROW`，单点定义）：旧名带"事项"，
  只能套在行动项那一类上，落到结论/风险栏就说不通（结论不是"事项"）。三栏共用一份骨架，
  骨架里点明"这三栏都按它分块"。
- **① 程序给骨架**：`perspective/hits.py::render_action_groups_block()` 算出要出现的组名行清单
  （本人那行固定，他人取**待办 owner ∪ 与会发言人**——结论/风险可能挂在任何一位发言人名下，
  不只待办的 owner），与命中块同一机制注入**草稿 / 审核 / 渲染**三处；客观视角返回空串 ⇒ 零外溢。
- **② 纪律给样例**：`PERSONAL_VIEW_DIRECTIVE` 带 4 行形状样例（组名行独占一行、块内 `- ` 一条一行、
  没有内容的块不出现），仍只进 `minutes` / `minutes_styles`。
- **结论与决定也分组**：`key_decisions` 契约/提示词补上同一口径；`_attribute_person_items()` 从只补
  risks / open_questions 扩到**也补 decisions**（上游 decisions 是纯文本、没有归属，按原文发言结构
  补出"谁提出/谁拍板"，看不出归属的平铺在最前、不加姓名）。
- **prompt 去矛盾**（真正的开关）：`tasks/minutes/prompts.py` 残留的旧口径「他人条目**每条以「姓名：」开头**」
  与契约（`contracts.py` 要求"组名元素"）冲突——实测契约口径在 10:45 出过一次组名行，之后连续三次都出不来，
  模型一律照旧口径写成逐条前缀。两处已改成与契约一致的组名行写法；审核侧两种形态仍都接受，不误拦。
- **状态通道（真链路事故）**：`user_action_groups_block` 起初没写进 `domain/meeting/models.py::MeetingState`，
  而 LangGraph **只传该 TypedDict 里声明过的 key** ⇒ 骨架写了、草稿/审核/渲染全程收不到
  （单元测试手工注入 dict，恰好掩盖了这一点）。已补声明，并加守护断言（key 在 `MeetingState` 里、
  视角节点确实写入、旧组名不在任何 prompt 源文件残留）。**新增 state key 必须同时改 `MeetingState`**，
  否则静默失效。
- **自测与实测**：6 套件 **1061 项断言**全过 + `sync_domain --check` + `compileall` 全绿；
  真链路复跑（决策/行动/风险三栏都有料的会话）：真人三栏各出 `**与我相关**：` + `**徐玥**：` / `**武思华**：`
  分块、条目内 0 条重复姓名；客观 0 条组名行（照旧平铺，条目按上游原文）。

## 变更记录 · 结构整理（2026-09-21 / 22）

一轮"零行为改动"的整理：功能与对外契约不变，改的是**代码组织、死代码与文档**。全部改动都过了
`python -m tests`（6 套件 1011 项断言）+ 两域 `sync_domain --check` + 全仓 `py_compile` + 真实链路
冒烟（meeting 与 notes 两条域）。

**目录与层次**
- 自测套件收拢到顶层 `tests/`（`python -m tests` 一键跑；不叫 `test`，避免遮蔽标准库同名包）
- 三包归位：`supervisor/` → `domain/_shared/`；`client/` → `tools/llm/`；
  `perspective/` 回顶层，画像数据独立成 `assets/profiles/`（附 `assets/README.md`）
- 领域支撑下沉：`meeting_memory/` → `domain/meeting/memory/`；`memory/`、`knowledge/`、
  `exercise_search/` → `domain/notes/…`；共享底座（落盘布局 / 向量库 / 文件→文本 / `safe_id`）留在 `tools/`
- `tools/` 内部：模板路由并入 `tools/templates/router/`；四个 HTML 生成器进 `tools/exports/html/`；
  代码生成器 → `tools/codegen/`，手工运维脚本 → `tools/devtools/`
- 仓库卫生：`.gitignore` 忽略 `logs/`、`data/*/{output,memory,knowledge}/`（60 个运行时文件移出版本库）

**引擎层零域导入（域钩子注册表）**
- 引擎（`tools/core/runner`、`tools/runtime/render`、`tools/exports/outputs`）不再 `import domain.*`：
  记忆准备/注入/回写、各线产物 HTML、无模板正文压缩统一由 `domain/<name>/hooks.py` 声明、
  域包 `__init__` 自注册，引擎只问 `hooks_for(ctx.name)`（未注册域 ⇒ 空钩子）。协议见
  `tools/core/domain_hooks.py`；加新域不必改 `tools/`

**去重与死代码**
- 删：`_preview` 的"可读化/编辑模型"死簇、`build_graph_embed`、`list_profile_entries`、
  `format_cite_line`、恒真 `should_write_result_md`、15 处历史别名、`cli_template` 死字段、
  不可达的 `LibraryRender.extract_structure` / 旧版理解节点 / 两个空渲染提示词、`minutes_render` 的
  无模板压缩分支（编排路径不可达）
- 收拢：10 份 `draft_from_context` → `domain_engine_text.scrape_draft`；8 份 `_clean` →
  `tools/core/text.py`（域侧经 `domain/_shared/text.py` 转导出）；`_han_count` → `length_budget.han_count`
- 三份 `_make_agent_node` → 引擎一份（域只覆写 `_line_shared_context`）；三处审核表头 →
  `DomainNodes._revision_instruction`；`_GRADE` 词表两处 → `select.GRADE_LABELS` 一处
- 去 no-op：`run_ocr_subprocess(timeout)`、`exercise_search` 的 grade/edition 空转链、
  `_choice_or_default(path)`（含生成器同步重生）；重复小常量 `IMAGE_EXTS` / `PROJECT_ROOT` / `_ndjson`
- app 层：两处 19 参调用块 → `_runner_args(p)`；`TaskLine.cn`（只写不读）删除；
  `lines_for` / `all_lines` 的"恒等映射 dict" → 线名集合
- 生成器：空结构常量改为"任务线契约 ∪ 域内真有引用"才生成（消掉与人手写的 `_EMPTY_*` 重复的死常量）

- 收尾自检补删（2026-09-22）：上一轮删掉 `_preview` 里"预览↔可读文本↔编辑模型"四函数后，
  `tools/templates/router/_base.py` 中只服务它们的 5 个符号成了孤儿（`_BANNER_RE` / `_SLOT_LINE_RE` /
  `_OLD_FILL_RE` / `_is_slot_body` / `_split_by_heading`；其中 `_is_slot_body` 只调那两个 `_*_RE`，
  属传递性死代码）；另删 `_placeholder.py` 从未被读取的 `_COLUMN_CONCURRENCY`、2 处孤儿
  `import json` 与 1 处未用导入；补 `perspective.__all__` 漏掉的 `PERSONAL_VIEW_DIRECTIVE` /
  `VIEW_DIRECTIVE_TITLE`

**文档**
- `README` 与 `api.md` 去重：接口契约以 `api.md` 为权威，README 只留概览与指针；模板三种形式的
  说明只保留一处；命令示例与目录树全部对齐新路径
- 修正一批与代码不符的说明：`run_mode` 的读取位置、worker 日志关键字（改为实际英文短句）、
  模板目录与 `AGENTFLOW_TEMPLATE_DIR`、`profile` 选档表、`user.json` 写法（含偏好/性格白名单与上限）

**已知待办（未含在本轮）**
- **quiz 的 `structure` 不重抽**（review 分支在附件改写后会重抽一次，quiz 不会 ⇒ 响应里的
  `questions` 不带 `kb_*` 溯源，页面仍带）：**按当前需求，quiz 线暂不使用 ⇒ 不改**。将来要用
  quiz 前先决定：两条线都重抽（推荐）或都不重抽（届时也要去掉 review 那 3 行），别留中间态
- **同步接口的 `monitor.catalog` 恒空**：`_catalog_quality_monitor` 只在流式接口挂载（待定：同步也返回，
  或明确只在文档里标注"仅流式"）
- `use_cache` 若要可用，需先做 LLMClient 进程级复用并同步改 `_client_usage` 的 token 差值统计
- 模板注册表（`template_v2` / `template_v3`）按需保留在顶层：`api_test` 以 `template_v2` 作为
  仓库根标记，搬入 `tools/` 会打断它
- **逐栏填充目前不限并发**：原 `_COLUMN_CONCURRENCY = 3`（注释写「同时最多起几栏」）定义后从未被
  任何代码读取，2026-09-22 自检时按死代码删除 ⇒ 现状是 `asyncio.gather` 一次起满所有栏。若要真的
  限到 3 栏，属于**行为改动**，需接线（本地端点排队时才有必要）

## 架构要点

- **多线并行**：各任务线监督返工闭环（approve/revise≤1次/reject→降级），互不阻塞
- **契约驱动**：每条任务线的模型/校验/装配由 `contracts.py` 声明，`sync_domain.py` 生成
- **生成区**：`models.py` / `orchestrator.py` / `meeting_factory.py` 的生成区由脚本管理
  （`--write` 重写、`--check` 校验），手写区（contracts/prompts/reports 类）脚本不碰
- **全局标准注入**：`domain/_shared/` 的全局标准经 `GlobalSupervisor.build_prompt` 注入各线 supervisor
- **域钩子（2026-09-22 反转）**：引擎层（`tools/`）**不 import 任何域**——记忆准备/注入/回写、
  各线产物 HTML、无模板正文收尾压缩，由 `domain/<name>/hooks.py` 声明、域包 `__init__` 自注册，
  引擎只问 `hooks_for(ctx.name)`（未注册域拿到空钩子，不抛）。加新域不必改 `tools/`；
  协议见 `tools/core/domain_hooks.py`
- **占位校验**：register 阶段预生成 `XxxReportValidation: pass`，写 Report 类无 NameError，
  sync_domain 全量后按字段生成真实校验
- **模板路由**：`tools/templates/router/` 包自动判型三类模板并分派最优处理，
  任何失败回退旧路径；渲染输出附带只读校验（残留占位符/JSON 合法性）
- **结构化输出加固**：`tools/llm/llmclient.py` 的 `structured()` 对截断输出做程序修复
  （括号栈补全保留有效数据），非截断校验错误最多一次针对性重试，不再依赖 repair 兜底
- **思维导图**：mindmap 线产出 Markdown 大纲，经 `tools/exports/html/mindmap.py` 固定导出
  交互式 HTML（markmap，离线单文件）和 PNG 图片（Playwright 截图）；
  npx/playwright 缺失时自动降级不影响主流程
- **知识图谱**：notes 域 graph 线提取概念节点与关系边（nodes/edges，
  均锚定原文 + evidence），经 `tools/exports/html/knowledge_graph.py` 导出 Cytoscape.js 交互式 HTML 和学习地图 Markdown（默认输出到 `data/{user_id}/output/{request_id}/`）；悬空边自动过滤、HTML 仍尽量生成；
  传 `extra.memory=true` + `X-User-Id` + `extra.subject` 时按学科跨会话增量（新增节点高亮，见 API.md 2.7.1）
- **输出稳定性**：各线 prompt 采用确定性规则（数量由内容决定、措辞锚定原文、
  顺序按原文出现、空字段 null/[]），同一输入重复运行保持内容与篇幅稳定
