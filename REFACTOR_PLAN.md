xianz# AgentFlow 架构重构与七大目录迁移改进清单

> 本文档针对 AgentFlow 项目当前的代码组织形态与技术债务，提出一套符合业界标准、生产就绪（Production-Ready）的 **7 大核心顶层目录重构方案**。
> 方案全面覆盖现有 334+ 个 Python 源码文件、31+ 场景模板与静态资产，并对核心耦合点给出针对性重构设计。

---

## 目录索引
1. [总体设计理念与顶层架构对比](#一总体设计理念与顶层架构对比)
2. [七大核心目录深度拆解与文件映射清单](#二七大核心目录深度拆解与文件映射清单)
   - [1. app/（应用交付与调度网关）](#1-app应用交付与调度网关)
   - [2. core/（多 Agent 编排调度内核）](#2-core多-agent-编排调度内核)
   - [3. domains/（垂直业务领域与 Agent 集群）](#3-domains垂直业务领域与-agent-集群)
   - [4. infra/（基础设施与外设适配层）](#4-infra基础设施与外设适配层)
   - [5. resources/（业务静态资产与模板库）](#5-resources业务静态资产与模板库)
   - [6. data/（多租户数据持久化根目录）](#6-data多租户数据持久化根目录)
   - [7. tests/（自动化测试与质量中心）](#7-tests自动化测试与质量中心)
3. [四大关键重构专项设计](#三四大关键重构专项设计)
   - [专项 A：消除 app/tasks.py 上帝文件，下沉领域特判](#专项-a消除-apptaskspy-上帝文件下沉领域特判)
   - [专项 B：重构 Worker 异步执行链路，切断对 HTTP 传输层的反向依赖](#专项-b重构-worker-异步执行链路切断对-http-传输层的反向依赖)
   - [专项 C：渲染器 Exporters 统一归位，彻底分离 memory 与 render](#专项-c渲染器-exporters-统一归位彻底分离-memory-与-render)
   - [专项 D：严格落地基于 user_id 的数据物理沙箱](#专项-d严格落地基于-user_id-的数据物理沙箱)
4. [五阶段平滑迁移实施路线图](#四五阶段平滑迁移实施路线图)

---

## 一、总体设计理念与顶层架构对比

### 1. 核心设计原则
* **认知负载平衡（7 ± 2 法则）**：避免 4 个目录过分内卷嵌套，也避免 13 个目录的过度碎片化。根目录仅保留 7 个具备明确边界的重量级子系统。
* **分层单向依赖（Clean Architecture）**：`app/` -> `domains/` -> `core/` <- `infra/`。业务编排不依赖具体 Web 框架，Worker 不依赖 HTTP 响应对象。
* **高内聚自闭环（Domain-Driven）**：领域旗下的任务线自包含提示词、契约、步骤与特有输入清洗，新增任务对外部系统零侵入。
* **严格多租户数据沙箱**：所有用户输入、运行时输出、向量索引、长期记忆均以 `data/{user_id}/` 为物理边界，禁止公共越权回退。

### 2. 根目录对照表

| 现有混乱根目录 (9+ 个) | 重构后黄金架构 (7 大目录) | 核心定位与职责 |
|---|---|---|
| `app/` (混杂 API、Worker、任务特判) | **`app/`** | 统一应用交付：分离为 `app/api/` (FastAPI) 与 `app/worker/` (Redis 消费) |
| `tools/core/` + `tools/runtime/` + `tools/schema/` | **`core/`** | 纯净编排引擎：LangGraph 调度、State 状态合并、事件流协议、动态注册表 |
| `domain/` + 根目录 `perspective/` | **`domains/`** | 垂直业务模型：`meeting/`、`notes/` 以及跨域收拢的 `shared/perspective/` |
| `tools/llm/` + `tools/ocr/` + `tools/memory/` + `tools/exports/` | **`infra/`** | 基础设施适配：LLM、OCR、存储/Redis、向量库，以及统一的 Exporter 导出器 |
| 根目录 `template/` + `assets/profiles/` | **`resources/`** | 业务只读资产：31+ 场景 Markdown 模板、画像 JSON 模板、角色映射表 |
| `data/` (混杂测试文件与临时产物) | **`data/`** | 数据持久化根：严格按 `{user_id}` 物理隔离的用户级沙箱 |
| `tests/` + 混乱的 `api_test/` (混有 21 张大图) | **`tests/`** | 自动化测试套件：分为 `unit/`、`integration/`，提取测试图片至 `fixtures/` |

---

## 二、七大核心目录深度拆解与文件映射清单

### 1. `app/`（应用交付与调度网关）

#### 目标结构
```text
app/
├── api/                          # Web API 接入子系统
│   ├── routes/
│   │   ├── agent.py              # 统一接口 /api/agent/v1（同步、流式、下载）
│   │   ├── tasks.py              # 异步任务接口 /api/v1/tasks（提交、查询、状态、事件流）
│   │   ├── preview.py            # 产物预览路由（原 meeting.py、notes.py 合并）
│   │   └── health.py             # 健康检查与探针（/api/v1/health）
│   ├── middlewares/              # 全局日志跟踪、RequestId 注入、CORS、全局异常捕获
│   ├── dependencies.py           # FastAPI 依赖注入项（获取 LLMClient、Redis、Storage 实例）
│   └── main.py                   # FastAPI 应用入口（原 app/main.py 瘦身）
├── worker/                       # 独立异步 Worker 子系统
│   ├── consumer.py               # Redis 队列消费者（并发槽调度、超时回收、优雅停机）
│   ├── lease.py                  # ZSet 租约管理与心跳定时续期器
│   ├── executor.py               # 异步作业执行体（直接监听 Core 事件流写入 Redis，彻底解耦 HTTP）
│   └── main.py                   # Worker 进程入口（python -m app.worker.main）
├── schemas.py                    # 请求/响应 Pydantic 模型（TaskRequest, TaskResponse, Monitor）
├── config.py                     # 应用级配置（Pydantic Settings 读取 .env）
└── tasklines.py                  # 对外任务线与领域白名单声明表
```

#### 详细文件迁移映射
* 原 `app/main.py` -> 拆分出通用配置后迁入 `app/api/main.py`
* 原 `app/routes/agent.py` -> 迁入 `app/api/routes/agent.py`
* 原 `app/routes/tasks.py` -> 迁入 `app/api/routes/tasks.py`
* 原 `app/routes/meeting.py` + `app/routes/notes.py` + `app/routes/_registry.py` -> 合并消除模板样板代码，迁入 `app/api/routes/preview.py`
* 原 `app/worker.py` -> 拆解为 `app/worker/consumer.py`、`app/worker/lease.py`、`app/worker/main.py`
* 原 `app/executor.py` -> 迁入 `app/worker/executor.py`（剥离字节流解析）
* 原 `app/job_store.py` -> 迁入 `infra/storage/redis_store.py`，app 层通过依赖调用
* 原 `app/tasks.py` -> **彻底拆解**：通用流程留存，特判下沉到各自 domain（见专项 A）

---

### 2. `core/`（多 Agent 编排调度内核）

#### 目标结构
```text
core/
├── graph/                        # LangGraph 图调度
│   ├── builder.py                # 多任务线并行 DAG 拓扑构建器
│   ├── state.py                  # 共享 State 基类与 Reducer 浅合并算法
│   └── nodes.py                  # 通用节点抽象（生成节点、审核节点、返工路由节点）
├── runner/                       # 核心运行与事件机制
│   ├── runner.py                 # 通用任务驱动器（生命周期管理、落盘编排）
│   └── events.py                 # 【重要】纯 Python 结构化领域事件协议（TaskEvent, Phase, Chunk, Done）
├── registry/                     # 【核心解耦】动态注册表（取代 AST 正则重写源码）
│   ├── domain_registry.py        # 领域注册器
│   └── task_registry.py          # 任务线注册装饰器（@register_task）
├── schema/                       # 契约与输出校验
│   ├── contracts.py              # GenerationContract, SupervisorContract DSL
│   ├── validation.py             # 结构化模型输出校验
│   └── fallback.py               # 结构化降级规则 DSL
├── execution/                    # 执行规范
│   └── gate.py                   # 上游硬对齐、表行截断、验收硬门禁
└── templates/                    # 模板解析引擎（原 tools/templates/）
    ├── router.py                 # 模板判型、占位填充、门禁检查
    ├── evaluator.py              # 通用约束评测与粘连修复
    └── budget.py                 # 篇幅预算与 prompt 拼装
```

#### 详细文件迁移映射
* 原 `tools/core/domain_engine.py` -> 拆分纯通用编排入 `core/graph/nodes.py` 与 `core/graph/builder.py`
* 原 `tools/core/runner.py` -> 迁入 `core/runner/runner.py`
* 原 `tools/core/runtime_context.py` -> 迁入 `core/runner/context.py`
* 原 `tools/schema/contracts.py` -> 迁入 `core/schema/contracts.py`
* 原 `tools/schema/validation.py` -> 迁入 `core/schema/validation.py`
* 原 `tools/schema/fallback_rules.py` -> 迁入 `core/schema/fallback.py`
* 原 `tools/execution/hard_execution.py` -> 迁入 `core/execution/gate.py`
* 原 `tools/templates/router/` -> 迁入 `core/templates/router.py`
* 原 `tools/templates/template_eval.py` -> 迁入 `core/templates/evaluator.py`
* 原 `tools/templates/length_budget.py` + `template_prompt.py` -> 迁入 `core/templates/budget.py`
* 原 `tools/runtime/kinds.py` + `render.py` -> 迁入 `core/graph/nodes.py`

---

### 3. `domains/`（垂直业务领域与 Agent 集群）

#### 目标结构
```text
domains/
├── shared/                       # 跨领域共享业务资产
│   ├── perspective/              # 【收归正统】原根目录 perspective/ 完整迁入
│   │   ├── agent.py              # 视角建模 Agent
│   │   ├── hits.py               # 点名表、发言人命中判定、动作归属
│   │   ├── preferences.py        # 用户偏好块拼装、人称代词转换
│   │   ├── synth.py              # 画像综合合成
│   │   └── contracts.py / models.py / prompts.py
│   ├── supervisor/               # 全局监督标准（原 domain/_shared/）
│   │   ├── global_supervisor.py
│   │   └── prompts.py
│   └── base.py                   # BaseDomainContext 与 DomainHooks 抽象定义
│
├── meeting/                      # 会议领域
│   ├── config.py                 # 领域配置与任务线声明（原 domain_config.py）
│   ├── state.py                  # MeetingState TypedDict（从 models.py 独立）
│   ├── models.py                 # 业务输出模型（原 models.py, models_base.py）
│   ├── reports.py                # 最终报告聚合定义
│   ├── hooks.py                  # 会议专有生命周期钩子（记忆适配、输入预处理）
│   ├── core/                     # 会议事实理解（原 meeting_core/）
│   │   ├── agent.py
│   │   ├── contracts.py
│   │   └── prompts.py
│   ├── memory/                   # 会议跨场次记忆追踪（彻底剥离 HTML 渲染）
│   │   ├── registry.py / sessions.py / runtime.py / state.py / store.py
│   ├── tasks/                    # 8 条任务线自闭环包
│   │   ├── minutes/              # 纪要
│   │   ├── actions/              # 待办
│   │   ├── agenda_minutes/       # 议程纪要（收归原在 app/tasks.py 里的 agenda OCR 特判）
│   │   ├── consensus_decision/   # 共识决策
│   │   ├── mindmap/              # 思维导图
│   │   ├── minutes_styles/       # 多样式纪要
│   │   ├── minutes_trace/        # 溯源纪要（剥离 html.py 到 infra/exporters/）
│   │   └── risks/                # 风险分析
│
└── notes/                        # 学习笔记领域
    ├── config.py / state.py / models.py / reports.py / hooks.py
    ├── core/                     # 笔记理解底座（原 notes_core/）
    ├── memory/                   # 图谱记忆演进（graph.py, resolve.py）
    ├── integrations/             # 领域外部客户端（原 exercise_search 高中题库搜索）
    │   ├── client.py / catalog.py / match.py / tex.py
    └── tasks/                    # 6 条任务线（catalog, checklist, graph, quiz...）
```

#### 详细文件迁移映射
* 原根目录 `perspective/*` -> 全部迁入 `domains/shared/perspective/`
* 原 `domain/_shared/*` -> 迁入 `domains/shared/supervisor/`
* 原 `domain/meeting/` -> 迁入 `domains/meeting/`
  * 提取 `domain/meeting/models.py` 中的 `MeetingState` 存入 `domains/meeting/state.py`
  * 将 `domain/meeting/memory/render.py` 中的 HTML 渲染函数拆分迁入 `infra/exporters/html/`
  * 将 `domain/meeting/tasks/minutes_trace/html.py` 迁入 `infra/exporters/html/trace_review.py`
* 原 `domain/notes/` -> 迁入 `domains/notes/`
  * 原 `domain/notes/exercise_search/` 迁入 `domains/notes/integrations/exercise_search/`

---

### 4. `infra/`（基础设施与外设适配层）

#### 目标结构
```text
infra/
├── llm/                          # 大模型客户端适配
│   ├── client.py                 # 统一 LLMClient（原 tools/llm/llmclient.py）
│   └── config.py                 # HTTP、WebSocket、vLLM 后端驱动配置
├── ocr/                          # OCR 引擎与版面处理
│   ├── engines/                  # PaddleOCR、RapidOCR、ServerOCR 驱动
│   ├── layout/                   # 自适应页眉页脚剔除、跨页去噪
│   └── formatters/               # KaTeX/LaTeX 公式纠错与 Markdown 归一化
├── storage/                      # 存储基础设施
│   ├── redis_store.py            # Redis 任务状态、事件流与队列底层操作
│   ├── vector_store.py           # ChromaDB 向量数据库封装
│   ├── path_resolver.py          # 【重要】严格隔离的 user_id 路径解析器
│   └── file_storage.py           # 本地/对象存储读写门面
├── memory/                       # 向量化记忆底层支持（原 tools/memory/）
│   ├── embed.py / entities.py / store.py
├── telemetry/                    # 可观测性
│   ├── logging.py                # 结构化统一日志（原 tools/core/logging_config.py）
│   └── monitor.py                # Token 消耗计算、缓存命中率分析
└── exporters/                    # 【统一集中】全部产物渲染与导出器（原 tools/exports/）
    ├── html/                     # 专属交互式 HTML 生成器
    │   ├── paper_css.py          # 打印排版 CSS 样式
    │   ├── minutes.py            # 纪要 HTML 渲染
    │   ├── actions.py            # 待办卡片 HTML 渲染
    │   ├── risks.py              # 风险看板 HTML 渲染
    │   ├── agenda_minutes.py     # 议程纪要专属渲染
    │   ├── consensus_decision.py # 共识决策交互页面
    │   ├── trace_review.py       # 溯源核对对照页面
    │   └── knowledge_graph.py    # 交互式图谱面板
    ├── charts/                   # 可视化图表
    │   ├── mindmap.py            # Markmap HTML 交互生成 + Playwright 截图
    │   └── graphviz.py           # Graphviz SVG 拓扑图生成
    └── markdown/                 # Markdown 规范化与收尾排版压缩
```

#### 详细文件迁移映射
* 原 `tools/llm/*` -> 迁入 `infra/llm/`
* 原 `tools/ocr/*` -> 迁入 `infra/ocr/`
* 原 `tools/knowledge/vector_store.py` -> 迁入 `infra/storage/vector_store.py`
* 原 `app/job_store.py` -> 迁入 `infra/storage/redis_store.py`
* 原 `tools/memory/*` -> 迁入 `infra/memory/`
* 原 `tools/monitor/*` -> 迁入 `infra/telemetry/monitor.py`
* 原 `tools/core/logging_config.py` -> 迁入 `infra/telemetry/logging.py`
* 原 `tools/exports/outputs.py` -> 迁入 `infra/exporters/`
* 原 `tools/exports/html/*` -> 迁入 `infra/exporters/html/`
* 原 `domain/meeting/memory/render.py` 中的 HTML 渲染代码 -> 拆分并入 `infra/exporters/html/`

---

### 5. `resources/`（业务静态资产与模板库）

#### 目标结构
```text
resources/
├── templates/                    # 原根目录 template/*.md（31 类场景 Markdown 模板）
│   ├── project_progress.md
│   ├── general_minutes.md
│   ├── admission_briefing.md
│   ├── ... (共 31 个场景模板)
│   └── README.md                 # 模板编写公约
├── profiles/                     # 原 assets/profiles/*.json（角色画像模板）
│   ├── objective.json            # 客观全员
│   ├── developer.json            # 研发视角
│   ├── executive.json            # 管理层视角
│   └── ...
└── role_mapping.json             # 角色映射配置文件
```

#### 详细文件迁移映射
* 原根目录 `template/*.md` -> 全部迁入 `resources/templates/`
* 原 `assets/profiles/*.json` -> 全部迁入 `resources/profiles/`
* 原 `assets/role_mapping.json` -> 迁入 `resources/role_mapping.json`

---

### 6. `data/`（多租户数据持久化根目录）

#### 目标结构与隔离规范
```text
data/
├── .gitignore                    # 忽略所有用户数据，只保留规范说明文件
├── README.md                     # 数据目录安全与挂载规范
│
├── {user_id}/                    # 严格按用户 ID 划分物理领地
│   ├── docs/                     # 用户输入的原始文本、音频转录、待 OCR 原始图片
│   ├── output/{request_id}/      # 每次调用的专属结果（result.md, minutes.html, mindmap.png）
│   ├── knowledge/
│   │   ├── chromadb/             # 用户专属的 ChromaDB 向量库物理持久化目录
│   │   ├── catalogs/             # 用户知识目录 JSON
│   │   └── ocr_archives/         # OCR 合并稿归档
│   ├── memory/                   # 跨会话长期演变记忆
│   │   ├── meeting/              # 会议场次状态机 sessions.json 与事实记录
│   │   └── notes/                # 个人知识图谱增量更新数据
│   └── profile/                  # 用户的个性化档案（user.json）
│
└── monitor/                      # 系统级脱敏运行指标（耗时、token 消耗日志）
```

---

### 7. `tests/`（自动化测试与质量中心）

#### 目标结构
```text
tests/
├── unit/                         # 零 LLM 单测（毫秒级运行，不花钱）
│   ├── test_core_profiles.py     # 画像选档与清洗断言（原 test_core.py）
│   ├── test_template_router.py   # 模板判型、门禁与占位断言
│   ├── test_perspective.py       # 视角偏好、人称代词、雷达图计算
│   ├── test_meeting_memory.py    # 跨场次状态机断言
│   └── test_agenda_coercion.py   # 议程类型强制转换断言
├── integration/                  # 流程集成测试与冒烟测试
│   ├── test_engine_smoke.py      # 引擎驱动、DAG 调度、事件流冒烟测试
│   └── test_agenda_minutes.py    # 议程纪要端到端测试（依赖 pytest + fixture）
├── fixtures/                     # 【重要】统一收拢测试资产
│   ├── sample_transcripts/       # 测试用音频文本夹具
│   ├── sample_images/            # 仅保留精简的代表性测试图片（清理原 api_test 中的冗余图）
│   └── sample_agendas/           # 测试议程材料
└── conftest.py                   # Pytest 全局夹具与环境初始化
```

#### 详细文件清理映射
* 原 `tests/test_*.py` -> 按单元与集成分类归入 `tests/unit/` 与 `tests/integration/`
* 原 `api_test/` 彻底清理废弃：
  * 有效的调用样例迁移为 `tests/integration/` 用例；
  * `api_test/sync/notes/library/U202314751/` 中的 21 张测试大图，筛选 2~3 张保留至 `tests/fixtures/sample_images/`，其余删除；
  * 过程中产生的临时 HTML 与 JSON 产物彻底删除。

---

## 三、四大关键重构专项设计

### 专项 A：消除 `app/tasks.py` 上帝文件，下沉领域特判

#### 1. 痛点
原 `app/tasks.py` 近 1000 行，内部包含了 `_ocr_single_agenda_doc`、`_catalog_quality_monitor`、`_fake_heading_chunk_count` 等大量特定业务线特判。

#### 2. 解耦方案
定义统一的 `DomainHooks.prepare_input` 与 `DomainHooks.post_process` 接口规范：
```python
# domains/shared/base.py
class DomainHooks(Protocol):
    async def prepare_task_input(
        self,
        task: str,
        user_id: str,
        req: TaskRequest,
        storage: StoragePathResolver,
    ) -> PreparedTaskInput:
        """各领域负责自己专属的文件解析与预处理（如 agenda 的专用 OCR、catalog 的骨架提取）"""
        ...

    def enrich_response_data(
        self,
        task: str,
        result: EngineResult,
    ) -> ResponseData:
        """各领域负责自己特有响应摘要的构造（如 checklist 摘要卡片）"""
        ...
```
* **效果**：`app/api/routes/agent.py` 只负责分发给对应的 `domain_handler`，`app/` 层不再出现任何 `if task == "agenda_minutes"` 代码！

---

### 专项 B：重构 Worker 异步执行链路，切断对 HTTP 传输层的反向依赖

#### 1. 痛点
原 [app/executor.py](file:///D:/study/demo/app/executor.py#L129-L148) 中，后台 Worker 居然调用了返回 FastAPI `StreamingResponse` 的函数，然后读字节流再 JSON decode：
```python
# 现状中的反模式
response = await stream_task(...)
async for raw in response.body_iterator:
    event = json.loads(raw.decode("utf-8"))
```

#### 2. 解耦方案
`core/runner/` 产出纯 Python 强类型事件流：
```python
# core/runner/events.py
@dataclass
class TaskEvent:
    type: Literal["phase", "chunk", "done", "error"]
    payload: dict[str, Any]

async def run_task_stream(ctx: DomainContext, ...) -> AsyncIterator[TaskEvent]:
    """核心引擎只产出纯领域事件，完全不知道 HTTP 的存在"""
    ...
```
* **Web API 层消费**：
  ```python
  # app/api/routes/agent.py
  async def stream_endpoint(...):
      async def event_generator():
          async for event in run_task_stream(...):
              yield json.dumps(asdict(event), ensure_ascii=False) + "\n"
      return StreamingResponse(event_generator(), media_type="application/x-ndjson")
  ```
* **Worker 队列消费**：
  ```python
  # app/worker/executor.py
  async def execute_job(job_id: str, ...):
      async for event in run_task_stream(...):
          if event.type == "chunk":
              redis_store.append_event(job_id, event)
          elif event.type == "done":
              redis_store.mark_succeeded(job_id, event)
  ```
* **效果**：Worker 直接消费事件流对象写入 Redis，运行速度更快，内存零二次序列化损耗，架构完全解耦。

---

### 专项 C：渲染器 Exporters 统一归位，彻底分离 memory 与 render

#### 1. 痛点
原 [domain/meeting/memory/render.py](file:///D:/study/demo/domain/meeting/memory/render.py) 膨胀至 2162 行，挂羊头卖狗肉地塞入了 `render_minutes_html`、`render_actions_html`、`render_risks_html` 等全套 HTML 页面生成代码；同时部分渲染器又散落在 `tools/exports/` 和 `minutes_trace/` 中。

#### 2. 解耦方案
* `domains/meeting/memory/` 仅保留核心记忆算法：实体抽取、跨场次状态机、向量索引注入与回写。
* 将所有页面生成逻辑全面迁入 `infra/exporters/html/`：
  * `infra/exporters/html/minutes.py`
  * `infra/exporters/html/actions.py`
  * `infra/exporters/html/risks.py`
  * `infra/exporters/html/trace_review.py`
* 领域内的 `hooks.py` 仅作为路由挂载声明：
  ```python
  # domains/meeting/hooks.py
  def html_for(line_name: str, title: str, text: str, data: dict) -> str | None:
      from infra.exporters.html import minutes, actions, risks
      ...
  ```

---

### 专项 D：严格落地基于 user_id 的数据物理沙箱

#### 1. 痛点
当前存在找不到用户文件时回退到 `data/docs/` 公共目录的逻辑，且各处存在硬编码拼路径。

#### 2. 解耦方案
引入强约束的 `StoragePathResolver`：
```python
# infra/storage/path_resolver.py
class StoragePathResolver:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def user_docs(self, user_id: str) -> Path:
        if not user_id or "/" in user_id or "\\" in user_id:
            raise ValueError(f"Invalid user_id: {user_id!r}")
        p = self.root / user_id / "docs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def user_output(self, user_id: str, request_id: str) -> Path:
        p = self.root / user_id / "output" / request_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def resolve_input_file(self, user_id: str, filename: str) -> Path:
        docs_dir = self.user_docs(user_id)
        target = (docs_dir / filename).resolve()
        if not target.is_file() or docs_dir not in target.parents:
            raise FileNotFoundError(f"用户文件不存在: {filename}")
        return target
```
* **效果**：杜绝跨目录穿透攻击，杜绝向公共无主目录回退，真正保证多租户物理安全。

---

## 四、五阶段平滑迁移实施路线图

为了保障业务不中断，建议采取“只增不毁、逐步分流、最后清理”的渐进式迁移策略：

```text
阶段 1：底层与静态资产规整（零风险）
  ├── 1. 创建 resources/，将 template/*.md 与 assets/ 迁入
  ├── 2. 创建 infra/，收拢 llm/、ocr/、telemetry/ 与 exporters/
  └── 3. 建立 infra/storage/path_resolver.py 路径解析器

阶段 2：内核与领域解耦（消除孤儿模块）
  ├── 1. 建立 core/，迁入 domain_engine、runner、contracts
  ├── 2. 建立 domains/shared/，迁入 perspective/ 与 global supervisor
  └── 3. 整理 domains/meeting 与 domains/notes，剥离 memory/render.py

阶段 3：Worker 与执行流解耦（关键链路改造）
  ├── 1. 在 core/runner 中实现 TaskEvent 纯事件流生成器
  ├── 2. 改造 app/worker/executor.py 直接消费 TaskEvent，干掉 HTTP 字节解析
  └── 3. app/api/routes 接入事件流并封装为 FastAPI StreamingResponse

阶段 4：瘦身 app/，消除上帝模块
  ├── 1. 定义 DomainHooks 规范
  ├── 2. 将 agenda OCR、catalog 骨架检查下沉至各自 domain 的 hooks
  └── 3. 废除 app/tasks.py，重构为轻量的请求分发器

阶段 5：测试重构与冗余清理
  ├── 1. 整理 tests/unit 与 tests/integration
  ├── 2. 抽取 api_test 样例至 tests/fixtures/，彻底删除 api_test 目录
  └── 3. 规范 data/ 目录的 .gitignore，验证全仓自动化测试通过
```

---
*注：本文件由系统设计分析后自动生成，作为后续分支重构与代码迁移的唯一权威指导文档。*
