# AgentFlow HTTP API · notes 域（笔记）

本文只覆盖 **notes 域**的四条任务线：`graph`（知识图谱）/ `library`（资料入库）/ `catalog`（知识目录）/
`checklist`（复习清单）。结构、字段与约定与总文档 [API.md](API.md) 完全一致，本文做**自包含**展开，
便于只对接 notes 域的同学使用。

- 启动方式、健康检查、自动文档（`/docs`）：同 API.md；
- meeting 域（minutes / actions / risks / minutes_styles / minutes_trace / consensus_decision）：见 API.md 第 2.6 节；
- 异步任务接口的完整契约：见 API.md 第 3 节；本文给 notes 的用法与示例。

本文档分三块：**健康检查**（第 1 节）→ **notes 任务线接口**（第 2 节，每条线四种形态）→
**异步任务接口**（第 3 节，`domain=notes`）。

---

## 0. 接口总览

### 0.1 URL 约定

| 端点形态 | 路径 | 方法 | 说明 |
|---|---|---|---|
| 普通（同步） | `/api/v1/notes/{task}` | POST | 请求体 TaskRequest，返回 TaskResponse（2.5.1） |
| 流式 | `/api/v1/notes/{task}/stream` | POST | NDJSON 事件流，请求体与普通接口一致（2.5.2） |
| 下载 | `/api/v1/notes/{task}/file/{request_id}/{file_name}` | GET | 附件下载，`file_name` 取响应 `data.file_name`（2.5.3） |
| 预览 | `/api/v1/notes/{task}/preview?request_id=&user_id=` | GET | 页面版 `{task}.html`，`text/html` 直接渲染（2.5.4） |
| 健康检查 | `/api/v1/health` | GET | 服务状态 + 执行模式 + 任务线清单（第 1 节） |
| 异步任务 | `/api/v1/tasks`、`/tasks/{job_id}`、`/tasks/{job_id}/result`、`/tasks/{job_id}/stream` | POST/GET | 与任务线解耦，`domain` 传 `notes`（第 3 节） |
| 静态产物 | `/data/{user_id}/output/{request_id}/{file_name}` | GET | 同源直接访问（无鉴权） |
| 目录数据 | `/data/{user_id}/knowledge/catalogs/{学科拼音}/{file_name}` | GET | catalog 的知识目录 json（2.6.3） |

### 0.2 任务线矩阵

| task | 中文 | 下载 / 预览 | 产物 |
|---|---|---|---|
| `graph` | 知识图谱 | ✅ | `graph.html`（交互式，Cytoscape.js；**无 md 落盘**，正文在 `data.text`） |
| `library` | 资料入库 | ❌ 无落盘产物 | `data.file_name` 为空串；结果只在响应 `data.text` |
| `catalog` | 知识目录 | ❌ 产物不在 output 目录 | `data/{user_id}/knowledge/catalogs/{学科拼音}/{时间戳}.json` + `result.md` |
| `checklist` | 复习清单 | ✅ | `checklist.html` + `result.md`（`data.text` 是精简摘要） |

- notes 域**没有同义 URL**；四条线都提供普通 POST 与流式 POST。
- 只有 `graph` 与 `checklist` 注册下载 / 预览端点（另外两条没有落盘到 output 目录的页面版产物）。
- 领域内还有 `quiz`（自测题）、`review`（笔记审查）两条任务线**未开放 HTTP 接口**，它们只会出现在
  `GET /api/v1/health` 的 `task_lines.notes` 里。
- 路由与清单的唯一声明处是 `app/tasklines.py`。

---

## 1. 健康检查

### `GET /api/v1/health`

无需请求头。返回服务状态、异步任务执行模式与两个域的**当前可用**任务线清单
（领域装配失败时降级报告，不影响其它接口）：

```jsonc
{
  "status": "ok",                                // 或 "degraded"
  "run_mode": "inline",                          // inline / queue：异步任务在哪执行（3.7）
  "task_lines": {
    "meeting": ["actions", "consensus_decision", "mindmap", "minutes", "minutes_styles", "minutes_trace", "risks"],
    "notes":   ["catalog", "checklist", "graph", "library", "quiz", "review"]
  }
  // status=degraded 时追加: "degraded": ["notes: <异常信息>"]
}
```

