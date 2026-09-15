# AgentFlow HTTP API

纯后端服务，唯一入口为 FastAPI（`uvicorn app.main:app`，默认 `http://127.0.0.1:8000`）。
自动文档：`GET /docs`（Swagger UI）、`GET /openapi.json`。

本文档分三块：

1. **健康检查**（第 1 节）：服务状态与任务线清单；
2. **任务线接口**（第 2 节，老接口）：URL 带 `domain`/`task`，每条任务线固定四种形态 ——
   普通（同步）、流式、GET 下载、GET 预览；
3. **异步任务接口**（第 3 节，新增）：`/api/v1/tasks` 四件套（提交 / 状态 / 结果 / 事件流），
   与具体任务线解耦。

---

## 0. 接口总览

### 0.1 URL 约定

| 端点形态 | 路径 | 方法 | 说明 |
|---|---|---|---|
| 普通（同步） | `/api/v1/{domain}/{task}` | POST | 请求体 TaskRequest，返回 TaskResponse（2.5.1） |
| 流式 | `/api/v1/{domain}/{task}/stream` | POST | NDJSON 事件流，请求体与普通接口一致（2.5.2） |
| 下载 | `/api/v1/{domain}/{task}/file/{request_id}/{file_name}` | GET | 附件下载，`file_name` 取响应 `data.file_name`（2.5.3） |
| 预览 | `/api/v1/{domain}/{task}/preview?request_id=&user_id=` | GET | 页面版 `{task}.html`，`text/html` 直接渲染（2.5.4） |
| 健康检查 | `/api/v1/health` | GET | 服务状态 + 两个域当前任务线清单（第 1 节） |
| 异步提交 | `/api/v1/tasks` | POST | 立即返回任务快照 `status=queued`（3.3） |
| 异步状态 | `/api/v1/tasks/{job_id}` | GET | 状态 / 阶段 / attempts / token（3.4） |
| 异步结果 | `/api/v1/tasks/{job_id}/result` | GET | 取结果快照，成功时带正文（3.5） |
| 异步事件流 | `/api/v1/tasks/{job_id}/stream?cursor=N` | GET | NDJSON，可断线重连（3.6） |
| 静态产物 | `/data/{user_id}/output/{request_id}/{file_name}` | GET | 同源直接访问（无鉴权） |
| 框架自带 | `/docs`、`/redoc`、`/openapi.json` | GET | Swagger / ReDoc / OpenAPI |

### 0.2 任务线矩阵

10 条任务线**都有普通 POST 与流式 POST**；下载 / 预览按"是否有落盘到 output 目录的产物"注册：

| 域 | task | 中文 | 下载 / 预览 | 产物文件（`data/{user_id}/output/{request_id}/`） |
|---|---|---|---|---|
| meeting | `minutes` | 会议纪要 | ✅ | `minutes.html` + `result.md` |
| meeting | `actions` | 待办行动 | ✅ | `actions.html` + `actions.md` |
| meeting | `risks` | 风险分析 | ✅ | `risks.html` + `risks.md` |
| meeting | `minutes_styles` | 多样式纪要 | ✅ | `minutes_styles.html` + `minutes_styles.md` |
| meeting | `minutes_trace` | 溯源纪要 | ✅ | `minutes_trace.html` + `minutes_trace.md` |
| meeting | `consensus_decision` | 共识决策 | ✅ | `consensus_decision.html` + `consensus_decision.md` |
| notes | `graph` | 知识图谱 | ✅ | `graph.html`（无 md 落盘，正文在 `data.text`） |
| notes | `library` | 资料入库 | ❌ 无落盘产物 | `data.file_name` 为空串 |
| notes | `catalog` | 知识目录 | ❌ 产物不在 output 目录 | 目录 JSON 在 `data/{user_id}/knowledge/catalogs/{学科拼音}/` |
| notes | `checklist` | 复习清单 | ✅ | `checklist.html` + `result.md` |

路由与清单的**唯一声明处**是 `app/tasklines.py`（域 → 任务线 → 是否注册产物端点），
路由注册、普通与异步接口的任务名校验都从它派生。

### 0.3 已下线的端点形态（2026-09 精简）

| 已下线 | 替代方式 |
|---|---|
| `GET /api/v1/{domain}/{task}/file?request_id=&user_id=`（便捷下载，文件名自动回退） | 用 `GET /api/v1/{domain}/{task}/file/{request_id}/{file_name}`，`file_name` 取响应 `data.file_name` |
| `POST /api/v1/meeting/consensus`、`POST /api/v1/meeting/decision`（同义 URL） | 用规范名 `POST /api/v1/meeting/consensus_decision` |

