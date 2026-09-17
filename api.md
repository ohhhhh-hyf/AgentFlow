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
| 健康检查 | `/api/v1/health` | GET | 服务状态 + 执行模式 `run_mode` + 两个域当前任务线清单（第 1 节） |
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

无需请求头。返回服务状态、**异步任务执行模式**与两个域**当前可用**的任务线清单
（领域装配失败时降级报告，不影响其它接口）：

```jsonc
{
  "status": "ok",                                // 或 "degraded"
  "run_mode": "inline",                          // inline / queue：异步任务在哪执行（见 3.7）
  "task_lines": {
    "meeting": ["actions", "consensus_decision", "mindmap", "minutes", "minutes_styles", "minutes_trace", "risks"],
    "notes":   ["catalog", "checklist", "graph", "library", "quiz", "review"]
  }
  // status=degraded 时追加: "degraded": ["notes: <异常信息>"]
}
```

> `run_mode` 是服务级配置（`.env` 的 `AGENTFLOW_RUN_MODE`），提交响应里不再回显它 ——
> 想确认当前模式查这里即可；`queue` 模式必须有 `python -m app.worker` 在跑，否则任务会停在 `queued`。

> `task_lines` 列的是**领域内全部已装配的任务线**，比对外接口多：`mindmap`、`quiz`、`review`
> 等尚未开放 HTTP 接口的任务线只在这里出现（黑名单之外的差异以第 2 节的矩阵为准）。

---

## 2. 任务线接口（`/api/v1/{domain}/{task}`）

老接口，URL 自带 `domain`（`meeting` / `notes`）与 `task`。每条任务线固定四种形态：
普通、流式、下载、预览（后两种仅当该任务线有落盘产物）。

> notes 域当前对外任务线为 `graph` / `library` / `catalog` / `checklist`，规则均以本文为准。

先讲三种形态共用的**请求头 / 请求体 / 响应体 / 错误**，再讲四种形态的协议，最后逐条介绍 10 条任务线。

### 2.1 请求头

| 头 | 必填 | 适用 | 说明 |
|---|---|---|---|
| `X-Request-Id` | POST 可选 | 普通 / 流式 | 调用方追踪 ID。缺省时服务端自动生成 `request_` + 分布式数字 ID。产物目录以最终 request_id 为名：`data/{user_id}/output/{request_id}/`；下载、结果核对都靠它定位。**自传时请用安全字符**（不含 `/`、`\`、`..`）—— 它会直接成为目录名。 |
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
- `docs` 里的**图片**会自动 OCR 成文本并入正文：多张**并发识别**，结果**按 `docs` 顺序拼接**
  （顺序可预期，可放心按页码排好再传）；页眉/页脚/页码（校名、地址电话、印刷编号等）会被剔除，
  不进正文。判据**逐图自适应**：以该图自身的行高中位数为标尺（印刷校名通常达 1.6 倍以上），
  结合它是否落在该图正文范围的上下 12% 边缘带内来判断，因此**不要求**页眉每页重复、
  也不要求各页排版一致；跨页重复的行另有一道路后备判据。
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
且四个接口共用同一份"任务快照"响应体（见 3.2）。

> **成败怎么看**：同步 / 流式接口，`code == 0` 就是成功、非 0 就是失败（等于 HTTP 状态码）；
> 异步接口要区分"这次调用的成败"与"任务本身的成败"，所以看 `status` 而不是只看 `code`（见 3.8 的三态表）。

### 2.5 四种端点形态

#### 2.5.1 普通接口（同步 POST）

```
POST /api/v1/{domain}/{task}
```

请求头见 2.1，请求体 TaskRequest（2.2），响应 TaskResponse（2.3）。
阻塞直到任务跑完（十几秒到几分钟），适合小文本调试与不需要实时进度的场景；
长任务建议用流式（2.5.2）或异步接口（第 3 节）。

完整示例（`minutes`）：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/meeting/minutes \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 1" \
  -H "X-Request-Id: $(uuidgen)" \
  -d '{"time":"","texts":{"transcript":"<会议转写文本>"},"docs":[],"extra":{}}'
```