`task_lines.notes` 列的是**已装配的全部任务线**，比对外接口多：`quiz`、`review` 只在这里出现。

---

## 2. notes 域任务线接口（`/api/v1/notes/{task}`）

### 2.1 请求头

| 头 | 必填 | 适用 | 说明 |
|---|---|---|---|
| `X-User-Id` | POST 必填 | 普通 / 流式 / 下载 / 预览 | 用户标识。知识库、知识目录、记忆、产物全部按用户隔离在 `data/{user_id}/` 下。GET 端点也可用 `?user_id=`（浏览器直接访问时无法带请求头），二者取一，都没有返回 400 |
| `X-Request-Id` | POST 可选 | 普通 / 流式 | 调用方追踪 ID。缺省时服务端生成 `request_` + 分布式数字 ID。产物目录以最终 request_id 为名：`data/{user_id}/output/{request_id}/`；**自传时请用安全字符**（不含 `/`、`\`、`..`）—— 它会直接成为目录名 |
| `Content-Type` | POST 必填 | 普通 / 流式 | `application/json` |

### 2.2 请求体（TaskRequest）

`domain` / `task` 由 URL 表达，请求体对四条线同构：

```jsonc
{
  "time": "",                       // 任务时间；notes 域一般留空
  "texts": {                        // 三类固定 key 的文本（多段用 \n 拼接）
    "transcript": "",               //   notes 域一般走 docs 传文件；老师重点用 docs 的 .txt 传
    "keypoints": "",
    "notes": ""
  },
  "docs": [],                       // 文件名列表（须已存在于服务端 data/{user_id}/docs/ 或 catalog 目录）
  "extra": {
    "template": "",                 // 输出模板（可空=默认无模板）
    "profile": "",                  // 用户画像/职业模板名（可空=客观全员视角）
    "project": "",                  // 项目绑定（会议记忆聚合用；notes 域一般留空）
    "subject": "",                  // 学科：library / catalog / checklist 必填；中文自动转拼音（物理 → wuli）
    "style": "",                    // notes 域不使用
    "memory": false                 // 是否写入跨会话记忆（graph 生效）
  }
}
```

**`docs` 的取用规则（notes 域重点）**：

| 任务线 | `docs` 里的文件怎么用 |
|---|---|
| `graph` | 笔记 `.txt/.md` → 直接解析；**图片** → 走「OCR + 整理 + 审校」流水线生成 Markdown 再解析（该流水线含一次审校 LLM 调用）；其它文档 → 正文预览 |
| `library` | 全量入库：PPT / PDF / docx / xlsx / txt / 图片（**图片会先 OCR 成 Markdown 再入库**） |
| `catalog` | 其它扩展名按资料处理（图片先 OCR）；**`.txt` 视为「老师重点」文本**（不 OCR，直接作为老师重点注入） |
| `checklist` | **必须是**：一个 `.json`（catalog 的知识目录文件，取 catalog 响应 `data.file_name`）+ 可选一个老师重点 `.txt`；其它扩展名返回 400 |

**`catalog` 的结构保证（P2）**：目录的**主题/知识点与顺序来自已入库合并稿解析出的"有序骨架"**，
不是模型自由发明——所以有两条可验收的硬指标：

- **覆盖**：合并稿里每个小节（页块内最浅标题 = 主题，更深 = 知识点）都会出现在目录里；
  模型漏掉的由程序补回（这些节点带 `node_status=program_restore`，一眼可辨）；
  合法例外是"降级"：知识点被写进某个 KP 的 `knowledge_items`（名字仍在）也算覆盖。
- **顺序**：章按其下最早节点排序，章内主题、主题内知识点按原文先后排序；
  `X（续）` 会并入同名主题，例题/易错/小结这类细碎标题不进层级（内容进 items）。

自检命令：`python tools/scripts/check_catalog_coverage.py --user {user_id} --subject {学科拼音}`
（输出覆盖率、同级乱序位置、整节串门与长条目存疑清单，退出码非 0 表示未达标）。

**目录体检指标在响应里**：catalog 的 `monitor.catalog` 会给出 `coverage`（覆盖率）、
`order_violations`（同级乱序处数）、`restored`（模型漏掉、程序按骨架补回的节点数）、
`llm_added`（模型新增的骨架外节点）、`misplaced_nodes`（整节串门）、`unverified_items`
（长条目像引用却全篇找不到依据）。`restored` 偏高说明这轮模型不听话（可重跑或换模型）；
`misplaced/unverified` 偏高说明内容有风险。它们只报告、不删改目录内容。

**图片 OCR 的行为（通用）**：多张图片**并发识别**，结果**按 `docs` 顺序拼接**（顺序可预期，
按页码排好再传即可）；页眉/页脚/页码（校名、地址电话、印刷编号等）会被识别并**剔除**，不会进正文。
判据**逐图自适应**：以该图自身的行高中位数为标尺（印刷校名通常达 1.6 倍以上），结合它是否落在
该图正文范围的上下 12% 边缘带内判断，因此**不要求**页眉每页重复、也不要求各页排版一致。

各线必填项（缺必填秒回 400，不触发模型调用）：

| 任务 | 必填 |
|---|---|
| `graph` | `X-User-Id`、`docs`（笔记文件） |
| `library` | `X-User-Id`、`extra.subject`、`docs` |
| `catalog` | `X-User-Id`、`extra.subject` |
| `checklist` | `X-User-Id`、`extra.subject`、`docs`（catalog 文件名） |

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
    "file_name": "graph.html"       // 产物文件名；无落盘产物（library）为空串
  }
}
```

