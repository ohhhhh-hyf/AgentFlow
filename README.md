# AgentFlow · 生产就绪的多 Agent 协同编排引擎与后端服务

AgentFlow 是一套专为复杂垂直领域（智能会议分析、知识工程、学习辅助、结构化研报等）打造的**高可靠、低耦合、多任务线并行协同的多 Agent 编排框架与后端交付系统**。

系统采用严格的 **Clean Architecture（整洁架构）** 与 **DDD（领域驱动设计）** 规范，将全局源码与静态资产精炼收敛为 **7 大核心顶层目录**。通过强类型数据流、无依赖的领域事件协议、严密的多租户物理隔离与确定性防幻觉执行门禁，保障系统在企业级生产环境中的确定性与高扩展性。

---

## 目录索引
1. [系统总体架构与 7 大核心目录](#一系统总体架构与-7-大核心目录)
2. [核心技术特性与设计优势](#二核心技术特性与设计优势)
3. [快速开始与环境搭建](#三快速开始与环境搭建)
4. [统一 API 接入与异步 Worker 架构](#四统一-api-接入与异步-worker-架构)
5. [支持的垂直业务领域与任务线（重点：Meeting 领域全面重构）](#五支持的垂直业务领域与任务线)
6. [多租户数据物理沙箱隔离规范](#六多租户数据物理沙箱隔离规范)
7. [质量保障与全套自动化测试（233+ 测试项）](#七质量保障与全套自动化测试)
8. [领域与任务线标准扩展指南](#八领域与任务线标准扩展指南)

---

## 一、系统总体架构与 7 大核心目录

AgentFlow 遵循严格的分层单向依赖原则（`app/` -> `domains/` -> `core/` <- `infra/`），根目录下仅保留具备清晰边界的 7 大核心目录：

```text
AgentFlow/
├── app/                          # 【应用交付层】FastAPI 网关与异步队列调度子系统
│   ├── api/                      # Web API 接入层（路由、中间件、依赖注入、健康探针）
│   ├── worker/                   # 独立异步 Worker 消费者（Redis 队列消费、分布式租约、心跳续期）
│   ├── config.py                 # 应用级配置与环境解析（样式/模板/产物目录解析）
│   ├── schemas.py                # 强类型请求与响应 Pydantic DTO
│   ├── tasklines.py              # 任务线与领域白名单唯一声明表
│   └── tasks.py                  # 任务请求装配分发器与样式门禁校验
│
├── core/                         # 【核心编排内核】多 Agent 协同调度与规则门禁
│   ├── graph/                    # LangGraph DAG 拓扑图构建、状态合并（State）与通用节点抽象
│   ├── runner/                   # 任务执行驱动器、纯领域事件流协议（TaskEvent）与上下文
│   ├── schema/                   # 结构化模型输出契约 DSL、校验与确定性降级规则
│   ├── execution/                # 硬执行门禁（上游对齐、表行截断、超长段落重写与防幻觉拦截）
│   ├── templates/                # 动态模板引擎（自动判型、占位符填充、篇幅预算与门禁白名单）
│   ├── registry/                 # 领域与任务线动态注册表
│   └── runtime/                  # 运行时状态、进度通知与渲染上下文支持
│
├── domains/                      # 【垂直业务领域】高内聚、自包含的业务 Agent 集群
│   ├── meeting/                  # 会议领域（经历全面工业级重构：双阶段流水线、8 大任务线、审核短路与全套自愈）
│   ├── notes/                    # 笔记与知识领域（知识图谱、智能题库、资料整理、目录编排、复习清单）
│   └── shared/                   # 跨领域共享业务组件
│       ├── perspective/          # 跨域通用视角建模（真人档案适配、第一人称代词转换、动作归属、关注雷达图）
│       ├── supervisor/           # 全局监督标准与通用 Prompt 注入
│       └── base.py               # 领域上下文与生命周期钩子（DomainHooks）协议
│
├── infra/                        # 【基础设施适配层】外设适配与技术底层实现
│   ├── llm/                      # 统一 LLM 客户端抽象（适配 HTTP、WebSocket 与本地 vLLM，支持括号栈自愈）
│   ├── ocr/                      # OCR 引擎抽象驱动（PaddleOCR、RapidOCR、ServerOCR）与版面去噪纠错
│   ├── storage/                  # 物理持久化基座（多租户路径解析器、Redis 状态存储、ChromaDB 向量库）
│   ├── memory/                   # 长期记忆与向量索引基础设施
│   ├── telemetry/                # 统一结构化可观测性日志与 Token / 性能监控
│   └── exporters/                # 统一产物导出器（专业响应式 CSS HTML、Markmap 导图、SVG 拓扑）
│
├── resources/                    # 【业务只读资产库】静态模板、样式规范与标准化画像
│   ├── templates/                # 32 份垂直场景行业 Markdown 模板（通用纪要、团队周会、共识决策、辩论、法庭等）
│   ├── styles/                   # 5 大会议纪要风格规范 Markdown 模板（brief, topic, review, retro, alignment）
│   ├── profiles/                 # 客观全员与各行业职业角色画像模板（JSON）
│   └── role_mapping.json         # 角色与职业画像别名映射表
│
├── data/                         # 【多租户数据持久化根】严格按 {user_id} 物理隔离的沙箱
│   └── {user_id}/                # 租户独立命名空间（docs 原始素材、output 产物、knowledge 索引）
│
├── tools/                        # 【离线研发运维工具集】代码生成脚手架与排查运维（生产严禁反向依赖）
│   ├── codegen/                  # 领域/任务线代码生成（register_domain, register_task, sync_domain）
│   └── devtools/                 # 离线数据排查与维护（check_user_profile, purge_kb_source）
│
└── tests/                        # 【自动化测试中心】零 LLM 单元测试与集成测试套件（13 个套件，233+ 测试项）
```

---

## 二、核心技术特性与设计优势

### 1. 纯强类型领域事件流协议（Pure TaskEvent Protocol）
内核引擎彻底剔除对 Web 框架（FastAPI / StreamingResponse）的反向依赖。`core/runner/` 产出强类型的结构化领域事件：
```python
@dataclass
class TaskEvent:
    type: Literal["phase", "chunk", "done", "error"]
    payload: dict[str, Any]
```
- **Web API 消费**：将其转换为标准 NDJSON 流实时下发给客户端；
- **Worker 消费**：直接监听事件对象并流水线推入 Redis，内存零二次反序列化开销。

### 2. 双轨任务执行架构（API Inline & Worker Queue）
- **Inline 模式（轻量化）**：单进程内联异步执行，适合本地研发、轻量测试及快速集成验证；
- **Queue 模式（生产高可用）**：API 进程仅负责任务受理与状态查询。作业入队至 Redis，由独立运行的 `python -m app.worker.main` 集群消费。支持基于 ZSet 的分布式租约心跳（Lease Heartbeat）、节点崩溃自动回收自愈、指数退避重试与优雅平滑停机（Graceful Shutdown）。

### 3. 严格的多租户物理沙箱隔离（Strict Multi-Tenant Sandbox）
通过统一的 `infra.storage.path_resolver.StoragePathResolver` 严格控制文件读写路径：
- 租户原始素材位于 `data/{user_id}/docs/`；
- 每次请求的生成产物位于 `data/{user_id}/output/{request_id}/`；
- 租户专有知识库索引位于 `data/{user_id}/knowledge/chromadb/`。
所有路径均进行防穿透校验，严禁回退到无主公共目录，杜绝越权访问。

### 4. 严密的契约驱动与防幻觉硬门禁（Contracts & Execution Gate）
- **生成契约**：严格限定每个 Agent 节点输出的 JSON 结构与字段类型；
- **程序化容错修复**：在 `infra/llm/` 客户端层提供括号栈补全，平滑修复长文本截断导致的 JSON 损坏；
- **执行硬门禁与白名单**：上游事实硬对齐检查、单栏篇幅预算自适应重写、同名标签防粘连修复、空栏目自动识别，并在模板门禁中设立合法状态白名单，最大程度抑制大模型幻觉与乱序。

---

## 三、快速开始与环境搭建

### 1. 环境准备
系统推荐运行在 **Python >= 3.9** 环境中（经严格测试兼容 Python 3.9 ~ 3.12）。

```bash
# 1. 克隆代码仓库
git clone <repository_url>
cd AgentFlow

# 2. 创建并激活虚拟环境
python3 -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

# 3. 安装依赖包
pip install -r requirements.txt
```

### 2. 配置环境变量（`.env`）
在项目根目录创建 `.env` 文件，根据实际部署的基础设施配置：

```dotenv
# ── 大语言模型驱动配置（支持 http / websocket / vllm）──────
LLM_BACKEND=http
DEEPSEEK_API_KEY=sk-your-api-key-here
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEMPERATURE=0.0

# ── 异步任务队列与 Redis 存储（生产推荐）────────────────
REDIS_URL=redis://127.0.0.1:6379/0
# 任务运行模式：inline（单进程内跑）或 queue（Redis 队列由独立 Worker 消费）
AGENTFLOW_RUN_MODE=inline

# ── OCR 驱动引擎配置（支持 serverocr / paddleocr / rapidocr）
OCR_ENGINE=serverocr

# ── 系统结构化日志配置 ─────────────────────────────────
AGENTFLOW_LOG_LEVEL=INFO
AGENTFLOW_LOG_FILE=logs/agentflow.log
AGENTFLOW_DIAG_LOG_FILE=logs/diag.log
```

### 3. 启动服务进程

#### 启动 Web API 网关
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
- API 文档访问地址：`http://localhost:8000/docs` (Swagger UI) 或 `/redoc`；
- 健康探针接口：`GET /api/v1/health`。

#### 启动后台 Worker 消费者（当 `AGENTFLOW_RUN_MODE=queue` 时）
```bash
python -m app.worker.main --concurrency 4 --grace 300
```
- `--concurrency`：设置单个 Worker 进程的并发作业槽数量（推荐 4~8）；
- `--grace`：收到 SIGTERM / SIGINT 停机信号时的排空优雅超时等待秒数。

---

## 四、统一 API 接入与异步 Worker 架构

系统向外统一暴露两组标准化 API 接入路径，所有接口均支持多租户物理沙箱隔离与强类型数据契约校验：

### 1. 统一实时作业接口 (`/api/agent/v1`)
所有垂直领域和具体任务线均通过统一的入口交互，由请求体中的 `domain` 和 `task` 进行动态分发：

* **同步执行**：`POST /api/agent/v1`（阻塞等待直至全部流程完成，返回统一快照结果）；
* **流式执行**：`POST /api/agent/v1/stream`（基于 `application/x-ndjson` 实时逐行下发阶段切换事件、流式正文分块与完成事件）；
* **产物下载**：`GET /api/agent/v1/file/{request_id}/{file_name}`（直接获取本次作业生成的单文件 HTML 网页、`result.md` 源码或导图文件）。

### 2. 生产统一异步任务接口 (`/api/agent/v1/async`)
专为长耗时作业设计的标准异步控制面，支持分布式 Worker 消费与断网重连续传：

| 方法与路径 | 功能定位 | 核心特性与说明 |
|---|---|---|
| `POST /api/agent/v1/async` | 异步任务提交 | 提交任务入参，立即返回 `job_id` 与 `request_id`（状态为 `queued`），不阻塞长耗时推理 |
| `GET  /api/agent/v1/async/{job_id}` | 状态与进度轮询 | 查询当前任务状态（`queued` / `running` / `succeeded` / `failed`）及当前执行阶段，响应体量极小（`text` 恒为 `null`），专供前端高频轮询 |
| `GET  /api/agent/v1/async/{job_id}/stream?cursor=0` | 增量事件流追溯 | 基于 NDJSON 订阅任务生命周期事件，支持 `cursor` 断点续传与网络闪断重连 |
| `GET  /api/agent/v1/async/{job_id}/result` | 最终全量结果获取 | 任务达到终态后获取完整 Markdown 正文（`text`）与产物文件名（`file_name`）；未完成时返回 200 快照而不报错 409 |

> [!NOTE]
> 为保障老版本客户端平滑过渡，系统同时提供 `/api/v1/tasks` 系列路径的静默兼容支持。

### 3. 标准化请求体结构 (`DomainTaskRequest`)
同步提交与异步提交共用同一套强类型入参契约：

```json
{
  "domain": "meeting",
  "task": "minutes",
  "memory": true,
  "texts": {
    "transcript": "周宁：今天主要复盘开发进展。林夏：算法侧纪要生成主流程已经稳定……",
    "keypoints": "",
    "notes": ""
  },
  "docs": [],
  "extra": {
    "time": "2026-09-01",
    "template": "",
    "profile": "user",
    "catalog": "",
    "project": "小艺慧记Agent",
    "subject": "",
    "style": "brief"
  }
}
```

* **HTTP Header 请求头要求**：
  * `X-User-Id: <user_id>`（**必需**）：租户唯一身份标识，驱动后端多租户目录隔离；
  * `X-Request-Id: <request_id>`（*可选*）：全链路调用追踪号，未传时由系统自增生成。
* **核心字段说明**：
  * `domain`（字符串，**必填**）：垂直业务领域（`"meeting"` 会议领域、`"notes"` 笔记领域）；
  * `task`（字符串，**必填**）：具体任务线代码（如 `"minutes"`、`"actions"`、`"risks"`、`"consensus_decision"`、`"minutes_styles"` 等）；
  * `memory`（布尔值，*可选*）：顶层记忆增强开关，开启后自动检索并写回跨场次事实与图谱记忆；
  * `texts`（键值对，*可选*）：原始文本集合（`transcript` 会议文本、`keypoints` 关键点、`notes` 用户速记）；
  * `docs`（文件名数组，*可选*）：需引用的原始文档名列表（存放于 `data/{user_id}/docs/`）；
  * `extra.time`（字符串，*可选*）：会议日期或时间（如 `"2026-09-01"`）；
  * `extra.style`（字符串，*可选*）：用于 `minutes_styles` 任务，严格限传 5 类（`"brief"`, `"topic"`, `"review"`, `"retro"`, `"alignment"`），非法值秒判 400；
  * `extra.profile`（字符串，*可选*）：视角档案模式（`"user"` 个人工作台视角、`"objective"` 客观全员）；
  * `extra.template`（字符串，*可选*）：显式指定的模板标识，留空时系统自动分发匹配。

### 4. 标准化统一响应快照
无论是同步接口还是异步接口，均返回一致的 8 字段结构化快照：

```json
{
  "code": 0,
  "job_id": "job_637547664132538372",
  "request_id": "req_20260901_001",
  "status": "succeeded",
  "message": "success",
  "text": "# 会议纪要\n\n## 会议概况\n本场会议主要复盘系统稳定性与交付进度……",
  "file_name": "minutes.html",
  "monitor": {
    "token_usage": 1580,
    "cache_hit": 1,
    "cost_time": 3.85
  }
}
```

---

## 五、支持的垂直业务领域与任务线

### 1. 会议领域（Meeting Domain - `domains/meeting/`）—— 经历彻底工业级重构

会议领域经历了一轮体系化的大重构，在架构解耦、执行性能、提示词工程与产物呈现上实现了全面升级：

#### 架构革新：先行理解层 + 视角建模层 + 8 任务线解耦
- **公共事实先行底座（Meeting Core）**：
  - `MeetingUnderstandingAgent` 独立提炼事实，采用 30~60 字极简骨架口径提纯，杜绝死板搬运；
  - **场景感知（`scene_hint.py`）**：依据所选模板特征动态注入指导方针；
  - **模板感知跳过（`understanding_skip.py`）**：对无需全量要素的模板，自适应按需裁剪字段抽取，降低延迟与 Token 开销。
- **双模视角建模（Perspective Modeling）**：
  - **客观全员视角（`objective`）**：保持完全中立第三方的全局纪要视野；
  - **个人专属视角（`user`）**：自动套用四栏专属工作台模板（`personal_minutes.md`：我的待办、重点关注、项目进展、我提出的未决），完成第一人称发言人代词智能归集（我 / 我方 / 同事），生成发言切片与关注度雷达图。
- **无依赖钩子挂载（`DomainHooks`）**：
  - 核心编排引擎不反向依赖领域模块，通过 `hooks.py` 统筹会议记忆回写（`persist_memory`）、前置准备（`prepare_memory`）及各线专有 HTML 导出器。

#### 性能与稳定性攻坚：审核短路与理解瘦身
- **短会极速放行（Fast-Path Bypass）**：原文 < 2000 字符或（议题≤2 且发言人≤2）时，直接跳过耗时的 LLM 审核节点，毫秒级快速 Approve 放行；
- **规则守卫门禁（Quick Facts Guardrail）**：2000~5000 字符区间引入零 LLM 事实守卫（人名在册率与关键数字忠实度），全过直接放行，命中红线才唤醒 LLM 深度送审；
- **送审稿精简瘦身（Compact Draft for Review）**：自动剥离程序强对齐字段，仅对推导提炼字段进行微截取送审，审核 Token 减少 60%+，并严格解耦 `review_bypassed` 与审核失败语义。

#### 8 大任务线重构细节全览

| 任务线代码 (`task`) | 中文名称 | 执行模式 (`kind`) | 导出产物 | 核心能力与重构成果 |
|---|---|---|---|---|
| **`minutes`** | 会议纪要 | `LLM_DOCUMENT` | `minutes.html`<br>`result.md` | **32 套场景模板动态路由**：覆盖周会、访谈、医疗、法庭、研讨等全场景，极简公文流排版，严禁 emoji 与套话；集成个人专属工作台模板；输出高保真响应式交互网页。 |
| **`consensus_decision`** | 共识决策 | `LLM_DOCUMENT` | `consensus_decision.html`<br>`result.md` | **彻底模板化重构**：由硬编码 Python 拼接升级为由 `resources/templates/consensus_decision.md` 模板驱动的标准大模型渲染。分为「决策总览」（精炼一句话决议矩阵）与「决策细节」（决策背景、讨论要点、得失权衡、最终决议 4 组阶梯展开，压轴决议，多条目独立列点，零 emoji，弹性输出）。模板门禁白名单全面放行共识标记，消除误报修补；配套响应式卡片流 HTML 导出。 |
| **`minutes_styles`** | 多样式纪要 | `LLM_DOCUMENT` | `minutes_styles.html`<br>`result.md` | **5 大黄金样式规范重构**：独立拆解 5 套标准模板至 `resources/styles/`（`brief` 极简速报、`topic` 议题专报、`review` 深度研讨、`retro` 敏捷复盘、`alignment` 战略对齐）。首栏 250-300 字摘要预算控制；API 强门禁校验非法样式；输出样式定制卡片 HTML。 |
| **`actions`** | 待办提取 | `LLM_EXTRACT` | `actions.html`<br>`result.md` | **Form A 现代工单票据卡片流**：事项按业务分类（Category）聚类归集，事项名称、优先级（高/中/低）、责任人、截止时间、交付标准、前置条件弹性展开，无则优雅省略，拒绝冗余占位符。 |
| **`risks`** | 风险分析 | `LLM_EXTRACT` | `risks.html`<br>`result.md` | **Form A 风险票据流**：按风险分类归集，红黄绿三级严重度预警，结构化提取责任归属、潜在影响与规避对策，输出交互式风险看板。 |
| **`minutes_trace`** | 溯源纪要 | `DETERMINISTIC_PIPELINE`<br>(Sidecar) | `minutes_trace.html`<br>`result.md` | **平实两级溯源结构**：摒弃生硬特殊标记，采用「会议概况 + 议题名称」两级平实排版；采用议题内涵加权（Jaccard + 词频）切片匹配原声，点击纪要要点一键定位高亮发言气泡与时间戳。 |
| **`agenda_minutes`** | 议程纪要 | `LLM_EXTRACT` | `agenda_minutes.html`<br>`result.md` | **议程 OCR 锚定与对齐**：支持议程单图片识别，通过议程类型强制转换（Agenda Coercion）阈值守卫将讨论内容按序锚定至议程看板。 |
| **`mindmap`** | 思维导图 | `LLM_DOCUMENT` | `mindmap.html`<br>`mindmap.png` | **交互式拓扑大纲**：自动提炼多层级思维导图 Markdown 拓扑，基于 Markmap 渲染交互式 HTML 页面与高清图片。 |

---

### 2. 笔记与知识领域（Notes Domain - `domains/notes/`）
面向知识库工程、学习分析与文档资产化：
- **`catalog`（知识目录编排）**：基于原文 Markdown 骨架树逐级提纯章节、主题与知识点卡片，同步输出 Markdown 层级树与可视化交互网页 `catalog.html`；
- **`checklist`（复习清单卡片）**：动态预算驱动的分批并行精细化知识点解析，产出 `checklist.html`；
- **`graph`（知识图谱构建）**：实体与关系抽取，生成基于 Cytoscape.js 的交互式学习地图；
- **`library`（资料智能入库）**：支持 PPT、PDF、Word 文档与笔记图片的版面分析、公式纠错与向量化存储；
- **`quiz`（自测题目生成）**：结合领域题库与教学大纲生成匹配测试题；
- **`review`（笔记审校与评注）**：对原始笔记进行学术性纠错与概念补全。

---

## 六、多租户数据物理沙箱隔离规范

所有用户数据均强制物理落地在 `data/{user_id}/` 下，结构完全自闭环：

```text
data/
└── {user_id}/                    # 严格按用户唯一 ID 物理隔离
    ├── docs/                     # 用户上传的待处理素材（文档、图片、音频文字稿）
    ├── output/{request_id}/      # 每次调用的隔离生成产物目录
    │   ├── result.md             # 最终生成的标准化 Markdown 文本
    │   ├── {task}.html           # 针对各任务线定制的专属交互式单文件 HTML（如 minutes.html / actions.html）
    │   └── {task}.png            # 渲染图表（如有）
    ├── knowledge/
    │   ├── chromadb/             # 该租户专享的向量检索库文件
    │   └── catalogs/             # 租户生成的学科/领域知识目录 JSON
    ├── memory/                   # 跨会话长期沉淀记忆（会议场次状态机、图谱增量更新）
    └── profile/
        └── user.json             # 租户专属个性化画像档案（偏好、职责、习惯）
```

用户可通过统一产物下载端点直接获取产物：
- 获取精美交互网页：`GET /api/agent/v1/file/{request_id}/{file_name}?user_id={user_id}`
- 获取 Markdown 源码正文：`GET /api/agent/v1/file/{request_id}/result.md?user_id={user_id}`

---

## 七、质量保障与全套自动化测试

AgentFlow 内置了严密的**零 LLM 确定性回归测试套件**，总计拥有 **13 个专项测试套件，233+ 测试用例**，能在秒级内快速完成核心业务逻辑、契约不变量与语法规则的验证，无需消耗外部模型 Token：

| 测试模块文件 | 测试定位与主要断言覆盖 | 用例数 |
|---|---|---|
| `test_consensus_decision_refactor.py` | 验证 `consensus_decision` 模板驱动解析、门禁白名单、鲁棒标题归一化与 HTML 卡片渲染 | 9 |
| `test_minutes_styles_refactor.py` | 验证 5 大样式模板规范、250-300 字首栏预算、API 门禁校验、Supervisor 契约与 HTML 导出 | 8 |
| `test_supervisor_optimization.py` | 验证审核短路（<2000 字符快速放行）、事实守卫（人名/数字门禁）、送审稿精简瘦身与契约口径 | 9 |
| `test_action_risk_flow_render.py` | 验证待办与风险的 Form A 工单/票据流 Markdown 渲染与 HTML 响应式卡片导出 | 8 |
| `test_minutes_trace_refactor.py` | 验证溯源纪要两级平实结构、议题内涵加权（Jaccard）切片算法、时间戳锚点与 HTML 定位高亮 | 4 |
| `test_template_router.py` | 验证 32 套垂直场景模板自动判型、占位符清洗、栏目字数预算自适应截断与门禁验收 | 86 |
| `test_perspective.py` | 验证个人视角工作台模板路由、第一人称代词替换、动作归属、发言切片与雷达图计算 | 22 |
| `test_agenda_coercion.py` | 验证议程类型强制转换（Agenda Coercion）阈值守卫与边界行为 | 11 |
| `test_agenda_minutes.py` | 验证议程纪要端到端全链路行为与 OCR 锚定集成 | 32 |
| `test_meeting_memory.py` | 验证跨场次长期记忆状态机、向量索引与事实溯源回写 | 25 |
| `test_core.py` | 验证画像选档、角色合并、契约校验与基础不变式 | 13 |
| `test_engine_smoke.py` | 验证 LangGraph DAG 拓扑调度流转与纯 TaskEvent 事件流驱动 | 5 |
| `test_draft_scrape.py` | 验证草稿与上下文抽取标记的一致性解析 | 1 |

```bash
# 运行全套自动化测试套件
python -m pytest tests/

# 单独运行重构核心模块测试套件
pytest tests/test_consensus_decision_refactor.py -v
pytest tests/test_minutes_styles_refactor.py -v
pytest tests/test_supervisor_optimization.py -v
pytest tests/test_template_router.py -q
```

---

## 八、领域与任务线标准扩展指南

系统遵循开放封闭原则（Open-Closed Principle）。通过内置的脚手架工具集（`tools/codegen/`），新增业务领域与任务线可实现开箱即用的自动化装配：

### 1. 新建垂直领域
```bash
python tools/codegen/register_domain.py --domain notes --name "笔记"
```
自动生成统一目录规范、工厂、配置和内置的视角建模（Perspective）。

### 2. 新建任务线骨架
```bash
python tools/codegen/register_task.py --domain meeting --task digest --name "摘要" --with-report
```
1. 自动生成契约模板（`contracts.py`）、提示词模板（`prompts.py`）、步骤实现（`steps/`）与最终报表模型（`reports.py`）；
2. 根据业务在 `contracts.py` 中定义结构化字段与审核规则，在 `prompts.py` 中编写精准提示词；
3. 一键同步代码生成区并执行静态一致性校验：
   ```bash
   # 同步并写入全量生成区（models_generated.py, orchestrator.py 等）
   python tools/codegen/sync_domain.py --domain meeting

   # CI 级别一致性严格校验（不修改文件，仅校验一致性）
   python tools/codegen/sync_domain.py --domain meeting --check
   ```
4. 在 `domains/<domain>/hooks.py` 挂载专有 HTML 导出器（如有），并在 `app/tasklines.py` 声明该任务线。系统将自动为其挂载 HTTP 接入端点与监控报表。

---

## 许可证
本项目采用 MIT 许可证开源。详见 LICENSE 文件。
