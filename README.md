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
  routes/{meeting,notes}.py   # 10 个任务线的同步 / 流式 / 产物下载路由
  routes/tasks.py             # 异步任务接口：提交 / 状态 / 结果 / 事件流（Redis）
  executor.py                 # 异步任务执行体：inline 与 worker 两种模式共用
  worker.py                   # 独立 worker：队列消费 / 并发槽 / 心跳租约 / 超时回收 / 优雅停机
  job_store.py                # Redis 任务状态、事件流、载荷、队列与租约（TTL 默认 7 天）
  id_worker.py                # request_id / job_id 发号器（Redis 日序号，无 Redis 时进程内降级）
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
  schema/                     # 契约 DSL（contracts）/ fallback 规则 / 结构化输出校验
  core/                       # 共享编排内核：domain_engine（图节点 mixin）/ runner / io / runtime_context / profiles / prompt_utils
  execution/                  # 硬执行规则：上游对齐 / 表行截断 / 验收门禁
  runtime/                    # 渲染运行时：render / context / kinds / supervisor_slice
  templates/                  # 模板渲染 prompt（template_prompt）与约束评测（template_eval）
  template_router/            # 模板路由：判型 / 占位填充 / 门禁 / 可读化
  exports/                    # 产物落盘：outputs / knowledge_graph / mindmap
  memory/                     # 跨会话记忆：记录累积 / 语义检索 / 引用标注 / 图谱增量
  knowledge/                  # 知识库：PPT/PDF/docx/xlsx 入库 + 向量检索 + 出处（RAG）
  ocr/                        # OCR 引擎适配（serverocr / rapidocr / paddleocr）
  monitor/                    # 任务监控：token / 缓存命中 / 按层耗时
  exercise_search/            # 高中题库检索（notes.quiz 用）
  scripts/                    # 开发工具：sync_domain / register_task 代码生成器
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

Redis 不可用时异步接口返回 503（`{"detail": "Redis 不可用（<url>）：…"}`），同步接口不受影响。

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
| 产物 | API 产物写入 `data/{user_id}/output/{request_id}/`；CLI 兜底写入 `data/{user_id}/output/cli_*/`（无根目录归档层） |
| 知识图谱 | HTML 可交互演示 |
| 思维导图 | HTML 需 Node.js/npx；PNG 需 Playwright Chromium |

样例与数据目录：

| 目录 | 用途 |
|---|---|
| `data/{user_id}/docs/` | 接口 `docs[]` 的输入文件（图片/文档/笔记） |
| `samples/{domain}/file/` | 样例输入文本 `.txt` |
| `perspective/profiles/` | 跨域公共画像（客观 + 职业模板）`.json` |
| `samples/{domain}/{task}_template/` | 任务模板样例 `.md` |
| `data/{user_id}/output/{request_id}/` | API 每次调用产物（`result.md` / `{task}.html`） |
| `data/{user_id}/memory/` | 跨会话记忆（records + chromadb 索引） |
| `data/{user_id}/knowledge/` | 知识库向量 + 知识目录 JSON |
| `data/{user_id}/ocr/` | OCR 合并稿 |
| `data/monitor/` | 任务监控 JSON（CLI monitor 开启时） |

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
提交响应会回显 `run_mode` 便于确认；`.env` 非法取值一律回落 `inline`。

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

日志关键字：`worker 启动 id=… 并发=… 租约=…s 心跳=…s 最多尝试=… 次`（启动生效值）、
`回收失联任务`（租约触发）、`停止取新任务，等待…收尾（最多 Ns）`（grace 开始）、`收尾超时，取消该槽位`（grace 到期）。
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

### 10. 自测与运维注意

```bash
python worker_selftest.py     # 46 项：队列 / 租约 / 回收 / 重试 / 停机 / 执行体契约；不调模型
```

自测默认跑 **5 号库**并在结束时清空，**拒绝在 0 号库运行**（那里是真实任务数据）；
可用 `AGENTFLOW_SELFTEST_REDIS_URL` 覆盖。
端到端 HTTP 链路用 `minutes_async_submit.py → status → result → stream` 四个脚本验证。

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

全部 10 个任务线接口 + 健康检查，请求/响应结构统一；另有一组基于 Redis 的异步任务接口
（提交 / 状态 / 结果 / 事件流，生产主路径），详见 **[API.md](API.md)**：

| 域 | 接口 | 用途 |
|---|---|---|
| meeting | `POST /api/v1/meeting/minutes` | 会议纪要提取 |
| meeting | `POST /api/v1/meeting/actions` | 待办提取 |
| meeting | `POST /api/v1/meeting/risks` | 风险识别 |
| meeting | `POST /api/v1/meeting/minutes_styles` | 多样式纪要 |
| meeting | `POST /api/v1/meeting/minutes_trace` | 溯源纪要 |
| meeting | `POST /api/v1/meeting/consensus_decision` | 共识决策（另有 `/consensus`、`/decision` 同义 URL） |
| notes | `POST /api/v1/notes/graph` | 知识图谱（学习地图 + 交互 HTML） |
| notes | `POST /api/v1/notes/library` | 资料入库 |
| notes | `POST /api/v1/notes/catalog` | 知识目录 |
| notes | `POST /api/v1/notes/checklist` | 复习清单 |
| - | `GET /api/v1/health` | 健康检查 + 任务线清单 |
| - | `POST /api/v1/tasks` | 异步提交任务（返回 `job_id`，不限任务线） |
| - | `GET /api/v1/tasks/{job_id}` | 异步任务状态（阶段 / 耗时 / token） |
| - | `GET /api/v1/tasks/{job_id}/result` | 异步任务结果（未完成返回 409） |
| - | `GET /api/v1/tasks/{job_id}/stream` | 异步任务事件流（NDJSON，`?cursor=` 断线续读） |