| 字段 | 说明 |
|---|---|
| `code` | 0=成功；失败时等于 HTTP 状态码（400/404/500） |
| `request_id` | 与请求头一致；**保存它**用于后续下载 / 预览 |
| `monitor` | 本次任务的 token 消耗与耗时 |
| `data.text` | 见各任务线：`graph` 是图谱报告文本；`catalog` 是目录树 Markdown；`checklist` 是**精简摘要**；`library` 是入库统计 |
| `data.file_name` | `graph`→`graph.html`；`checklist`→`checklist.html`；`catalog`→知识目录 json 名；`library`→空串 |

### 2.4 错误约定

| HTTP | 场景 | 响应体 |
|---|---|---|
| 400 | 缺少必填请求头/必填字段/字段取值非法 | `{"code": 400, "request_id": "…", "message": "缺少…"}` |
| 404 | 任务不存在 / 输入文件不存在 / 产物文件不存在 | 同上结构 |
| 422 | 请求体不符合模型（如 texts 未知 key、类型错误） | Pydantic 默认校验错误体 |
| 500 | 任务运行失败 / 未捕获异常 | `{"code": 500, "request_id": "…", "message": "任务运行失败：…"}` |

错误响应一律**不含** `monitor` 与 `data` 字段。
**异步任务接口（第 3 节）的错误体不同**：`{"code": <HTTP 状态码>, "message": "<原因>"}`（见 3.8）。

> 成败怎么看：同步 / 流式接口 `code == 0` 即成功；异步接口要区分"调用成败"与"任务成败"，看 `status`。

### 2.5 四种端点形态

#### 2.5.1 普通接口（同步 POST）

```
POST /api/v1/notes/{task}
```

请求头见 2.1，请求体见 2.2，响应见 2.3。阻塞直到任务结束
（`graph` 解析 + 渲染、`catalog` 目录生成、`library` 入库、`checklist` 出卡都可能在几十秒量级）。
长任务建议用流式（2.5.2）或异步接口（第 3 节）。

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/notes/catalog \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 1" \
  -H "X-Request-Id: $(uuidgen)" \
  -d '{"docs":[],"extra":{"subject":"量子力学"}}'