```jsonc
{
  "code": 0,
  "request_id": "3f9a…",                  // 保存它：产物目录名，用于下载/预览
  "message": "success",
  "monitor": {"token_usage": 11932, "cache_hit": 7040, "cost_time": 9.6},
  "data": {
    "text": "# 会议纪要标题\n…",           // Markdown 正文
    "file_name": "minutes.html"           // 页面版文件名；配 request_id 可下载/预览
  }
}
```

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
- **顺序跟随原文**：章 / 主题 / 知识点按资料原文（文件 → 页码 → 块序）的先后顺序排列，
  不按重要性或主题聚类重排（生成后还有一道确定性保序兜底）。增量更新时，
  本次资料里没有的历史遗留章节排在末尾。
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
- `data.text` 为**精简摘要**（统计 + 卡片列表，每条只有名称与所属章节，**不含卡片正文**）；
  完整 Markdown 落盘 `result.md`，页面版 `checklist.html`（推荐用预览/下载查看全量）。

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

常用的四个接口：

| 接口 | 方法 | 作用 | 一句话 |
|---|---|---|---|
| `/api/v1/tasks` | POST | 提交任务 | 拿 `job_id`，立刻返回（3.3） |
| `/api/v1/tasks/{job_id}` | GET | 查状态 | 轮询进度，不含正文（3.4） |
| `/api/v1/tasks/{job_id}/result` | GET | 取结果 | 同一份快照，成功时带正文（3.5） |
| `/api/v1/tasks/{job_id}/stream` | GET | 订阅事件流 | NDJSON，可断线重连（3.6） |

**四个接口返回同一份"任务快照"**（见 3.2），差别只在填充程度。
任务线由请求体的 `domain` + `task` 指定（取值与第 2 节完全一致），所以这组与具体任务线解耦。

任务状态与事件流存在 **Redis**：`.env` 的 `REDIS_URL`（缺省 `redis://127.0.0.1:6379/0`）、
`AGENTFLOW_JOB_TTL_SECONDS`（缺省 7 天）。Redis 不可用时本组接口返回 503，第 2 节的接口不受影响。
执行模式（`inline` / `queue`）看 `GET /api/v1/health` 的 `run_mode` 字段。

### 3.1 请求体（AsyncTaskRequest = TaskRequest + `domain` / `task`）

```jsonc
{
  "domain": "meeting",              // meeting / notes
  "task": "minutes",                // 该域下的任务线（见 0.2 矩阵）
  "time": "",                       // 任务时间（会议开始/转录完成时刻），可空
  "texts": {                        // 与第 2 节同构：transcript / keypoints / notes
    "transcript": "会议转写文本",
    "keypoints": "",
    "notes": ""
  },
  "docs": [],                       // 文件名列表（data/{user_id}/docs/ 或 catalog 目录）
  "extra": {                        // 与第 2 节同构
    "template": "", "profile": "", "project": "", "subject": "", "style": "", "memory": false
  }
}
```

除 `domain` / `task` 外，字段语义、`docs` 的取用规则、各任务线的**必填项**与第 2 节完全一致
（见 2.2 与 0.2）：例如 `minutes` 必填 `texts.transcript`、`library` 必填 `extra.subject` + `docs`、
`minutes_trace` 必填 `transcript` + `keypoints` + `notes`。

最小可用请求（按任务线）：

| 任务线 | 最小请求体 |
|---|---|
| `minutes` / `actions` / `risks` / `consensus_decision` | `{"domain":"meeting","task":"<线>","texts":{"transcript":"<转写文本>"}}` |
| `minutes_styles` | 同上 + `"extra":{"style":"time"}`（`time`/`logic`/`causal`/`party`/`urgency`） |
| `minutes_trace` | 同上 + `"texts":{"transcript":"…","keypoints":"<重点>","notes":"<笔记>"}` |
| `graph` | `{"domain":"notes","task":"graph","docs":["<笔记.txt>"]}` |
| `library` | `{"domain":"notes","task":"library","docs":["<文件.docx>"],"extra":{"subject":"<学科>"}}` |
| `catalog` | `{"domain":"notes","task":"catalog","extra":{"subject":"<学科>"}}` |
| `checklist` | `{"domain":"notes","task":"checklist","docs":["<catalog文件名.json>"],"extra":{"subject":"<学科>"}}` |