两个域的路由面因此从 46 条收敛到 36 条（每条任务线固定四类端点）。

---

## 1. 健康检查

### `GET /api/v1/health`

无需请求头。返回服务状态与两个域**当前可用**的任务线清单（领域装配失败时降级报告，不影响其它接口）：

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

> `task_lines` 列的是**领域内全部已装配的任务线**，比对外接口多：`mindmap`、`quiz`、`review`
> 等尚未开放 HTTP 接口的任务线只在这里出现（黑名单之外的差异以第 2 节的矩阵为准）。

---

## 2. 任务线接口（`/api/v1/{domain}/{task}`）

老接口，URL 自带 `domain`（`meeting` / `notes`）与 `task`。每条任务线固定四种形态：
普通、流式、下载、预览（后两种仅当该任务线有落盘产物）。

先讲三种形态共用的**请求头 / 请求体 / 响应体 / 错误**，再讲四种形态的协议，最后逐条介绍 10 条任务线。

### 2.1 请求头

| 头 | 必填 | 适用 | 说明 |
|---|---|---|---|
| `X-Request-Id` | POST 可选 | 普通 / 流式 | 调用方追踪 ID。缺省时服务端自动生成 `request_` + 分布式数字 ID。产物目录以最终 request_id 为名：`data/{user_id}/output/{request_id}/`；下载、结果核对都靠它定位。 |
| `X-User-Id` | POST 必填 | 普通 / 流式 / 下载 / 预览 | 用户标识。知识库、知识目录、记忆、产物全部按用户隔离在 `data/{user_id}/` 下。GET 端点也可改用 URL 参数 `?user_id=`（浏览器直接访问时无法带请求头），二者取一，都没有返回 400 |
| `Content-Type` | POST 必填 | 普通 / 流式 | `application/json` |

### 2.2 请求体（TaskRequest）

`domain` / `task` 由 URL 表达，请求体对全部任务线同构：

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
    "style": "",                    // 仅 minutes_styles 使用（见 2.6.4）
    "memory": false                 // 是否写入跨会话记忆（notes 图谱/目录与会议记忆相关任务生效）
  }
}
```

字段说明：

- `texts` 只接受 `transcript / keypoints / notes` 三个 key，出现其它 key 返回 422。
- `docs` 的取用位置与角色由任务决定：
  - 常规任务：`data/{user_id}/docs/` 下的文档/图片文件名；
  - `catalog` / `checklist`：`.txt` 被读取为**老师重点文本**（位于 `data/{user_id}/docs/`）；
  - `checklist`：`.json` 为该学科**知识目录文件**——文件名取 catalog 响应 `data.file_name`，
    服务端在 `data/{user_id}/knowledge/catalogs/{学科拼音}/` 下定位。
- `template` / `profile` 为空字符串表示"不套模板 / 客观视角"。

各任务线的必填项（缺必填字段时**秒回 400，不触发模型调用**）：

| 任务 | 必填 |
|---|---|
| minutes / actions / risks / consensus_decision | `X-User-Id`、`texts.transcript` |
| minutes_styles | `X-User-Id`、`texts.transcript`、`extra.style` |
| minutes_trace | `X-User-Id`、`texts.transcript`、`texts.keypoints`、`texts.notes` |
| graph | `X-User-Id`、`docs`（笔记文件） |
| library | `X-User-Id`、`extra.subject`、`docs` |
| catalog | `X-User-Id`、`extra.subject` |
| checklist | `X-User-Id`、`extra.subject`、`docs`（catalog 文件名） |

### 2.3 响应体（TaskResponse）

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
    "file_name": "minutes.html"     // 本次产物的文件名，用于下载定位
  }
}
```

| 字段 | 说明 |
|---|---|
| `code` | 0 表示成功；失败时等于 HTTP 状态码（400/404/500 等） |
| `request_id` | 与请求头一致；**保存它**用于后续下载 / 预览 |
| `message` | `success` 或错误原因 |
| `monitor.token_usage / cache_hit / cost_time` | 本次任务模型消耗与耗时 |
| `data.text` | Markdown 产物正文（大任务正文可能很长，按需截断展示） |
| `data.file_name` | 产物文件名。规则：catalog 返回知识目录 json 名；有页面版返回 `{task}.html`；仅文本产物返回 `result.md` 或 `{task}.md`；无落盘产物（library）为空串 |