```

```jsonc
{
  "code": 0,
  "request_id": "3f9a…",
  "message": "success",
  "monitor": {"token_usage": 18234, "cache_hit": 9216, "cost_time": 22.4},
  "data": {"text": "# 量子力学 知识目录\n…", "file_name": "20260915_143001_512.json"}
}
```

#### 2.5.2 流式接口（POST NDJSON）

```
POST /api/v1/notes/{task}/stream
```

请求体与校验规则和普通接口**完全一致**（校验失败仍直接返回 HTTP 错误，不走流）。
响应为 NDJSON（`Content-Type: application/x-ndjson`），每行一个事件：

| 事件 | 字段 | 说明 |
|---|---|---|
| `phase` | `node` | 每进入一个编排节点推送一次（如 生成/审校/渲染） |
| `chunk` | `line` / `title` / `text` | 渲染文本增量，前端按行追加 |
| `done` | `code` / `request_id` / `message` / `quality_warning` / `monitor` / `data` | 最终结果（与普通响应同构，多一个 `quality_warning`） |
| `error` | `code` / `message` | 运行失败；`code` 4xx=输入类错误、5xx=可重试的运行错误 |

```bash
curl -N -X POST http://127.0.0.1:8000/api/v1/notes/catalog/stream \
  -H "Content-Type: application/json" -H "X-User-Id: 1" \
  -d '{"docs":[],"extra":{"subject":"量子力学"}}'
```

#### 2.5.3 下载接口（GET 附件）

```
GET /api/v1/notes/{task}/file/{request_id}/{file_name}
```

- 仅 `graph` 与 `checklist` 提供；`file_name` 取响应 `data.file_name`；
- 返回 `Content-Disposition: attachment`；`user_id` 用 `?user_id=` 或 `X-User-Id`；
- 产物不存在返回 404。

```bash
curl -OJ "http://127.0.0.1:8000/api/v1/notes/checklist/file/<request_id>/checklist.html?user_id=1"
```

#### 2.5.4 预览接口（GET 页面版）

```
GET /api/v1/notes/{task}/preview?request_id=&user_id=
```

- 只允许取产物目录内的 `{task}.html`（服务端校验，不暴露 `/data` 整树）；
- 无 `Content-Disposition` 头 → 浏览器直接渲染，适合人工查看。

```bash
open "http://127.0.0.1:8000/api/v1/notes/checklist/preview?request_id=<request_id>&user_id=1"
```

#### 2.5.5 产物定位速查

| 已拿到 | 位置 / URL |
|---|---|
| `request_id` + `file_name`（graph / checklist） | `/data/{user_id}/output/{request_id}/{file_name}`（静态，浏览器直接打开） |
| graph / checklist 的页面版 | `…/api/v1/notes/{task}/preview?request_id=…&user_id=…` 预览；`…/file/{request_id}/{file_name}` 下载 |
| catalog 的知识目录 json | `data/{user_id}/knowledge/catalogs/{学科拼音}/{file_name}`（`file_name` 为 catalog 响应值） |
| checklist 的全量 Markdown | `result.md`（在产物目录里，随 `file_name` 同目录） |

### 2.6 四条任务线

#### 2.6.1 笔记知识图谱 `graph`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/notes/graph` |
| 流式 | `POST /api/v1/notes/graph/stream` |
| 下载 | `GET /api/v1/notes/graph/file/{request_id}/{file_name}` |
| 预览 | `GET /api/v1/notes/graph/preview?request_id=&user_id=` |

- 必填：`docs`（`data/{user_id}/docs/` 下的笔记 `.txt/.md`；图片会先 OCR + 审校）。
- `extra.subject`：按「用户 + 学科」做图谱**增量合并**；`extra.memory=true` 时跨会话增量（新增节点高亮）。
- 产物：交互式 `graph.html`（Cytoscape.js，样式自包含单文件）；**无 md 落盘**，
  `data.text` 是图谱报告文本；下载 `result.md` 会 404。

#### 2.6.2 资料入库 `library`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/notes/library` |
| 流式 | `POST /api/v1/notes/library/stream` |
| 下载 | 不提供（无落盘产物） |
| 预览 | 不提供（无页面版） |

- 必填：`extra.subject`、`docs`（PPT / PDF / docx / xlsx / txt / 图片；图片先 OCR 成 Markdown）。
- 入库后资料进入该用户该学科的知识库（向量索引），供检索与**带出处**问答；也是 `catalog` 生成目录的数据源。
- **无落盘产物**：结果文本与统计只在响应 `data.text` 中返回，`data.file_name` 为空串。

