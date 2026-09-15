# AgentFlow HTTP API

纯后端服务，唯一入口为 FastAPI（`uvicorn app.main:app`，默认 `http://127.0.0.1:8000`）。
自动文档：`GET /docs`（Swagger UI）、`GET /openapi.json`。

当前开放 **10 组任务接口**，分布在两个域；每组接口同时提供 **POST 同步**、**POST 流式（NDJSON）** 与 **GET 产物获取**：

| 域 | 任务（URL 中的 task） | 中文 |
|---|---|---|
| meeting（会议） | `minutes` / `actions` / `risks` / `minutes_styles` / `minutes_trace` / `consensus_decision` | 会议纪要 / 待办行动 / 风险分析 / 多样式纪要 / 溯源纪要 / 共识决策 |
| notes（笔记） | `graph` / `library` / `catalog` / `checklist` | 知识图谱 / 资料入库 / 知识目录 / 复习清单 |

> 说明：`consensus_decision` 额外注册了 `consensus`、`decision` 两个同义 URL（仅同步接口）；领域内存在但**未开放 HTTP 接口**的任务线（如 quiz / review / mindmap）不在此文档范围内。

此外新增一组生产主路径异步任务接口：

| 接口 | 用途 |
|---|---|
| `POST /api/v1/tasks` | 提交任务，立即返回 `job_id` 与 `request_id` |
| `GET /api/v1/tasks/{job_id}` | 查询任务状态、阶段、耗时、token、错误 |
| `GET /api/v1/tasks/{job_id}/result` | 获取完成后的最终结果 |
| `GET /api/v1/tasks/{job_id}/stream` | 订阅任务事件流（NDJSON，可断线重连） |

---

## 1. 通用约定

### 1.1 请求头

| 头 | 必填 | 适用 | 说明 |
|---|---|---|---|
| `X-Request-Id` | POST 可选 | 同步 / 流式 | 调用方追踪 ID。缺省时服务端自动生成 `request_` + 分布式数字 ID。产物目录以最终 request_id 为名：`data/{user_id}/output/{request_id}/`；GET 产物、结果核对都靠它定位。 |
| `X-User-Id` | POST 必填 | 同步 / 流式 / GET 下载 | 用户标识。知识库、知识目录、记忆、产物全部按用户隔离在 `data/{user_id}/` 下。GET 下载/预览也可改用 URL 参数 `?user_id=`（浏览器直接访问时无法带请求头） |
| `Content-Type` | POST 必填 | 同步 / 流式 | `application/json` |

### 1.2 通用请求体（TaskRequest）

`domain/task` 由 URL 表达，请求体对全部任务同构：

```jsonc
{
  "time": "",                       // 任务时间（会议开始/转录完成时刻）；可为空
  "texts": {                        // 三类固定 key 的文本（多段用 \n 拼接）
    "transcript": "",               //   正文：会议转写 / 笔记原文 / 老师重点全文
    "keypoints": "",                //   用户重点（部分任务线的必填溯源材料）
    "notes": ""                     //   用户笔记（部分任务线的必填溯源材料）
  },
  "docs": [],                       // 文件名列表（须已存在于服务端 data/{user_id}/docs/ 或 catalog 目录）
  "extra": {
    "template": "",                 // 输出模板（可空=默认无模板，格式见 README「自定义输出模板」）
    "profile": "",                  // 用户画像/职业模板名（可空=客观全员视角）
    "project": "",                  // 项目绑定（会议记忆按项目聚合时使用；可空）
    "subject": "",                  // 学科（notes 域知识相关任务必填；中文自动转拼音，如 物理→wuli）
    "style": "",                    // 仅 minutes_styles 使用（见该任务）
    "memory": false                 // 是否写入跨会话记忆（notes 图谱/目录与会议记忆相关任务生效）
  }
}
```

字段说明：

- `texts` 只接受 `transcript / keypoints / notes` 三个 key，出现其它 key 返回 422。
- `docs` 的取用位置与角色由任务决定：
  - 常规任务：`data/{user_id}/docs/` 下的文档/图片文件名；
  - `catalog` / `checklist`：`.txt` 被读取为**老师重点文本**（位于 `data/{user_id}/docs/`）；
  - `checklist`：`.json` 为该学科**知识目录文件**——文件名取 catalog 响应 `data.file_name`，服务端在 `data/{user_id}/knowledge/catalogs/{学科拼音}/` 下定位。
- `template` / `profile` 为空字符串表示"不套模板 / 客观视角"。

各任务线的必填项（缺必填字段时秒回 400，不触发模型调用）：