**产物落盘**（仅 `data.file_name` 非空的任务）：`data/{user_id}/output/{request_id}/` 目录下，
`{task}.html`（页面版，样式自包含单文件）+ `result.md` / `{task}.md`（Markdown）；
graph 为交互式 `graph.html`；catalog 的 json 在 `data/{user_id}/knowledge/catalogs/{学科拼音}/`。

### 2.4 错误约定

| HTTP | 场景 | 响应体 |
|---|---|---|
| 400 | 缺少必填请求头/必填字段/字段取值非法 | `{"code": 400, "request_id": "…", "message": "缺少…"}` |
| 404 | 任务不存在 / 产物文件不存在 | 同上结构 |
| 422 | 请求体不符合模型（如 texts 未知 key、类型错误） | Pydantic 默认校验错误体 |
| 500 | 任务运行失败 / 未捕获异常 | `{"code": 500, "request_id": "…", "message": "任务运行失败：…"}` |

错误响应一律**不含** `monitor` 与 `data` 字段（避免全 0/空字段噪音）。
**异步任务接口（第 3 节）的错误体不同**：固定为 `{"code": <HTTP 状态码>, "message": "<原因>"}`（见 3.8），
且四个接口共用同一份“任务快照”响应体（见 3.2）。

### 2.5 四种端点形态

#### 2.5.1 普通接口（同步 POST）

```
POST /api/v1/{domain}/{task}
```

请求头见 2.1，请求体 TaskRequest（2.2），响应 TaskResponse（2.3）。
阻塞直到任务跑完（十几秒到几分钟），适合小文本调试与不需要实时进度的场景；
长任务建议用流式（2.5.2）或异步接口（第 3 节）。

#### 2.5.2 流式接口（POST NDJSON）

```
POST /api/v1/{domain}/{task}/stream
```

请求体与校验规则和普通接口**完全一致**（校验失败仍直接返回 HTTP 错误，不走流）。
响应为 **NDJSON**（`Content-Type: application/x-ndjson`），每行一个 JSON 事件：

| 事件 | 字段 | 说明 |
|---|---|---|
| `{"type": "phase", "node": str}` | 编排阶段名 | 每进入一个节点推送一次（如 审核/渲染） |
| `{"type": "chunk", "line": str, "title": str, "text": str}` | 渲染文本增量 | `text` 为本次增量，前端按行追加 |
| `{"type": "done", "code": 0, "request_id": str, "message": "success", "quality_warning": str\|null, "monitor": {…}, "data": {…}}` | 最终结果 | 字段与普通响应同构（多一个 `quality_warning` 质量提示） |
| `{"type": "error", "code": int, "message": str}` | 运行失败 | `code` 4xx 表示输入类错误、5xx 表示可重试的运行错误 |

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

#### 2.5.3 下载接口（GET 附件）

```
GET /api/v1/{domain}/{task}/file/{request_id}/{file_name}
```

- `request_id` = 普通/流式接口响应里的 `request_id`，`file_name` = 响应里的 `data.file_name`。
- 返回 `Content-Disposition: attachment`（浏览器弹保存），`user_id` 用 `?user_id=` 或 `X-User-Id` 提供。
- 产物不存在返回 404，提示缺哪个文件。

```bash
curl -OJ "http://127.0.0.1:8000/api/v1/meeting/minutes/file/<request_id>/minutes.html?user_id=1"
```

#### 2.5.4 预览接口（GET 页面版）

```
GET /api/v1/{domain}/{task}/preview?request_id=&user_id=
```

- 只允许取产物目录内的 `{task}.html`（受 `resolve_output_file` 校验，**不暴露 `/data` 整树**）。
- 无 `Content-Disposition` 头 → 浏览器直接渲染；适合人工查看页面版产物。

#### 2.5.5 静态路径与产物定位速查

服务把项目根 `data/` 目录挂为静态资源，`/data/{user_id}/output/{request_id}/{task}.html` 等可直接访问（**无鉴权**）。

| 已拿到 | 位置/URL |
|---|---|
| `request_id` + `file_name` | `/data/{user_id}/output/{request_id}/{file_name}`（静态，浏览器直接打开） |
| 支持下载/预览的任务线（meeting 六线 + notes graph/checklist） | `/api/v1/{domain}/{task}/preview?request_id=…&user_id=…` 预览；`/api/v1/{domain}/{task}/file/{request_id}/{file_name}` 下载 |
| catalog 目录数据 | `data/{user_id}/knowledge/catalogs/{学科拼音}/{file_name}`（`file_name` 为 catalog 响应值） |