#### 2.6.3 知识目录 `catalog`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/notes/catalog` |
| 流式 | `POST /api/v1/notes/catalog/stream` |
| 下载 | 不提供（`file_name` 指向知识目录 json，不在 output 目录） |
| 预览 | 不提供（无页面版） |

- 必填：`extra.subject`（学科，中文自动转拼音）。
- `docs` 中 `.txt` 作为**老师重点**读取；其余按资料处理（图片先 OCR）；也允许**完全不带输入**
  （按该学科已入库资料生成/增量更新目录）。
- **顺序跟随原文**：章 / 主题 / 知识点按资料原文（文件 → 页码 → 块序）的先后顺序排列，
  不按重要性或主题聚类重排（生成后还有一道确定性保序兜底）。**增量更新**时，
  本次资料里没有的历史遗留章节排在末尾。
- 产物：目录数据 json 写入 `data/{user_id}/knowledge/catalogs/{学科拼音}/{时间戳}.json`
  （`data.file_name` 返回该文件名，**下一步 checklist 要用它**）；`data.text` 为目录树 Markdown；
  同时落盘 `result.md`。

#### 2.6.4 复习清单 `checklist`

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/notes/checklist` |
| 流式 | `POST /api/v1/notes/checklist/stream` |
| 下载 | `GET /api/v1/notes/checklist/file/{request_id}/{file_name}` |
| 预览 | `GET /api/v1/notes/checklist/preview?request_id=&user_id=` |

- 必填：`extra.subject`、`docs` —— docs 里**必须包含一个 catalog json 文件名**
  （取 catalog 响应 `data.file_name`），可再追加一个老师重点 `.txt`；其它扩展名返回 400。
- 卡片分档：S（核心）/ A（重点）/ B（简要）/ C（补充），由目录里的 `importance`、
  `foundational_level`、老师重点与难度等字段决定（**与目录的排列顺序无关**）。
- `data.text` 是**精简摘要**：统计 + 卡片列表（每条只有名称与所属章节，**不含卡片正文**）；
  完整 Markdown 落盘 `result.md`，页面版 `checklist.html`（推荐用预览/下载看全量）。

#### 2.6.5 顺序依赖示例（入库 → 目录 → 清单）

```bash
# 1) 资料入库（docs 在 data/1/docs/ 下；学科必填）
curl -s -X POST http://127.0.0.1:8000/api/v1/notes/library \
  -H "Content-Type: application/json" -H "X-User-Id: 1" \
  -d '{"docs":["<文件.docx>"],"extra":{"subject":"量子力学"}}'
# 2) 生成/增量更新知识目录 → 记下响应 data.file_name（目录 json 名）
curl -s -X POST http://127.0.0.1:8000/api/v1/notes/catalog \
  -H "Content-Type: application/json" -H "X-User-Id: 1" \
  -d '{"docs":["<老师重点.txt(可选)>"],"extra":{"subject":"量子力学"}}'
# 3) 基于该目录生成复习清单（docs 填第 2 步的 file_name）
curl -s -X POST http://127.0.0.1:8000/api/v1/notes/checklist \
  -H "Content-Type: application/json" -H "X-User-Id: 1" \
  -d '{"docs":["20260915_143001_512.json"],"extra":{"subject":"量子力学"}}'
