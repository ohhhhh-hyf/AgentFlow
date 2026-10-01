# AgentFlow · 生产就绪的多 Agent 协同编排引擎与后端服务

AgentFlow 是一套专为复杂垂直领域（智能会议分析、知识工程、学习辅助、结构化研报等）打造的**高可靠、低耦合、多任务线并行协同的多 Agent 编排框架与后端交付系统**。

系统采用严格的 **Clean Architecture（整洁架构）** 与 **DDD（领域驱动设计）** 规范，将全局源码与静态资产精炼收敛为 **7 大核心顶层目录**。通过强类型数据流、无依赖的领域事件协议、严密的多租户物理隔离与确定性防幻觉执行门禁，保障系统在企业级生产环境中的确定性与高扩展性。

---

## 目录索引
1. [系统总体架构与 7 大核心目录](#一系统总体架构与-7-大核心目录)
2. [核心技术特性与设计优势](#二核心技术特性与设计优势)
3. [快速开始与环境搭建](#三快速开始与环境搭建)
4. [统一 API 接入与异步 Worker 架构](#四统一-api-接入与异步-worker-架构)
5. [支持的垂直业务领域与任务线](#五支持的垂直业务领域与任务线)
6. [多租户数据物理沙箱隔离规范](#六多租户数据物理沙箱隔离规范)
7. [质量保障与全套自动化测试](#七质量保障与全套自动化测试)
8. [领域与任务线标准扩展指南](#八领域与任务线标准扩展指南)

---

## 一、系统总体架构与 7 大核心目录

AgentFlow 遵循严格的分层单向依赖原则（`app/` -> `domains/` -> `core/` <- `infra/`），根目录下仅保留具备清晰边界的 7 大核心目录：

```text
AgentFlow/
├── app/                          # 【应用交付层】FastAPI 网关与异步队列调度子系统
│   ├── api/                      # Web API 接入层（路由、中间件、依赖注入、健康探针）
│   ├── worker/                   # 独立异步 Worker 消费者（Redis 队列消费、分布式租约、心跳续期）
│   ├── config.py                 # 应用级配置与环境解析
│   ├── schemas.py                # 强类型请求与响应 Pydantic DTO
│   ├── tasklines.py              # 任务线与领域白名单唯一声明表
│   └── tasks.py                  # 任务请求装配分发器
│
├── core/                         # 【核心编排内核】多 Agent 协同调度与规则门禁
│   ├── graph/                    # LangGraph DAG 拓扑图构建、状态合并（State）与通用节点抽象
│   ├── runner/                   # 任务执行驱动器、纯领域事件流协议（TaskEvent）与上下文
│   ├── schema/                   # 结构化模型输出契约 DSL、校验与确定性降级规则
│   ├── execution/                # 硬执行门禁（上游对齐、表行截断、超长段落重写与防幻觉拦截）
│   ├── templates/                # 动态模板引擎（自动判型、占位符填充、篇幅预算与门禁）
│   ├── registry/                 # 领域与任务线动态注册表
│   └── runtime/                  # 运行时状态、进度与渲染上下文支持
│
├── domains/                      # 【垂直业务领域】高内聚、自包含的业务 Agent 集群
│   ├── meeting/                  # 会议领域（事实提取、议程纪要、待办抽取、共识决策、风险、溯源）
│   ├── notes/                    # 笔记与知识领域（知识图谱、智能题库、资料整理、目录编排、复习清单）
│   └── shared/                   # 跨领域共享业务组件
│       ├── perspective/          # 跨域通用视角建模（真人档案适配、第一人称代词转换、动作归属）
│       ├── supervisor/           # 全局监督标准与通用 Prompt 注入
│       └── base.py               # 领域上下文与生命周期钩子（DomainHooks）协议
│
├── infra/                        # 【基础设施适配层】外设适配与技术底层实现
│   ├── llm/                      # 统一 LLM 客户端抽象（适配 HTTP、WebSocket 与本地 vLLM）
│   ├── ocr/                      # OCR 引擎抽象驱动（PaddleOCR、RapidOCR、ServerOCR）与版面去噪纠错
│   ├── storage/                  # 物理持久化基座（多租户路径解析器、Redis 状态存储、ChromaDB 向量库）
│   ├── memory/                   # 长期记忆与向量索引基础设施
│   ├── telemetry/                # 统一结构化可观测性日志与 Token / 性能监控
│   └── exporters/                # 统一产物导出器（专业打印 CSS HTML、Markmap 导图、SVG 拓扑）
│
├── resources/                    # 【业务只读资产库】静态模板与标准化画像
│   ├── templates/                # 31+ 垂直场景 Markdown 模板（会议、访谈、法庭、医疗、教学等）
│   ├── profiles/                 # 客观全员与各行业职业角色画像模板（JSON）
│   └── role_mapping.json         # 角色与职业画像别名映射表
│
├── data/                         # 【多租户数据持久化根】严格按 {user_id} 物理隔离的沙箱
│   └── {user_id}/                # 租户独立命名空间（docs 原始素材、output 产物、knowledge 索引）
│
└── tests/                        # 【自动化测试中心】零 LLM 单元测试与集成测试套件
    ├── test_core.py              # 画像选档、角色合并与基础不变量测试
    ├── test_engine_smoke.py      # DAG 拓扑图与纯事件流调度冒烟测试
    ├── test_template_router.py   # 模板判型、占位填充与验收硬门禁断言
    ├── test_meeting_memory.py    # 跨场次长期记忆状态机与事实溯源断言
    ├── test_perspective.py       # 视角偏好、人称代词转换与雷达图计算断言
    ├── test_draft_scrape.py      # 草稿与上下文抽取标记一致性测试
    ├── test_agenda_coercion.py   # 议程类型强制转换与判定阈值守卫
    └── test_agenda_minutes.py    # 议程端到端全链路行为集成测试
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
- **执行硬门禁**：上游事实硬对齐检查、单栏篇幅预算自适应重写、同名标签防粘连修复、空栏目自动识别，最大程度抑制大模型幻觉与乱序。

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
AGENTFLOW_JOB_TTL_SECONDS=604800

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

系统向外统一暴露两组标准化 API 接入路径：

### 1. 统一实时作业接口 (`/api/agent/v1`)
所有垂直领域和具体任务线均通过统一的入口交互，由请求体中的 `domain` 和 `task` 进行动态分发：

* **同步执行**：`POST /api/agent/v1`（阻塞等待直至全部流程完成，返回最终结构化结果）；
* **流式执行**：`POST /api/agent/v1/stream`（基于 `application/x-ndjson` 实时返回阶段切换与文本输出）；
* **产物下载**：`GET /api/agent/v1/file/{request_id}/{file_name}`（直接获取本次作业生成的 HTML、Markdown 或图片产物）。

#### 同步调用示例
```bash
curl -X POST http://127.0.0.1:8000/api/agent/v1 \
  -H "Content-Type: application/json" \
  -H "X-User-Id: tenant_001" \
  -d '{
    "domain": "meeting",
    "task": "minutes",
    "texts": {
      "transcript": "张三：本次会议讨论下一阶段技术架构演进方案。李四：建议采用事件驱动与多租户物理沙箱隔离……"
    },
    "extra": {
      "template": "general_minutes",
      "profile": "objective"
    }
  }'
```

### 2. 生产异步任务接口 (`/api/v1/tasks`)
专为长耗时作业（如包含多张高精度图片 OCR、多级大模型推理研判）设计的标准异步控制面：

| 方法与路径 | 说明 |
|---|---|
| `POST /api/v1/tasks` | 提交异步作业，立即返回 `job_id` 与 `request_id` |
| `GET /api/v1/tasks/{job_id}` | 轮询查询当前作业状态、阶段、耗时与结果摘要 |
| `GET /api/v1/tasks/{job_id}/stream?cursor=0` | 支持断点续传的事件流追溯接口（支持断网重连） |
| `GET /api/v1/tasks/{job_id}/result` | 作业完成后获取全量结构化产物报表 |

---

## 五、支持的垂直业务领域与任务线

系统目前原生内置两个重量级垂直领域模型，具备清晰的扩展规范：

### 1. 会议领域（Meeting Domain - `domains/meeting/`）
涵盖商务研讨、项目推进与技术评审等全流程场景：
- **`minutes`（会议纪要）**：基于事实提纯的高保真多板块纪要，自动按议程归纳要点与决议；
- **`actions`（待办提取）**：四要素结构化提取（事项、责任人、截止时间、验收标准）；
- **`risks`（风险识别）**：深度研判潜在阻碍、依赖项与红线问题，评定风险等级与规避对策；
- **`agenda_minutes`（议程纪要）**：议程单图片 OCR 智能锚定与时序对齐，锁定讨论进度与决策结论；
- **`consensus_decision`（共识决策）**：针对争议性议题梳理共识演进过程与最终拍板决议；
- **`minutes_styles`（多样式纪要）**：支持公文风、精炼简报风、详细速记风等多模态渲染；
- **`minutes_trace`（溯源纪要）**：每项决策和待办均打上会议原始对话依据的时间戳与发言人锚点；
- **`mindmap`（思维导图）**：自动梳理全局拓扑，生成可交互的 Markmap HTML 及高清 PNG 图片。

### 2. 笔记与知识领域（Notes Domain - `domains/notes/`）
面向知识库工程、学习分析与文档资产化：
- **`catalog`（知识目录编排）**：基于原文 Markdown 骨架树逐级提纯章、主题与知识点；
- **`checklist`（复习清单卡片）**：动态预算驱动的分批并行精细化知识点解析；
- **`graph`（知识图谱构建）**：实体与关系抽取，生成基于 Cytoscape.js 的交互式学习地图；
- **`library`（资料智能入库）**：支持 PPT、PDF、Word 文档与笔记图片的版面分析、公式纠错与向量化存储；
- **`quiz`（自测题目生成）**：结合领域题库与教学大纲生成匹配测试题；
- **`review`（笔记审校与评注）**：对原始笔记进行学术性纠错与概念补全。

### 3. 通用视角建模（Perspective Modeling - `domains/shared/perspective/`）
支持两种核心视角的无缝切换：
- **客观视角（Objective）**：站在绝对中立第三方角度梳理事实脉络；
- **个人视角（Personal）**：基于 `data/{user_id}/user.json` 中的画像配置，智能识别发言人命中，自动完成人称代词置换（“我/你”），将结论与行动项按「与我相关」分块归集。

---

## 六、多租户数据物理沙箱隔离规范

所有用户数据均强制物理落地在 `data/{user_id}/` 下，结构完全自闭环：

```text
data/
└── {user_id}/                    # 严格按用户唯一 ID 物理隔离
    ├── docs/                     # 用户上传的待处理素材（文档、图片、音频文字稿）
    ├── output/{request_id}/      # 每次调用的隔离生成产物
    │   ├── result.md             # 最终生成的标准化 Markdown 文本
    │   ├── {task}.html           # 针对各任务线定制的专属交互式单文件 HTML
    │   └── {task}.png            # 渲染图表（如有）
    ├── knowledge/
    │   ├── chromadb/             # 该租户专享的向量检索库文件
    │   └── catalogs/             # 租户生成的学科/领域知识目录 JSON
    ├── memory/                   # 跨会话长期沉淀记忆（会议场次状态机、图谱增量更新）
    └── profile/
        └── user.json             # 租户专属个性化画像档案（偏好、职责、习惯）
```

---

## 七、质量保障与全套自动化测试

AgentFlow 内置了严密的**零 LLM 确定性回归测试套件**，能在毫秒级到秒级内快速完成核心业务逻辑、契约不变量与语法规则的验证，无需消耗外部模型 Token：

```bash
# 运行全套自动化测试套件
python -m pytest tests/

# 单独运行各专项测试套件
python -m tests.test_core               # 画像选档、角色合并与基础不变量测试
python -m tests.test_engine_smoke       # DAG 拓扑调度与纯事件流流转测试
python -m tests.test_agenda_coercion    # 议程类型强制转换与判定阈值守卫
python -m tests.test_meeting_memory     # 跨场次长期记忆状态机与事实溯源测试
python -m tests.test_perspective        # 视角偏好、代词替换与雷达图计算测试
python -m tests.test_draft_scrape       # 草稿与上下文抽取标记一致性测试
python -m pytest tests/test_template_router.py  # 模板判型、占位填充与验收门禁断言
```

---

## 八、领域与任务线标准扩展指南

系统遵循开放封闭原则（Open-Closed Principle），扩展全新的垂直领域或在现有领域下新增任务线，零侵入核心编排引擎：

1. **定义契约**：在 `domains/<domain>/tasks/<task>/contracts.py` 中声明 Pydantic 输出模型契约与字段规则；
2. **定义 Prompt**：在 `domains/<domain>/tasks/<task>/prompts.py` 中编写包含明确结构化规范的 Prompt 模板；
3. **编排步骤**：在 `domains/<domain>/tasks/<task>/steps/` 中实现对应 Agent 的生成节点与审核节点；
4. **挂载生命周期**：在 `domains/<domain>/hooks.py` 中声明专有渲染逻辑（`html_for`）或预处理逻辑（`prepare_task_input`）；
5. **注册任务白名单**：在 `app/tasklines.py` 的白名单配置中登记新任务线。系统将自动为其挂载 HTTP 接入端点与监控报表。

---

## 许可证
本项目采用 MIT 许可证开源。详见 LICENSE 文件。