| 任务 | 必填 |
|---|---|
| minutes / actions / risks / consensus_decision | `X-User-Id`、`texts.transcript` |
| minutes_styles | `X-User-Id`、`texts.transcript`、`extra.style` |
| minutes_trace | `X-User-Id`、`texts.transcript`、`texts.keypoints`、`texts.notes` |
| graph | `X-User-Id`、`docs`（笔记文件） |
| library | `X-User-Id`、`extra.subject`、`docs` |
| catalog | `X-User-Id`、`extra.subject` |
| checklist | `X-User-Id`、`extra.subject`、`docs`（catalog 文件名） |

### 1.3 通用响应（TaskResponse）

```jsonc
{
  "code": 0,                        // 业务码：0=成功；非 0 时与 HTTP 状态一致
  "request_id": "3f9a…",            // 回显调用方传入的追踪 ID
  "message": "success",
  "monitor": {                      // 任务监控（错误响应中不出现）
    "token_usage": 29553,           //   本次任务消耗总 token
    "cache_hit": 10496,             //   缓存命中 token
    "cost_time": 31.6               //   耗时（秒）
  },
  "data": {                         // 任务产物（错误响应中不出现）
    "text": "# …（Markdown 正文）",
    "file_name": "minutes.html"     // 本次产物的文件名，用于 GET 下载定位
  }
}
```

| 字段 | 说明 |
|---|---|
| `code` | 0 表示成功；失败时等于 HTTP 状态码（400/404/500 等） |
| `request_id` | 与请求头一致；**保存它**用于后续 GET 产物 |
| `message` | `success` 或错误原因 |
| `monitor.token_usage / cache_hit / cost_time` | 本次任务模型消耗与耗时 |
| `data.text` | Markdown 产物正文（大任务正文可能很长，按需截断展示） |
| `data.file_name` | 产物文件名。规则：catalog 返回知识目录 json 名；有页面版返回 `{task}.html`；仅文本产物返回 `result.md` 或 `{task}.md`；无落盘产物（library）为空串 |

**产物落盘**（仅 `data.file_name` 非空的任务）：`data/{user_id}/output/{request_id}/` 目录下，
`{task}.html`（页面版，样式自包含单文件）+ `result.md` / `{task}.md`（Markdown）；
graph 额外有交互式 `graph.html`；catalog 的 json 在 `data/{user_id}/knowledge/catalogs/{学科拼音}/`。

### 1.4 错误约定

| HTTP | 场景 | 响应体 |
|---|---|---|
| 400 | 缺少必填请求头/必填字段/字段取值非法 | `{"code": 400, "request_id": "…", "message": "缺少…"}` |
| 404 | 任务不存在 / GET 产物文件不存在 | 同上结构 |
| 422 | 请求体不符合模型（如 texts 未知 key、类型错误） | Pydantic 默认校验错误体 |
| 500 | 任务运行失败 / 未捕获异常 | `{"code": 500, "request_id": "…", "message": "任务运行失败：…"}` |
| 503 | 异步任务接口 Redis 不可用 | `{"detail": "Redis 不可用（<REDIS_URL>）：…"}` |

错误响应一律**不含** `monitor` 与 `data` 字段（避免全 0/空字段噪音）。

> 上表适用于同步 / 流式接口。异步任务接口（`/api/v1/tasks*`）由框架 `HTTPException` 抛错，
> 响应体统一为 `{"detail": "…"}`（如 404 `任务不存在：<job_id>`、409 `任务尚未完成：<status>`、
> 503 Redis 不可用、400 `缺少 X-User-Id`），不套用 TaskResponse。

### 1.5 GET 产物获取三形态

产物文件保存在服务端，获取方式取决于使用场景（详见第 2 节）：

| 用途 | 端点 | 响应 |
|---|---|---|
| 下载（附件） | `/api/v1/{domain}/{task}/file?request_id=…&user_id=…`（文件名自动回退 html→md） | `Content-Disposition: attachment` |
| 下载（指定文件名） | `/api/v1/{domain}/{task}/file/{request_id}/{file_name}` | 同上 |
| 浏览器预览 | `/api/v1/{domain}/{task}/preview?request_id=…&user_id=…` | `text/html` inline，直接渲染 |
| 任意静态文件 | `/data/{user_id}/output/{request_id}/{file_name}` | 按扩展名返回（同源） |

> 支持文件端点的任务线：meeting 域全部六条；notes 域 `graph` 与 `checklist`（两条线均有页面版产物）。

---

## 2. GET 接口

### 2.1 健康检查 `GET /api/v1/health`

无需请求头。返回服务状态与两个域当前可用的任务线清单（加载失败时降级报告，不影响其它接口）：