> `catalog` 的结构与顺序以**已入库合并稿解析出的有序骨架**为准（覆盖每个小节、按原文先后排序，
> 程序会把模型漏掉的节点补回并标 `node_status=program_restore`）。
> `catalog` 的结构保证与监控指标见 `README.md` 的知识目录说明。

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

| 字段 | 类型 | 出现时机 | 说明 |
|---|---|---|---|
| `code` | int | 恒有 | 0=这次 HTTP 调用成功；非 0=HTTP 状态码（错误体见 3.8）。**任务本身的成败看 `status`** |
| `job_id` | str | 恒有 | 任务标识，提交时生成（`job_` + 分布式数字 ID），四个接口恒定回传 |
| `request_id` | str | 恒有 | 产物目录名（`data/{user_id}/output/{request_id}/`）；配 `file_name` 可下载/预览。提交时若带了 `X-Request-Id` 则用它 |
| `status` | str | 恒有 | **给代码判断**，只有四个取值：`queued`（排队/待执行）、`running`（执行中）、`succeeded`、`failed` |
| `message` | str | 恒有 | **给人看**：执行中为阶段（`running:meeting_understanding`）或正在渲染的线名（`会议纪要`）；失败时是错误原因；成功是 `success`；重排是 `requeued(attempt N)` |
| `text` | str\|null | 仅结果接口 | Markdown 产物正文（来源见 3.5）；状态轮询恒为 `null`，避免每次轮询背大文本 |
| `file_name` | str | 成功后 | 产物文件名（如 `minutes.html`）；无落盘产物的任务线为空串 |
| `monitor` | obj | 恒有 | 本次消耗：`token_usage`（总 token）、`cache_hit`（缓存命中 token）、`cost_time`（秒） |
| `quality_warning` | str | 可选 | 渲染质量提示，仅结果接口在非空时出现（同步/流式接口没有这个字段） |

**字段随阶段的变化**（同一个 job 从提交到完成）：

| 阶段 | `status` | `message` | `text` | `file_name` | `monitor` |
|---|---|---|---|---|---|
| 刚提交 | `queued` | `queued` | `null` | `""` | 零值 |
| 排队中（多人同时提交） | `queued` | `requeued(attempt N)` 表示被重排过 | `null` | `""` | 零值 |
| 执行中 | `running` | `running:{阶段}` / 渲染中的线名 | `null` | `""` | 实时增长 |
| 成功 | `succeeded` | `success` | 结果接口给正文 | `{task}.html` 等 | 完整 |
| 失败 | `failed` | 错误原因 | `null` | `""` | 失败前消耗 |

> `status` 与 `message` 的分工：`status` 是状态机枚举（固定四个取值，给 `if` / `switch` 用），
> `message` 是这一刻的可读说明（阶段、原因）。只留前者会不知道失败原因，只留后者就得靠字符串匹配判断状态
> —— 这与 HTTP 的"状态码 + reason phrase"是同一模式。

### 3.3 提交任务 `POST /api/v1/tasks`

- 请求头：`X-User-Id` 必填、`X-Request-Id` 可选（缺省时服务端生成）、`Content-Type: application/json`；
- 成功返回 **HTTP 200** + 快照（`status=queued`、`monitor` 零值、`text=null`）；
- 校验失败见 3.8（`domain`/`task` 非法、缺 `X-User-Id` 等都在提交时就返回错误，不会建 job）。

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 1" \
  -H "X-Request-Id: $(uuidgen)" \
  -d '{"domain":"meeting","task":"minutes","texts":{"transcript":"<会议转写文本>"},"docs":[],"extra":{}}'
```

响应：

```jsonc
{
  "code": 0,
  "job_id": "job_637571127538876418",
  "request_id": "request_637571127538876417",
  "status": "queued",
  "message": "queued",
  "text": null,
  "file_name": "",
  "monitor": {"token_usage": 0, "cache_hit": 0, "cost_time": 0.0}
}
```

两种执行模式下的差别（模式见 `GET /api/v1/health` 的 `run_mode`）：

| 模式 | 提交之后 |
|---|---|
| `queue` | 任务入队后由 `python -m app.worker` 执行。若没有 worker 在跑，会一直停在 `queued`（`LLEN agentflow:queue` 能看到它） |
| `inline`（缺省） | API 进程内的 BackgroundTasks 立刻执行；不建租约、失败即终态（不重试） |

### 3.4 查询状态 `GET /api/v1/tasks/{job_id}`

轮询接口，返回同一份快照，**`text` 恒为 `null`**（正文只在结果接口给）。
建议轮询间隔 **1~2 秒**；`queued` 阶段可能持续较久（并发满了在排队），不要用固定次数就放弃。

```bash
curl -s http://127.0.0.1:8000/api/v1/tasks/job_637571127538876418
```

```jsonc
// 执行中
{"code": 0, "job_id": "job_…418", "request_id": "request_…417",
 "status": "running", "message": "running:minutes", "text": null, "file_name": "",
 "monitor": {"token_usage": 8200, "cache_hit": 5120, "cost_time": 3.2}}