> 未传 `X-User-Id` 的历史兼容路径 `data/output/{request_id}/` 仍被 `/data` 静态目录覆盖，
> 但新调用请始终携带用户头。

### 2.6 meeting 域（6 条任务线）

#### 2.6.1 会议纪要 `minutes`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/meeting/minutes` |
| 流式 | `POST /api/v1/meeting/minutes/stream` |
| 下载 | `GET /api/v1/meeting/minutes/file/{request_id}/{file_name}` |
| 预览 | `GET /api/v1/meeting/minutes/preview?request_id=&user_id=` |

- 必填：`texts.transcript`（会议转写文本）。
- `extra.memory=true` 时：命中历史会议记忆则正文带"参考历史会议"来源标注并写入会议记忆
  （按 `extra.project` 聚合）；`time` 非空时写入记忆时间。
- 产物：`minutes.html`（页面版）+ `result.md`。

```jsonc
// 请求
{ "time": "", "texts": { "transcript": "<会议转写文本>", "keypoints": "", "notes": "" },
  "docs": [], "extra": { "template": "", "profile": "", "project": "", "subject": "", "style": "", "memory": false } }
// 响应 data
{ "text": "# 会议纪要标题\n…", "file_name": "minutes.html" }
```

```bash
# 带记忆的会议纪要（第二场会可接住第一场的项目进展）
curl -X POST http://127.0.0.1:8000/api/v1/meeting/minutes -H "Content-Type: application/json" \
  -H "X-Request-Id: $(uuidgen)" -H "X-User-Id: 1" \
  -d '{"time":"2026-09-07","texts":{"transcript":"<会议转写文本>"},"extra":{"memory":true,"project":"<项目名(可选)>"}}'
```

#### 2.6.2 待办行动 `actions`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/meeting/actions` |
| 流式 | `POST /api/v1/meeting/actions/stream` |
| 下载 | `GET /api/v1/meeting/actions/file/{request_id}/{file_name}` |
| 预览 | `GET /api/v1/meeting/actions/preview?request_id=&user_id=` |

- 必填：`texts.transcript`。从会议中提取待办与分工（含负责人、时间要求）。
- 产物：`actions.html` + `actions.md`。

#### 2.6.3 风险分析 `risks`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/meeting/risks` |
| 流式 | `POST /api/v1/meeting/risks/stream` |
| 下载 | `GET /api/v1/meeting/risks/file/{request_id}/{file_name}` |
| 预览 | `GET /api/v1/meeting/risks/preview?request_id=&user_id=` |

- 必填：`texts.transcript`。输出风险条目（描述/严重度/来源/应对/负责人）。
- 产物：`risks.html` + `risks.md`。

#### 2.6.4 多样式纪要 `minutes_styles`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/meeting/minutes_styles` |
| 流式 | `POST /api/v1/meeting/minutes_styles/stream` |
| 下载 | `GET /api/v1/meeting/minutes_styles/file/{request_id}/{file_name}` |
| 预览 | `GET /api/v1/meeting/minutes_styles/preview?request_id=&user_id=` |

- 必填：`texts.transcript`、`extra.style`（组织模式，取值：`time` 时间线 / `logic` 逻辑 /
  `causal` 因果 / `party` 分角色 / `urgency` 优先级）。
- 产物：`minutes_styles.html` + `minutes_styles.md`。

#### 2.6.5 溯源纪要 `minutes_trace`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/meeting/minutes_trace` |
| 流式 | `POST /api/v1/meeting/minutes_trace/stream` |
| 下载 | `GET /api/v1/meeting/minutes_trace/file/{request_id}/{file_name}` |
| 预览 | `GET /api/v1/meeting/minutes_trace/preview?request_id=&user_id=` |

- 必填：`texts.transcript`（会议事实）+ `texts.keypoints`（用户重点）+ `texts.notes`（用户笔记）。
- 用户重点/笔记作为溯源材料参与对齐；输出结论、风险、行动均带原文溯源钉。
- 产物：`minutes_trace.html`（左正文 / 右证据审阅栏）+ `minutes_trace.md`。

#### 2.6.6 共识决策 `consensus_decision`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/meeting/consensus_decision` |
| 流式 | `POST /api/v1/meeting/consensus_decision/stream` |
| 下载 | `GET /api/v1/meeting/consensus_decision/file/{request_id}/{file_name}` |
| 预览 | `GET /api/v1/meeting/consensus_decision/preview?request_id=&user_id=` |