```jsonc
{
  "status": "ok",                                // 或 "degraded"
  "task_lines": {
    "meeting": ["actions", "consensus_decision", "mindmap", "minutes", "minutes_styles", "minutes_trace", "risks"],
    "notes":   ["catalog", "checklist", "graph", "library", "quiz", "review"]
  }
  // status=degraded 时追加: "degraded": ["notes: <异常信息>"]
}
```

### 2.2 产物下载 / 预览端点

**meeting 域六条任务线**（`minutes / actions / risks / minutes_styles / minutes_trace / consensus_decision`）与 **notes 域 `graph`、`checklist`** 均注册了同一套文件端点：

```
GET /api/v1/{domain}/{task}/file/{request_id}/{file_name}     # 指定文件名下载（file_name 取响应 data.file_name）
GET /api/v1/{domain}/{task}/file?request_id=…&user_id=…       # 便捷下载：文件名免填，自动按 {task}.html → {task}.md → result.md 回退
GET /api/v1/{domain}/{task}/preview?request_id=…&user_id=…    # 受控预览：只允许取产物目录内 {task}.html，text/html inline 渲染
```

- `user_id` 也可通过 `X-User-Id` 请求头提供（二者取一，都没有返回 400）。
- 下载端点返回 `Content-Disposition: attachment`（浏览器弹保存）；预览端点无该头（浏览器直接渲染页面）。
- 产物不存在返回 404（提示缺哪个文件）。
- notes 域仅 `graph`、`checklist` 注册（library 无落盘产物；catalog 的文件名指向知识目录 json，不在 output 目录，不提供下载）。

### 2.3 静态资源 `GET /data/…`

服务把项目根 `data/` 目录挂为静态资源：`/data/{user_id}/output/{request_id}/{task}.html` 等均可直接访问（浏览器渲染页面版产物）。`/docs`（Swagger）、`/openapi.json` 为框架自带。

---

## 3. POST 同步接口

请求头：`X-User-Id` 必填，`X-Request-Id` 可选（见 1.1）。请求体：TaskRequest（见 1.2）。
响应：TaskResponse（见 1.3）。以下按任务逐一列出差异与产物。

### meeting 域

#### 3.1 会议纪要 `POST /api/v1/meeting/minutes`

- 必填：`texts.transcript`（会议转写文本）。
- `extra.memory=true` 时：命中历史会议记忆则正文带"参考历史会议"来源标注并写入会议记忆（按 `extra.project` 聚合）；`extra.time` 非空时写入记忆时间。
- 产物：`minutes.html`（页面版）+ `result.md`。

```jsonc
// 请求
{ "time": "", "texts": { "transcript": "<会议转写文本>", "keypoints": "", "notes": "" },
  "docs": [], "extra": { "template": "", "profile": "", "project": "", "subject": "", "style": "", "memory": false } }
// 响应 data
{ "text": "# 会议纪要标题\n…", "file_name": "minutes.html" }
```

#### 3.2 待办行动 `POST /api/v1/meeting/actions`

- 必填：`texts.transcript`。从会议中提取待办与分工（含负责人、时间要求）。
- 产物：`actions.html` + `actions.md`。

#### 3.3 风险分析 `POST /api/v1/meeting/risks`

- 必填：`texts.transcript`。输出风险条目（描述/严重度/来源/应对/负责人）。
- 产物：`risks.html` + `risks.md`。

#### 3.4 多样式纪要 `POST /api/v1/meeting/minutes_styles`

- 必填：`texts.transcript`、`extra.style`（组织模式，取值：`time` 时间线 / `logic` 逻辑 / `causal` 因果 / `party` 分角色 / `urgency` 优先级）。
- 产物：`minutes_styles.html` + `minutes_styles.md`。

#### 3.5 溯源纪要 `POST /api/v1/meeting/minutes_trace`

- 必填：`texts.transcript`（会议事实）+ `texts.keypoints`（用户重点）+ `texts.notes`（用户笔记）。
- 用户重点/笔记作为溯源材料参与对齐；输出结论、风险、行动均带原文溯源钉。
- 产物：`minutes_trace.html`（左正文 / 右证据审阅栏）+ `minutes_trace.md`。

#### 3.6 共识决策 `POST /api/v1/meeting/consensus_decision`

同义 URL：`/api/v1/meeting/consensus`、`/api/v1/meeting/decision`（仅同步）。

- 必填：`texts.transcript`。输出议题共识结论与因果推导报告。
- 产物：`consensus_decision.html` + `consensus_decision.md`。

### notes 域

#### 3.7 笔记知识图谱 `POST /api/v1/notes/graph`