# 4) 取产物（用各步响应里的 request_id + data.file_name）
curl -OJ "http://127.0.0.1:8000/api/v1/notes/checklist/file/<rid>/checklist.html?user_id=1"
#    浏览器预览：http://127.0.0.1:8000/api/v1/notes/checklist/preview?request_id=<rid>&user_id=1
```

---

## 3. 异步任务接口（`domain=notes`）

与第 2 节同源的一条生产主路径：提交立即返回任务快照，任务后台执行，进度与结果用另外三个接口获取。
**四个接口返回同一份"任务快照"**，任务线由请求体的 `domain` + `task` 指定（本文固定 `domain=notes`）。
完整契约（含 Redis 键、重试与租约语义）见 API.md 第 3 节，这里只列 notes 的用法。

### 3.1 请求体

```jsonc
{
  "domain": "notes",
  "task": "catalog",                // graph / library / catalog / checklist
  "time": "",
  "texts": {"transcript": "", "keypoints": "", "notes": ""},
  "docs": [],
  "extra": {"template": "", "profile": "", "subject": "量子力学", "memory": false}
}
```

除 `domain`/`task` 外，字段语义、`docs` 规则与必填项与 2.2 完全一致。

### 3.2 统一响应体（四个接口共用）

```jsonc
{
  "code": 0,                    // 0=成功；非 0=HTTP 状态码
  "job_id": "job_…",
  "request_id": "request_…",    // 下载产物要用（/file/{request_id}/{file_name}）
  "status": "queued",           // queued / running / succeeded / failed
  "message": "queued",          // 阶段名 或 失败原因（人可读）
  "text": null,                 // 产物正文：仅结果接口有值
  "file_name": "",              // 产物文件名
  "monitor": {"token_usage": 0, "cache_hit": 0, "cost_time": 0.0}
}
```

| 接口 | `status` | `text` | `file_name` |
|---|---|---|---|
| 提交（3.3） | `queued` | `null` | `""` |
| 状态（3.4） | 实时 | 恒 `null` | 成功后填 |
| 结果（3.5） | 成功 `succeeded`；未完成或失败原样返回 | 成功时给正文 | 同上 |
| 事件流（3.6） | 每行实时 | 仅 `chunk`（增量）与 `done` | `done` 时 |

`message` 在失败时是**错误原因**，其余时候是阶段（`running:catalog`）或状态描述
（`queued` / `success` / `requeued(attempt N)`）。可选的 `quality_warning` 仅结果接口在非空时出现。

### 3.3 提交任务 `POST /api/v1/tasks`

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/tasks \
  -H "Content-Type: application/json" -H "X-User-Id: 1" \
  -d '{"domain":"notes","task":"catalog","docs":[],"extra":{"subject":"量子力学"}}'
```

响应即快照（`status=queued`，`monitor` 零值）。`run_mode=queue` 时必须有
`python -m app.worker` 在跑，否则任务会停在 `queued`（`LLEN agentflow:queue` 能看到）；
`run_mode` 从 `GET /api/v1/health` 读。

### 3.4 查询状态 `GET /api/v1/tasks/{job_id}`

轮询接口，返回同一份快照，`text` 恒为 `null`。建议间隔 1~2 秒。

### 3.5 获取结果 `GET /api/v1/tasks/{job_id}/result`

成功的任务带上 `text`（notes 域：`graph` 图谱报告 / `catalog` 目录树 / `checklist` 精简摘要 /
`library` 入库统计）与 `file_name`。未完成或失败**同样返回 200 + 快照**
（`status` 为 `queued`/`running`/`failed`，原因在 `message`），不用处理 409；只有 job 不存在返回 404。

### 3.6 事件流 `GET /api/v1/tasks/{job_id}/stream`

NDJSON，每行恒定带 `type` + `job_id` + `status` + `message`；`chunk` 带增量 `text`；
`done` 与结果接口逐字一致。支持 `?cursor=N` 断线续读。

### 3.7 执行模式与队列语义

- `inline`（缺省）：API 进程内执行，起一个 uvicorn 就能用；失败即终态、无重试。
- `queue`：入库 / 目录 / 清单这类长任务建议用队列模式 —— 并发上限、失败重试、重启不丢任务；
  全局并发看 `ZCARD agentflow:leases`，积压看 `LLEN agentflow:queue`。

### 3.8 错误体

```jsonc
{"code": 404, "message": "任务不存在：job_xxx"}
```

| HTTP | `message` 示例 | 场景 |
|---|---|---|
| 400 | `domain 仅支持 meeting / notes` / `缺少 X-User-Id` | 域非法 / 缺用户标识 |
| 404 | `任务线不存在：no_such` / `notes 不支持任务线：minutes` / `任务不存在：job_…` | 任务线非法 / job 不存在 |
| 422 | （Pydantic 默认校验错误体） | 请求体不合模型 |
| 503 | `Redis 不可用（<url>）：…` / `任务入队失败：…` | Redis 不可用 |