- 必填：`texts.transcript`。输出议题共识结论与因果推导报告。
- 产物：`consensus_decision.html` + `consensus_decision.md`。

### 2.7 notes 域（4 条任务线）

#### 2.7.1 笔记知识图谱 `graph`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/notes/graph` |
| 流式 | `POST /api/v1/notes/graph/stream` |
| 下载 | `GET /api/v1/notes/graph/file/{request_id}/{file_name}` |
| 预览 | `GET /api/v1/notes/graph/preview?request_id=&user_id=` |

- 必填：`docs`（`data/{user_id}/docs/` 下的笔记 `.txt/.md` 文件；图片会先 OCR + 审校再解析）。
- `extra.subject` 用于按用户+学科做图谱增量合并；`extra.memory=true` 时跨会话增量（新增节点高亮）。
- 产物：交互式 `graph.html`（Cytoscape.js，自包含单文件）；无 md 落盘（正文在 `data.text`）。

#### 2.7.2 资料入库 `library`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/notes/library` |
| 流式 | `POST /api/v1/notes/library/stream` |
| 下载 | 不提供（无落盘产物） |
| 预览 | 不提供（无页面版产物） |

- 必填：`extra.subject`、`docs`（文档/图片全量入库：PPT/PDF/docx/xlsx/txt/图片）。
- 入库后资料进入该用户该学科的知识库（向量索引），供检索与带出处问答。
- **无落盘产物文件**：结果文本与统计只在响应 `data.text` 中返回，`data.file_name` 为空串。

#### 2.7.3 知识目录 `catalog`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/notes/catalog` |
| 流式 | `POST /api/v1/notes/catalog/stream` |
| 下载 | 不提供（`file_name` 指向知识目录 json，不在 output 目录） |
| 预览 | 不提供（无页面版产物） |

- 必填：`extra.subject`（学科，中文自动转拼音）。
- `docs` 中 `.txt` 会作为老师重点读取；无输入文本时按该学科已入库资料生成/增量更新目录。
- 产物：目录数据 json 写入 `data/{user_id}/knowledge/catalogs/{学科拼音}/{时间戳}.json`
  （`data.file_name` 返回该文件名）；`data.text` 为目录树 Markdown；同时落盘 `result.md`。

#### 2.7.4 复习清单 `checklist`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/notes/checklist` |
| 流式 | `POST /api/v1/notes/checklist/stream` |
| 下载 | `GET /api/v1/notes/checklist/file/{request_id}/{file_name}` |
| 预览 | `GET /api/v1/notes/checklist/preview?request_id=&user_id=` |

- 必填：`extra.subject`、`docs`——docs 里**必须包含一个 catalog json 文件名**
  （catalog 响应 `data.file_name`），可再追加一个老师重点 `.txt`。
- 任务基于指定/最新的知识目录生成复习清单：高优先知识点为完整卡片，低优先为简要条目。
- `data.text` 为**精简摘要**（统计 + 卡片列表，适合接口返回）；完整 Markdown 落盘 `result.md`，
  页面版 `checklist.html`（推荐用预览/下载查看全量）。

#### 2.7.5 notes 域顺序依赖示例（入库 → 目录 → 清单）

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
# 4) 取产物（用各步响应里的 request_id 与 data.file_name）
curl -OJ "http://127.0.0.1:8000/api/v1/notes/checklist/file/<rid>/checklist.html?user_id=1"
# 浏览器预览：http://127.0.0.1:8000/api/v1/notes/checklist/preview?request_id=<rid>&user_id=1
```

---

## 3. 异步任务接口（`/api/v1/tasks`）

新增的一组接口，**生产主路径**：提交立即返回任务快照，任务在后台执行，进度与结果通过另外三个接口获取。
它不替代第 2 节的接口，而是把"受理"与"执行"解耦 —— 长任务不再占用一个 HTTP 连接，
并发可控、失败可重试、服务重启不丢任务。

任务线由请求体的 `domain` + `task` 指定（取值与第 2 节完全一致），所以这组只有四个端点、与具体任务线解耦；
**四个接口返回同一份"任务快照"**（见 3.2），差别只在填充程度。

任务状态与事件流存在 **Redis**：`.env` 的 `REDIS_URL`（缺省 `redis://127.0.0.1:6379/0`）、
`AGENTFLOW_JOB_TTL_SECONDS`（缺省 7 天）。Redis 不可用时本组接口返回 503，第 2 节的接口不受影响。
执行模式（`inline` / `queue`）见 `GET /api/v1/health` 的 `run_mode` 字段。