> **下载端点**：`minutes` / `actions` / `risks` / `minutes_styles` / `minutes_trace` / `graph` / `checklist`
> 各有配套 `GET /api/v1/{domain}/{task}/file/{request_id}/{file_name}` 下载接口
> （`request_id` = POST 时的 `X-Request-Id`，`file_name` = 响应 `data.file_name`，产物以附件形式返回），
> 详见 API.md 6.11。`library`（无落盘）与 `catalog`（file_name 指向知识目录 JSON）不提供下载。

```bash
curl -X POST http://127.0.0.1:8000/api/v1/meeting/minutes \
  -H "Content-Type: application/json" \
  -H "X-User-Id: u1" \
  -d '{"texts": {"transcript": "会议记录全文……"}}'
```

任务线：

| 领域 | 任务线 | 输出内容 | 主要产物（`data/{user_id}/output/{request_id}/`） |
|---|---|---|---|
| `meeting` | `minutes` | 会议纪要 | `result.md` + `minutes.html` |
| `meeting` | `actions` | 待办事项 | `actions.md` + `actions.html` |
| `meeting` | `risks` | 风险分析 | `risks.md` + `risks.html` |
| `meeting` | `minutes_styles` | 多样式纪要 | `result.md` |
| `meeting` | `minutes_trace` | 溯源纪要 | `minutes_trace.md` |
| `meeting` | `mindmap` | 思维导图 | CLI：`data/{user_id}/output/cli_*/mindmap/`（`mindmap_*.png` / `.html`） |
| `notes` | `graph` | 知识图谱 | `graph.html`（无 md） |
| `notes` | `review` | 笔记审查 | `result.md` + `review.html` |
| `notes` | `quiz` | 自测题（推理题 + 高中题库真题） | `result.md` + `quiz.html` |
| `notes` | `library` | 资料入库 | 仅接口返回文本，不落盘文件 |
| `notes` | `catalog` | 知识目录 | `result.md` + 目录 JSON（`data/{user_id}/knowledge/catalogs/{学科}/`） |
| `notes` | `checklist` | 复习清单 | `result.md` + `checklist.html` |

产物落盘规则（均在 `data/` 下，不再有根目录 `output/` 归档层）：

| 目录 | 内容 | 说明 |
|---|---|---|
| `data/{user_id}/output/{request_id}/result.md` | 最终文本 / 大纲 | `minutes` / `catalog` / `checklist` 等使用；`actions` / `risks` / `minutes_styles` / `minutes_trace` 按任务线命名为 `{task}.md`；模板门禁失败时改写为 `result_rejected.md` |
| `data/{user_id}/output/{request_id}/{task}.html` | 页面版 | 生成线：`minutes` / `actions` / `risks` / `minutes_styles` / `minutes_trace` / `review` / `quiz` / `checklist` / `graph`；`library` / `catalog` 不生成页面版 |
| `data/{user_id}/output/cli_*/mindmap/mindmap_*.html` | 思维导图 HTML | CLI 运行兜底目录；`mindmap` 只保留 HTML/PNG |
| `data/{user_id}/output/cli_*/mindmap/mindmap_*.png` | 思维导图 PNG | Playwright 不可用时跳过 |
| `data/{user_id}/output/{request_id}/graph.html` | 知识图谱交互 HTML | Cytoscape.js 交互演示版 |

产物文件可通过配套下载端点获取（`GET /api/v1/{domain}/{task}/file/{request_id}/{file_name}`，强制下载），也可直接访问静态路径 `/data/{user_id}/output/{request_id}/{file_name}`（浏览器直接打开，无鉴权）。

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
- **思维导图**：mindmap 线产出 Markdown 大纲，经 `tools/exports/mindmap.py` 固定导出
  交互式 HTML（markmap，离线单文件）和 PNG 图片（Playwright 截图）；
  npx/playwright 缺失时自动降级不影响主流程
- **知识图谱**：notes 域 graph 线提取概念节点与关系边（nodes/edges，
  均锚定原文 + evidence），经 `tools/exports/knowledge_graph.py` 导出 Cytoscape.js 交互式 HTML 和学习地图 Markdown（默认输出到 `data/{user_id}/output/{request_id}/`）；悬空边自动过滤、HTML 仍尽量生成；
  传 `extra.memory=true` + `X-User-Id` + `extra.subject` 时按学科跨会话增量（新增节点高亮，见 API.md 6.6）
- **输出稳定性**：各线 prompt 采用确定性规则（数量由内容决定、措辞锚定原文、
  顺序按原文出现、空字段 null/[]），同一输入重复运行保持内容与篇幅稳定