// 已完成（同一个接口，此时 file_name 有值但仍不给正文）
{"code": 0, "job_id": "job_…418", "request_id": "request_…417",
 "status": "succeeded", "message": "success", "text": null, "file_name": "minutes.html",
 "monitor": {"token_usage": 11932, "cache_hit": 7040, "cost_time": 9.6}}

// 失败（message 就是原因）
{"code": 0, "job_id": "job_…418", "request_id": "request_…417",
 "status": "failed", "message": "texts / docs 至少提供一个", "text": null, "file_name": "",
 "monitor": {"token_usage": 0, "cache_hit": 0, "cost_time": 0.2}}
```

三种情况怎么处理：

- `queued` / `running` → 继续轮询（或改用 3.6 的事件流拿实时进度）；
- `succeeded` → 用 3.5 取正文，或直接用 `request_id` + `file_name` 下载 / 预览；
- `failed` → `message` 就是失败原因；`request_id` 目录下通常有中间产物可供排查。

### 3.5 获取结果 `GET /api/v1/tasks/{job_id}/result`

仍是同一份快照，**成功的任务会带上 `text`（正文）与 `file_name`**。

```bash
curl -s http://127.0.0.1:8000/api/v1/tasks/job_637571127538876418/result
```

```jsonc
{
  "code": 0,
  "job_id": "job_637571127538876418",
  "request_id": "request_637571127538876417",
  "status": "succeeded",
  "message": "success",
  "text": "# 复习清单页面加载速度专项对齐会\n…（Markdown 正文）…",
  "file_name": "minutes.html",
  "monitor": {"token_usage": 11932, "cache_hit": 7040, "cost_time": 9.6}
}
```

**`text` 是 Markdown 正文，不是文件内容本身**：接口不读磁盘，也不返回 HTML。三种来源：

| 任务线 | `text` 是什么 |
|---|---|
| 多数任务线（minutes / actions / risks / minutes_styles / minutes_trace / consensus_decision / catalog） | 落盘的 `result.md` / `{task}.md` **全文**（与产物目录里那份内容一致） |
| `checklist` | **精简摘要**（统计 + 卡片列表）。完整版在 `result.md` 与 `checklist.html` 里，想看全量要下载/预览 |
| `graph` | 图谱报告文本（该线**无 md 落盘**） |

`file_name` 的取值规则（`_output_file_name`）：

| 情况 | `file_name` |
|---|---|
| `catalog` | 知识目录 json 文件名（在 `data/{user_id}/knowledge/catalogs/{学科拼音}/`） |
| 有页面版 HTML 的任务线 | `{task}.html`（如 `minutes.html`） |
| 只有文本产物 | `result.md` 或 `{task}.md` |
| 无落盘产物（`library`） | 空串 `""` |

**取文件**（接口只返回数据，URL 需要自己用 `request_id` + `file_name` 拼）：

```bash
rid="request_637571127538876417"
# ① 下载页面版 HTML（file_name 就是返回里的那个）
curl -OJ "http://127.0.0.1:8000/api/v1/meeting/minutes/file/$rid/minutes.html?user_id=1"
# ② 浏览器直接看页面版
open "http://127.0.0.1:8000/api/v1/meeting/minutes/preview?request_id=$rid&user_id=1"
# ③ 要 Markdown 文件（有 md 落盘的任务线；graph 没有 result.md，会 404）
curl -OJ "http://127.0.0.1:8000/api/v1/meeting/minutes/file/$rid/result.md?user_id=1"
# ④ 同源静态路径（无鉴权）
curl -OJ "http://127.0.0.1:8000/data/1/output/$rid/minutes.html"
```

任务还没跑完或已失败时**同样返回 200 + 该快照**（`status` 为 `queued` / `running` / `failed`，
失败原因在 `message`），不用处理 409 分支；只有 job 不存在才返回 404。

### 3.6 事件流 `GET /api/v1/tasks/{job_id}/stream`

订阅执行过程，响应为 **NDJSON**（`Content-Type: application/x-ndjson`），每行一个事件：
**恒定带 `type` + `job_id` + `status` + `message`**，其余按事件类型补充，字段名与 3.2 完全一致。

```
GET /api/v1/tasks/{job_id}/stream?cursor=0     # cursor = 事件下标，从 0 开始
```

| `type` | 补充字段 | 说明 |
|---|---|---|
| `queued` | `request_id` | 已受理 |
| `started` | `attempt` | 第 attempt 次尝试开始执行 |
| `phase` | —（`message` 即 `running:{阶段}`） | 进入编排节点（审校/渲染等） |
| `chunk` | `text` | 渲染文本**增量**，前端按行追加 |
| `requeued` | `attempt` | 放回队列等下一次尝试（尚未终态） |
| `error` | `code` | 失败；`code` 是**任务失败码**（4xx 输入类不重试 / 5xx 可重试） |
| `done` | `request_id` / `text` / `file_name` / `monitor`（+ 可选 `quality_warning`） | 成功终态，**与 3.5 结果接口逐字一致**（只多一个 `type`） |

```bash
curl -N "http://127.0.0.1:8000/api/v1/tasks/job_…418/stream?cursor=0"
```

```jsonc
{"type": "queued",  "job_id": "job_…418", "request_id": "request_…417", "status": "queued",  "message": "queued"}
{"type": "started", "job_id": "job_…418", "status": "running", "message": "running", "attempt": 1}
{"type": "phase",   "job_id": "job_…418", "status": "running", "message": "running:meeting_understanding"}
{"type": "chunk",   "job_id": "job_…418", "status": "running", "message": "会议纪要", "text": "# 复习清单页面"}
{"type": "chunk",   "job_id": "job_…418", "status": "running", "message": "会议纪要", "text": "加载速度专项对齐会于今日…"}
{"type": "done",    "job_id": "job_…418", "request_id": "request_…417", "status": "succeeded",
                    "message": "success", "text": "# …", "file_name": "minutes.html",
                    "monitor": {"token_usage": 11932, "cache_hit": 7040, "cost_time": 9.6}}