### 3.1 请求体（AsyncTaskRequest = TaskRequest + `domain` / `task`）

```jsonc
{
  "domain": "meeting",              // meeting / notes
  "task": "minutes",                // 该域下的任务线（见 0.2 矩阵）
  "time": "",
  "texts": {"transcript": "会议转写文本"},
  "docs": [],
  "extra": {"memory": false}
}
```

除 `domain` / `task` 外，字段与语义完全等同于 2.2 的 TaskRequest（含各任务线的必填项）。

### 3.2 统一响应体（四个接口共用）

```jsonc
{
  "code": 0,                    // 0=成功；非 0=HTTP 状态码
  "job_id": "job_…",
  "request_id": "request_…",    // 下载产物要用（/file/{request_id}/{file_name}）
  "status": "queued",           // queued / running / succeeded / failed
  "message": "queued",          // 阶段名 或 失败原因（人可读）
  "text": null,                 // 产物正文：仅结果接口有值
  "file_name": "",              // 产物文件名：结果接口（及已成功的状态查询）有值
  "monitor": {                  // 消耗：零值起步
    "token_usage": 0, "cache_hit": 0, "cost_time": 0.0
  }
}
```

| 字段 | 说明 |
|---|---|
| `code` | 0=这次 HTTP 调用成功；非 0=HTTP 状态码（错误体见 3.8）。**任务本身的成败看 `status`** |
| `job_id` | 任务标识，四个接口恒定回传 |
| `request_id` | 产物目录名；配 `file_name` 可下载（`GET /api/v1/{domain}/{task}/file/{request_id}/{file_name}`） |
| `status` | **给代码判断**：`queued`（排队/待执行）、`running`（执行中）、`succeeded`、`failed` |
| `message` | **给人看**：执行中为阶段（`running:meeting_understanding`）或正在渲染的线名（`会议纪要`）；失败时为错误原因；成功为 `success`；重排为 `requeued(attempt N)` |
| `text` | Markdown 产物正文，**只有结果接口**返回（状态轮询恒为 `null`，避免每次轮询背大文本） |
| `file_name` | 产物文件名（如 `minutes.html`），成功后即可用于下载 / 预览 |
| `monitor` | 本次消耗：`token_usage` / `cache_hit` / `cost_time`（秒） |
| `quality_warning` | **可选字段**：渲染质量提示，仅结果接口在非空时出现 |

四个接口只在**填充程度**上有区别：

| 接口 | `status` | `message` | `text` | `file_name` | `monitor` |
|---|---|---|---|---|---|
| 提交（3.3） | `queued` | `queued` | `null` | `""` | 零值 |
| 状态（3.4） | 实时 | 阶段 / 失败原因 | 恒 `null` | 成功后填 | 实时 |
| 结果（3.5） | 成功 `succeeded`；未完成或失败则原样返回 | 同上 | 成功时给正文 | 同上 | 实时 |
| 事件流（3.6） | 每行实时 | 同上 | 仅 `chunk`（增量）与 `done` | `done` 时 | `done` 时 |

一个 job 的完整示例（同一份快照的四种填充）：

```jsonc
// ① POST /api/v1/tasks —— 提交
{"code": 0, "job_id": "job_637571127538876418", "request_id": "request_637571127538876417",
 "status": "queued", "message": "queued", "text": null, "file_name": "",
 "monitor": {"token_usage": 0, "cache_hit": 0, "cost_time": 0.0}}

// ② GET /api/v1/tasks/{job_id} —— 3 秒后查状态
{"code": 0, "job_id": "job_…418", "request_id": "request_…417",
 "status": "running", "message": "running:minutes", "text": null, "file_name": "",
 "monitor": {"token_usage": 8200, "cache_hit": 5120, "cost_time": 3.2}}

// ③ GET /api/v1/tasks/{job_id}/result —— 完成后取结果
{"code": 0, "job_id": "job_…418", "request_id": "request_…417",
 "status": "succeeded", "message": "success",
 "text": "# 复习清单页面加载速度专项对齐会…", "file_name": "minutes.html",
 "monitor": {"token_usage": 11932, "cache_hit": 7040, "cost_time": 9.6}}
```

> `status` 与 `message` 的分工：`status` 是状态机枚举（固定四个取值，给 `if` / `switch` 用），
> `message` 是这一刻的可读说明（阶段、原因）。只留前者会不知道失败原因，只留后者就得靠字符串匹配判断状态
> —— 这与 HTTP 的"状态码 + reason phrase"是同一模式。

### 3.3 提交任务 `POST /api/v1/tasks`