- 必填：`docs`（`data/{user_id}/docs/` 下的笔记 `.txt/.md` 文件；图片会先 OCR + 审校再解析）。
- `extra.subject` 用于按用户+学科做图谱增量合并；`extra.memory=true` 时跨会话增量（新增节点高亮）。
- 产物：交互式 `graph.html`（Cytoscape.js，自包含单文件）；无 md 落盘（正文在 `data.text`）。

#### 3.8 资料入库 `POST /api/v1/notes/library`

- 必填：`extra.subject`、`docs`（文档/图片全量入库：PPT/PDF/docx/xlsx/txt/图片）。
- 入库后资料进入该用户该学科的知识库（向量索引），供检索与带出处问答。
- **无落盘产物文件**：结果文本与统计只在响应 `data.text` 中返回，`data.file_name` 为空串。

#### 3.9 知识目录 `POST /api/v1/notes/catalog`

- 必填：`extra.subject`（学科，中文自动转拼音）。
- `docs` 中 `.txt` 会作为老师重点读取；无输入文本时按该学科已入库资料生成/增量更新目录。
- 产物：目录数据 json 写入 `data/{user_id}/knowledge/catalogs/{学科拼音}/{时间戳}.json`（`data.file_name` 返回该文件名）；`data.text` 为目录树 Markdown；同时落盘 `result.md`。

#### 3.10 复习清单 `POST /api/v1/notes/checklist`

- 必填：`extra.subject`、`docs`——docs 里**必须包含一个 catalog json 文件名**（catalog 响应 `data.file_name`），可再追加一个老师重点 `.txt`。
- 任务基于指定/最新的知识目录生成复习清单：高优先知识点为完整卡片，低优先为简要条目。
- `data.text` 为**精简摘要**（统计 + 卡片列表，适合接口返回）；完整 Markdown 落盘 `result.md`，页面版 `checklist.html`（推荐用 GET 预览/下载查看全量）。

---

## 4. POST 流式接口

每条任务线对应 `/stream` 端点，请求体与同步接口完全一致、校验规则一致（校验失败仍直接返回 HTTP 错误，不走流）：

```
POST /api/v1/meeting/{task}/stream        # task ∈ minutes / actions / risks / minutes_styles / minutes_trace / consensus_decision
POST /api/v1/notes/{task}/stream          # task ∈ graph / library / catalog / checklist
```

响应为 **NDJSON**（`Content-Type: application/x-ndjson`），每行一个 JSON 事件：

| 事件 | 字段 | 说明 |
|---|---|---|
| `{"type": "phase", "node": str}` | 编排阶段名 | 每进入一个节点推送一次（如 审核/渲染） |
| `{"type": "chunk", "line": str, "title": str, "text": str}` | 渲染文本增量 | `text` 为本次增量，前端按行追加 |
| `{"type": "done", "code": 0, "request_id": str, "message": "success", "quality_warning": str\|null, "monitor": {…}, "data": {…}}` | 最终结果 | 字段与同步响应同构（多一个 `quality_warning` 质量提示） |
| `{"type": "error", "code": 500, "message": str}` | 运行失败 | 流中途异常 |

```bash
curl -N -X POST http://127.0.0.1:8000/api/v1/meeting/minutes/stream \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: $(uuidgen)" -H "X-User-Id: 1" \
  -d '{"time":"","texts":{"transcript":"<会议转写文本>"},"docs":[],"extra":{}}'
# 输出示例（每行一个事件，phase 节点名随任务不同）：
# {"type": "phase", "node": "<编排节点名>"}
# {"type": "chunk", "line": "minutes", "title": "会议纪要", "text": "# …"}
# {"type": "done", "code": 0, "request_id": "…", "quality_warning": null, "monitor": {…}, "data": {…}}
```

---

## 5. 异步任务接口

异步任务接口不替代现有同步接口；它是生产主路径。同步接口仍可用于小文本测试和兼容旧调用。

任务状态与事件流存在 **Redis**：`.env` 的 `REDIS_URL`（缺省 `redis://127.0.0.1:6379/0`）、
`AGENTFLOW_JOB_TTL_SECONDS`（缺省 7 天，状态与事件流共用）。Redis 不可用时本组接口返回 503，
同步 / 流式接口不受影响。运行期日志可只看 `agentflow:job:{job_id}` 与 `agentflow:job:{job_id}:events` 两个 key。

> 与同步接口的区别：本组接口缺必填字段时**不在提交时**返回 400，而是先返回 `queued`，
> 随后任务转为 `failed`（`error` 字段给出缺失项），`GET /result` 返回 409。
> 请求体本身不合模型仍返回 422。