```

- **`cursor` 语义**：事件在 Redis 里按下标顺序保存，`cursor=N` 表示"从第 N 条开始给我"，
  客户端记住已收到的条数就能断线续读（`cursor=0` 是从头回放，适合排查）；
- **终止**：收到 `done` 或 `error` 后服务端会关闭连接；`requeued` 之后还会继续有新的 `started`；
- **什么时候用流式、什么时候用轮询**：需要过程可见（进度条、逐字显示、前端做"正在生成"体验）用 `/stream`；
  只要最终结果、或轮询间隔很长，用 `/status` + `/result` 更省资源（一次真实 minutes 任务实测有 ~150 条 `chunk` 事件）。

### 3.7 执行模式与队列语义

执行位置由 `.env` 的 `AGENTFLOW_RUN_MODE` 决定（也可从 `GET /api/v1/health` 的 `run_mode` 读到）：

| 模式 | 执行者 | 说明 |
|---|---|---|
| `inline`（缺省） | API 进程内的 BackgroundTasks | 起一个 uvicorn 就能用；不建租约、失败即终态、无重试 |
| `queue` | 独立进程 `python -m app.worker` 消费 `agentflow:queue` | 生产主路径：并发上限、失败重试、重启不丢任务 |

queue 模式额外使用两个 Redis key：`agentflow:queue`（List，待执行队列）与 `agentflow:leases`
（ZSet，member=job_id、score=租约到期时间戳）。两个能直接看的指标：

```bash
docker exec -it redis redis-cli -n 0 llen  agentflow:queue    # 积压任务数（排队多长）
docker exec -it redis redis-cli -n 0 zcard agentflow:leases   # 正在执行的任务数（= 全局并发占用）
```

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
- 机制细节（键结构、租约判定、运维观测）见 [README](README.md) 的「异步任务与 Redis」一节。

### 3.8 错误体

本组接口的错误体固定为两个字段（**不套用 3.2 的快照**，也不同于第 2 节的 TaskResponse）：

```jsonc
{"code": 404, "message": "任务不存在：job_xxx"}
```

| HTTP | `message` 示例 | 场景 |
|---|---|---|
| 400 | `domain 仅支持 meeting / notes` / `缺少 X-User-Id` | 域非法 / 缺用户标识 |
| 404 | `任务线不存在：no_such` / `meeting 不支持任务线：graph` / `任务不存在：job_…` | 任务线非法 / job 不存在 |
| 422 | （Pydantic 默认校验错误体：`{"detail":[{...}]}`） | 请求体不合模型（缺 `domain`/`task`、`texts` 出现未知 key 等） |
| 503 | `Redis 不可用（<url>）：…` / `任务入队失败：…` | Redis 不可用 / 入队失败 |

**三种"没拿到想要的东西"要分开判断**（这是最常混淆的地方）：

| 现象 | HTTP | 看哪里 | 含义 |
|---|---|---|---|
| `code != 0` | 400/404/422/503 | `message` | **这次调用失败**（地址、参数、依赖问题） |
| `code == 0` 且 `status == "failed"` | 200 | `message` | **任务失败**：服务端收下了，但执行没成功（输入问题或运行错误） |
| `code == 0` 且 `status` 是 `queued`/`running` | 200 | `message` | **任务还没跑完**：继续轮询或订阅（不是错误） |

### 3.9 客户端完整示例

轮询取结果（四个接口通用同一套取值逻辑）：

```python
import time
import requests