请求头：`X-User-Id` 必填，`X-Request-Id` 可选（缺省时服务端生成）。
响应即上面①的快照：`status=queued`、`monitor` 零值、`text` 为 `null`。

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/tasks \
  -H "Content-Type: application/json" -H "X-User-Id: 1" \
  -d '{"domain":"meeting","task":"minutes","texts":{"transcript":"<会议转写文本>"},"docs":[],"extra":{}}'
```

> `.env` 的 `AGENTFLOW_RUN_MODE=queue` 时任务不会立即执行：必须至少有一个
> `python -m app.worker` 在跑，否则会一直停在 `status=queued`（`LLEN agentflow:queue` 能看到它）。
> `inline`（缺省）由 API 进程内的 BackgroundTasks 直接执行，起一个 uvicorn 就能用
> （失败即终态、无重试，行为与旧版一致）。

### 3.4 查询状态 `GET /api/v1/tasks/{job_id}`

轮询接口，返回同一份快照，`text` 恒为 `null`。建议间隔 1~2 秒。

- `status` 为 `queued` / `running` → 继续等；
- `succeeded` → 用 3.5 取正文，或直接用 `request_id` + `file_name` 下载 / 预览；
- `failed` → `message` 就是失败原因。

```bash
curl -s http://127.0.0.1:8000/api/v1/tasks/<job_id>
```

### 3.5 获取结果 `GET /api/v1/tasks/{job_id}/result`

仍是同一份快照，**成功的任务会带上 `text`（正文）与 `file_name`**。

任务还没跑完或已失败时**同样返回 200 + 该快照**（`status` 为 `queued` / `running` / `failed`，
失败原因在 `message`），不用处理 409 分支；只有 job 不存在才返回 404。

```bash
curl -s http://127.0.0.1:8000/api/v1/tasks/<job_id>/result
```

### 3.6 事件流 `GET /api/v1/tasks/{job_id}/stream`

响应为 NDJSON，每行一个事件：**恒定带 `type` + `job_id` + `status` + `message`**，其余按事件补充，
字段名与 3.2 完全一致。支持 `cursor` 从指定下标开始读取（断线重连）：

```
GET /api/v1/tasks/{job_id}/stream?cursor=0
```

| `type` | 补充字段 | 说明 |
|---|---|---|
| `queued` | `request_id` | 已受理 |
| `started` | `attempt` | 第 attempt 次尝试开始执行 |
| `phase` | —（`message` 即 `running:{阶段}`） | 阶段推进 |
| `chunk` | `text` | 渲染文本**增量**，前端按行追加 |
| `requeued` | `attempt` | 放回队列等下一次尝试（尚未终态） |
| `error` | `code` | 失败；`code` 是**任务失败码**（4xx 输入类不重试 / 5xx 可重试） |
| `done` | `request_id` / `text` / `file_name` / `monitor`（+ 可选 `quality_warning`） | 成功终态，**与 3.5 结果接口逐字一致**（只多一个 `type`） |

```jsonc
{"type": "queued",  "job_id": "job_…418", "request_id": "request_…417", "status": "queued",  "message": "queued"}
{"type": "started", "job_id": "job_…418", "status": "running", "message": "running", "attempt": 1}
{"type": "phase",   "job_id": "job_…418", "status": "running", "message": "running:meeting_understanding"}
{"type": "chunk",   "job_id": "job_…418", "status": "running", "message": "会议纪要", "text": "# 复习清单页面"}
{"type": "done",    "job_id": "job_…418", "request_id": "request_…417", "status": "succeeded",
                    "message": "success", "text": "# 复习清单…", "file_name": "minutes.html",
                    "monitor": {"token_usage": 11932, "cache_hit": 7040, "cost_time": 9.6}}