> 注意区分：**调用失败** = HTTP 状态码 + `{code, message}`；**任务失败** = 200 + 快照里的
> `status=failed` + `message=失败原因`。缺必填项在异步接口里表现为"先 `queued`、随后 `failed`"。

### 3.9 调用顺序示例

```bash
# 1) 提交（记下 job_id）
curl -s -X POST http://127.0.0.1:8000/api/v1/tasks -H "Content-Type: application/json" \
  -H "X-User-Id: 1" \
  -d '{"domain":"notes","task":"catalog","docs":["<老师重点.txt(可选)>"],"extra":{"subject":"量子力学"}}'
# 2) 轮询状态
curl -s http://127.0.0.1:8000/api/v1/tasks/<job_id>
# 3) 取结果（含 data.text 与 file_name）
curl -s http://127.0.0.1:8000/api/v1/tasks/<job_id>/result
# 4) 订阅事件流
curl -N "http://127.0.0.1:8000/api/v1/tasks/<job_id>/stream?cursor=0"
```

---

## 4. 常见问题（FAQ）

**Q1：catalog 的顺序为什么和笔记原文一致？我想按重要性排。**
目录顺序是**有意跟随原文**的（章/主题/知识点按"文件 → 页码 → 块序"），因为用户对照笔记时
顺序不一致会困惑；重要性不体现在顺序上，而是体现在每个知识点的 `importance` /
`foundational_level` 字段上（`checklist` 就是按这些字段决定卡片分档与优先级的，与顺序无关）。
增量更新时，本次资料里没有的历史遗留章节排在末尾。

**Q2：catalog 为什么不能下载 / 预览？**
它没有页面版产物，且 `data.file_name` 指向**知识目录 json**（不在 output 目录），
所以不走下载端点。要取 json 直接读：`data/{user_id}/knowledge/catalogs/{学科拼音}/{file_name}`。

**Q3：`library` 为什么 `file_name` 是空串、也没有下载端点？**
入库不产生页面版或 Markdown 产物，结果只在响应 `data.text`（统计 + 文本）；数据实际进了知识库
（向量索引），供检索与带出处问答。

**Q4：`graph` 的 `result.md` 下载 404？**
`graph` **无 md 落盘**：正文（图谱报告）在 `data.text`，页面版是交互式 `graph.html`。
要文件就下载/预览 `graph.html`。

**Q5：`checklist` 的 `data.text` 为什么不完整？**
它是**精简摘要**（统计 + 卡片列表，只有名称与所属章节），为的是接口返回轻量；
完整卡片内容在 `result.md` 与 `checklist.html` 里，用 2.5.3/2.5.4 取。

**Q6：`checklist` 的 `docs` 到底填什么？**
**必须**填一个 catalog 的 json 文件名（`catalog` 响应的 `data.file_name`），可再追加一个老师重点
`.txt`。填别的扩展名会 400。没有目录文件就先跑一次 `catalog`。

**Q7：老师重点怎么传？**
`catalog` 与 `checklist` 用 `docs` 里的 `.txt`（服务端从 `data/{user_id}/docs/` 读取其内容作为老师重点）；
`graph` 的 `.txt` 是笔记正文（不是老师重点）。`texts` 里的 `keypoints/notes` 在 notes 域一般不用。

**Q8：图片顺序会被打乱吗？**
不会。多张图片并发识别，但**按 `docs` 的顺序拼接**（与完成先后无关）。
请按**页码数字序**排好再传 —— 服务端只保证不重排，不会替你按页码排序
（按文件名字符串排会把 `_10` 排到 `_2` 前面）。

**Q9：同一学科反复调用 `catalog` 会怎样？**
是**增量更新**：复用已有目录的节点 ID，只补新增内容；`version` 递增。历史遗留章节（本次资料里没有的）
排在末尾。

**Q10：`graph` 的 `extra.memory=true` 有什么用？**
按「用户 + 学科」跨会话增量：命中历史图谱时只并入新增节点，并在产物里高亮新节点。