base = "http://127.0.0.1:8000"
sid = requests.post(
    f"{base}/api/v1/tasks",
    json={"domain": "meeting", "task": "minutes",
          "texts": {"transcript": transcript}, "docs": [], "extra": {}},
    headers={"X-User-Id": "1"},
    timeout=30,
).json()
if sid["code"] != 0:                      # 这次调用失败
    raise RuntimeError(sid["message"])
job_id, request_id = sid["job_id"], sid["request_id"]

while True:                               # 轮询到终态
    snap = requests.get(f"{base}/api/v1/tasks/{job_id}", timeout=30).json()
    if snap["status"] != "succeeded" and snap["status"] != "failed":
        print("进行中：", snap["status"], snap["message"], snap["monitor"]["cost_time"], "s")
        time.sleep(2)
        continue
    break

if snap["status"] == "failed":            # 任务失败（HTTP 仍是 200）
    raise RuntimeError(f"任务失败：{snap['message']}")

result = requests.get(f"{base}/api/v1/tasks/{job_id}/result", timeout=60).json()
print(result["text"][:200])               # Markdown 正文
# 取文件：用 request_id + file_name 拼
html = requests.get(
    f"{base}/api/v1/meeting/minutes/file/{request_id}/{result['file_name']}",
    params={"user_id": "1"}, timeout=60,
).content
open("minutes.html", "wb").write(html)
```

订阅事件流（实时进度）：

```python
with requests.get(f"{base}/api/v1/tasks/{job_id}/stream?cursor=0", stream=True, timeout=3600) as resp:
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        event = json.loads(line)          # 每行都有 type / job_id / status / message
        if event["type"] == "chunk":
            print(event["message"], event["text"], end="")   # 增量正文
        elif event["type"] == "done":
            break