```

```bash
curl -N "http://127.0.0.1:8000/api/v1/tasks/<job_id>/stream?cursor=0"
```

### 3.7 执行模式与队列语义

执行位置由 `.env` 的 `AGENTFLOW_RUN_MODE` 决定（也可从 `GET /api/v1/health` 的 `run_mode` 读到）：

| 模式 | 执行者 | 说明 |
|---|---|---|
| `inline`（缺省） | API 进程内的 BackgroundTasks | 起一个 uvicorn 就能用；不建租约、失败即终态、无重试 |
| `queue` | 独立进程 `python -m app.worker` 消费 `agentflow:queue` | 生产主路径：并发上限、失败重试、重启不丢任务 |

queue 模式额外使用两个 key：`agentflow:queue`（List，待执行队列）与 `agentflow:leases`
（ZSet，member=job_id、score=租约到期时间戳）。两个可直接观测的指标：
`LLEN agentflow:queue` = 积压任务数，`ZCARD agentflow:leases` = 正在执行的任务数。

- **并发上限**：全局并发 = 所有 worker 的 `--concurrency` 之和，看 `ZCARD agentflow:leases`；
  入口限流按请求数限速，管不住执行侧并发，真正的风控点在这里。
- **重试**：5xx / 异常按 `AGENTFLOW_JOB_MAX_ATTEMPTS`（默认 2，含首次）自动重排重试；
  4xx 输入类错误直接终态，不浪费一次模型调用。重试复用同一个 `request_id`，
  所以产物目录与会议记忆（按 request_id 生成 meeting_id）是覆盖而非重复。
- **超时回收**：worker 执行期间按 `AGENTFLOW_HEARTBEAT_SECONDS`（默认 10s）续租约；
  worker 崩溃/被杀后租约在 `AGENTFLOW_LEASE_SECONDS`（默认 60s）后过期，
  任务被收回重排，不会永远卡在 `running`。
- **优雅停机**：worker 收到 SIGTERM/SIGINT 后停止取新任务，跑完手上任务再退出；
  超过 `--grace` 秒未完成则退出，任务由租约超时兜底重排。
- **幂等边界**：`library` 入库用确定性块 ID + upsert，重复执行是覆盖；
  `minutes` 的会议记忆按 request_id 派生 meeting_id，重复执行同样覆盖 ——
  但**不要用同一个 request_id 并发执行两次**（例如旧 worker 还活着就手工重投），
  两个进程会同时写同一个产物目录。
- 机制细节（键结构、租约、重试判定、运维观测）见 [README](README.md) 的「异步任务与 Redis」一节。

### 3.8 错误体

本组接口的错误体固定为两个字段（**不套用 3.2 的快照**，也不同于第 2 节的 TaskResponse）：

```jsonc
{"code": 404, "message": "任务不存在：job_xxx"}
```

| HTTP | `message` 示例 | 场景 |
|---|---|---|
| 400 | `domain 仅支持 meeting / notes` / `缺少 X-User-Id` | 域非法 / 缺用户标识 |
| 404 | `任务线不存在：no_such` / `meeting 不支持任务线：graph` / `任务不存在：job_…` | 任务线非法 / job 不存在 |
| 422 | （Pydantic 默认校验错误体） | 请求体不合模型 |
| 503 | `Redis 不可用（<url>）：…` / `任务入队失败：…` | Redis 不可用 |

> 注意区分：**调用失败** = HTTP 状态码 + `{code, message}`；**任务失败** = 200 + 快照里的
> `status=failed` + `message=失败原因`。

### 3.9 调用顺序示例

```bash
# 1) 提交 → 记下 job_id（响应 status=queued）
curl -s -X POST http://127.0.0.1:8000/api/v1/tasks -H "Content-Type: application/json" \
  -H "X-User-Id: 1" \
  -d '{"domain":"meeting","task":"minutes","texts":{"transcript":"<会议转写文本>"},"docs":[],"extra":{}}'
# 2) 轮询状态（queued → running:阶段 → succeeded / failed）
curl -s http://127.0.0.1:8000/api/v1/tasks/<job_id>
# 3) 取结果（同一份快照，成功时带 text / file_name）
curl -s http://127.0.0.1:8000/api/v1/tasks/<job_id>/result
# 4) 或订阅事件流（NDJSON，支持 ?cursor=N 断线续读）
curl -N "http://127.0.0.1:8000/api/v1/tasks/<job_id>/stream?cursor=0"
# 5) 取产物文件（用结果里的 request_id 与 file_name）
curl -OJ "http://127.0.0.1:8000/api/v1/meeting/minutes/file/<request_id>/minutes.html?user_id=1"
```

客户端一套取值逻辑即可覆盖四个接口：

```python
r = requests.get(f"{base}/api/v1/tasks/{job_id}").json()   # 四个接口通用
if r["code"] != 0:                     # 调用失败
    raise RuntimeError(r["message"])
if r["status"] == "failed":            # 任务失败
    print("失败：", r["message"])
print(r["status"], r["monitor"]["token_usage"], r.get("text") or r.get("file_name"))
```

对应的现成脚本：`minutes_async_submit.py` → `minutes_async_status.py` → `minutes_async_result.py`
→ `minutes_async_stream.py`（脚本里改 `JOB_ID` 与服务地址即可）。