### 5.1 提交任务 `POST /api/v1/tasks`

请求头：`X-User-Id` 必填，`X-Request-Id` 可选。缺省时服务端生成 `request_` + 分布式数字 ID；异步任务自身生成 `job_` + 分布式数字 ID。

请求体在原 TaskRequest 基础上增加 `domain` 与 `task`：

```jsonc
{
  "domain": "meeting",
  "task": "minutes",
  "time": "",
  "texts": {"transcript": "会议转写文本"},
  "docs": [],
  "extra": {"memory": false}
}
```

响应：

```jsonc
{
  "code": 0,
  "message": "queued",
  "job_id": "job_637529814248456194",
  "request_id": "request_637529814248456193",
  "status": "queued"
}
```

### 5.2 查询状态 `GET /api/v1/tasks/{job_id}`

返回 Redis 中的任务状态：

```jsonc
{
  "job_id": "job_...",
  "request_id": "request_...",
  "user_id": "1",
  "domain": "meeting",
  "task": "minutes",
  "status": "running",
  "phase": "meeting_understanding",
  "message": "running:meeting_understanding",
  "cost_time": 12.4,
  "token_usage": 0,
  "cache_hit": 0,
  "error": ""
}
```

`status` 取值：`queued` / `running` / `succeeded` / `failed`。

### 5.3 获取结果 `GET /api/v1/tasks/{job_id}/result`

任务成功后返回与流式接口 `done` 事件一致的最终结果。任务未完成时返回 `409`。

### 5.4 事件流 `GET /api/v1/tasks/{job_id}/stream`

响应为 NDJSON，事件来自任务运行过程：`queued` / `started` / `phase` / `chunk` / `done` / `error`。

支持 `cursor` 参数从指定事件下标开始读取：

```
GET /api/v1/tasks/{job_id}/stream?cursor=0
```

---

## 6. 端到端调用示例（推荐流程）

**步骤 1：入库 → 目录 → 清单（notes 域顺序依赖）**

```bash
# 1) 资料入库（docs 在 data/1/docs/ 下）
curl -X POST http://127.0.0.1:8000/api/v1/notes/library -H "Content-Type: application/json" \
  -H "X-Request-Id: $(uuidgen)" -H "X-User-Id: 1" \
  -d '{"docs":["<文件名.docx>"],"extra":{"subject":"<学科>"}}'
# 2) 生成/更新知识目录 → 响应 data.file_name 为目录 json 文件名
curl -X POST http://127.0.0.1:8000/api/v1/notes/catalog -H "Content-Type: application/json" \
  -H "X-Request-Id: $(uuidgen)" -H "X-User-Id: 1" \
  -d '{"docs":["<老师重点.txt(可选)>"],"extra":{"subject":"<学科>"}}'
# 3) 基于目录生成复习清单（docs 填第 2 步的 file_name）
curl -X POST http://127.0.0.1:8000/api/v1/notes/checklist -H "Content-Type: application/json" \
  -H "X-Request-Id: $(uuidgen)" -H "X-User-Id: 1" \
  -d '{"docs":["<catalog文件名.json>"],"extra":{"subject":"<学科>"}}'
# 4) 获取产物（用响应里的 request_id）
curl -OJ "http://127.0.0.1:8000/api/v1/meeting/minutes/file?request_id=<rid>&user_id=1"   # 下载
# 浏览器打开预览：
#   http://127.0.0.1:8000/api/v1/meeting/minutes/preview?request_id=<rid>&user_id=1
```

**会议域（minutes 带记忆）**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/meeting/minutes -H "Content-Type: application/json" \
  -H "X-Request-Id: $(uuidgen)" -H "X-User-Id: 1" \
  -d '{"time":"2026-09-07","texts":{"transcript":"<会议转写文本>"},"extra":{"memory":true,"project":"<项目名(可选)>"}}'
```

**GET 产物定位速查**

| 已拿到 | 位置/URL |
|---|---|
| `request_id` + `file_name` | `GET /data/{user_id}/output/{request_id}/{file_name}`（静态） |
| 支持文件端点的任务（meeting 六线 + notes graph/checklist） | `/api/v1/{domain}/{task}/preview?request_id=…&user_id=…` 预览；`/file?request_id=…&user_id=…` 下载 |
| catalog 目录数据 | `data/{user_id}/knowledge/catalogs/{学科拼音}/{file_name}`（`file_name` 为 catalog 响应值） |

> 未传 `X-User-Id` 的历史兼容路径 `data/output/{request_id}/` 仍被 `/data` 静态目录覆盖，但新调用请始终携带用户头。