```

对应的现成脚本：`minutes_async_submit.py` → `minutes_async_status.py` → `minutes_async_result.py`
→ `minutes_async_stream.py`；地址与 `JOB_ID` 可用环境变量覆盖，无需改文件：

```bash
export AGENTFLOW_BASE_URL=http://127.0.0.1:8003    # 服务器端口与本地不同时
export JOB_ID=job_xxx
python minutes_async_result.py
```

### 3.10 字段演进与版本兼容

本组接口的响应体在 2026-09 统一过一次（四个接口共用 3.2 的快照），之前的结构是：

| 旧结构 | 现在 |
|---|---|
| 提交响应：`{code, message, job_id, request_id, status, run_mode}` | 完整快照；`run_mode` 移到 `GET /api/v1/health` |
| 状态响应：`job_id`/`status`/`phase`/`error`/`token_usage`/`file_name`/时间戳等**平铺**字段 | 统一快照：度量收进 `monitor`，正文相关收进 `text`/`file_name`，其余字段不再返回（运维信息看 Redis / worker 日志） |
| 结果响应：`{type, code, request_id, message, quality_warning, monitor, data:{text,file_name}}` | 统一快照（去掉 `type`，`text`/`file_name` 提到顶层，`quality_warning` 变可选） |
| 错误体：`{"detail": "…"}` | `{"code": …, "message": …}` |
| 结果接口未完成时返回 409 | 返回 200 + 快照（`status` 为 `queued`/`running`/`failed`） |

**客户端自检**：拿到的响应里**没有 `status` 字段**，就说明服务端还是旧版（或客户端按旧结构取值）——
旧结构的正文在 `data.text`、文件名在 `data.file_name`，且结果未完成会返回 409。

---

## 4. 常见问题（FAQ）

**Q1：`result` 为什么不返回文件（HTML）或 `preview_url`？**
接口只返回**数据**，不返回拼好的链接 —— 链接由客户端用返回的 `request_id` + `file_name` 拼
（见 3.5 的四种取文件方式）。HTML 页面版是样式自包含的单文件（实测 `minutes.html` ~10KB，
而 md 正文只有 ~1KB），放进 JSON 会让每次结果查询大一个数量级，所以 JSON 给 Markdown 正文、
文件走下载 / 预览端点。

**Q2：为什么 `text` 是 Markdown，不是那个 `file_name` 指向的文件内容？**
`text` 是**正文文本**，`file_name` 是**页面版文件名**，两者用途不同：JSON 里给文本便于直接展示/复制，
`file_name` 给你去下载排版好的页面。注意 `checklist` 的 `text` 是精简摘要（完整版在 `result.md`/`checklist.html`），
`graph` 没有 md 落盘（3.5 的表）。

**Q3：任务明明失败了，为什么 HTTP 是 200？**
200 表示"服务端收下了/查询成功了"；任务的成败看 `status`（`failed`）+ `message`（原因）。
只有**这次调用本身**出错（参数非法、job 不存在、Redis 挂了）才是 4xx/5xx（3.8 的三态表）。

**Q4：提交后一直 `queued`，是卡住了吗？**
`queue` 模式下要有 `python -m app.worker` 在跑才会执行；没有 worker 就一直是 `queued`。
有 worker 时也可能真在排队（并发满了），看 `LLEN agentflow:queue` 和 `ZCARD agentflow:leases`（3.7）。
`inline` 模式下如果一直是 `queued`，说明进程还在处理排在前面的请求。

**Q5：`attempts` 变 2 了，是重复扣费吗？**
说明这条任务被重试过一次（5xx/异常，或 worker 失联被回收）。重试会**全量重跑**且复用同一个
`request_id`，产物与记忆是覆盖而非新增；次数上限由 `AGENTFLOW_JOB_MAX_ATTEMPTS`（默认 2）控制。
4xx 输入类错误不会重试。

**Q6：`message` 里出现 `requeued(attempt 1)` 是什么意思？**
这条任务被重排过（可重试失败或执行它的 worker 失联），现在回到队列等下一次尝试；
跟着 `/stream` 还会看到新的 `started` 事件。不是错误，是自愈过程。

**Q7：`request_id` 我可以自己指定吗？**
可以 —— 提交时带 `X-Request-Id` 就用你的，否则服务端生成。它会成为产物目录名，
所以同一 `request_id` 重复执行会覆盖同一个目录（重试正是靠这个保证幂等）。

**Q8：产物我先拿到了，之后还能再取吗？**
能。状态、事件流、载荷在 Redis 里保留 7 天（`AGENTFLOW_JOB_TTL_SECONDS`）；
产物文件在 `data/{user_id}/output/{request_id}/` 下长期保留，凭 `request_id` + `file_name` 随时下载/预览。

**Q9：为什么 `/status` 拿不到正文，非要多调一个 `/result`？**
轮询通常几秒一次，正文可能几万字符 —— 分开是为了让轮询轻量。只要结果的话，直接在终态后调一次 `/result` 即可
（或直接用 `/stream` 的 `done` 事件，它和 `/result` 逐字一致）。
