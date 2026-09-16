# AgentFlow HTTP API · notes 域（笔记）

本文是 **notes 域**的完整接口文档，覆盖四条任务线：

| 任务线 | 中文名 | 作用 |
|---|---|---|
| `graph` | 知识图谱 | 从笔记正文（txt/md/图片）抽取概念与关系，产出交互式图谱页 |
| `library` | 资料入库 | 把 PPT / PDF / docx / xlsx / txt / 图片入到该用户该学科的知识库 |
| `catalog` | 知识目录 | 按原文骨架生成/增量更新「章 → 主题 → 知识点」三级目录 |
| `checklist` | 复习清单 | 基于已有目录生成分档复习卡片（含导图、图谱、行动清单） |

结构、字段与约定与总文档 [api.md](api.md) 一致；本文做**自包含**展开，只对接 notes 域也能读完即用。

> 阅读顺序建议：**0 总览**（3 分钟，知道有哪些接口）→ **2 通用约定**（字段/错误/产物）→ **3 任务线详解**
> （写业务代码时照抄）→ **4/5 调用形态**（同步 / 异步）→ **7 FAQ**（踩坑时查）。

---

## 0. 总览

### 0.1 URL 约定

| 形态 | 方法与路径 | 适用 |
|---|---|---|
| 普通（同步） | `POST /api/v1/notes/{task}` | 四条线都有 |
| 流式（同步） | `POST /api/v1/notes/{task}/stream` | 四条线都有 |
| 下载产物 | `GET /api/v1/notes/{task}/file/{request_id}/{file_name}` | 仅 `graph` / `checklist` |
| 浏览器预览 | `GET /api/v1/notes/{task}/preview?request_id=&user_id=` | 仅 `graph` / `checklist` |
| 异步任务（四条线共用） | `POST /api/v1/tasks`、`GET /api/v1/tasks/{job_id}`、`GET /api/v1/tasks/{job_id}/result`、`GET /api/v1/tasks/{job_id}/stream` | `domain=notes` |
| 健康检查 | `GET /api/v1/health` | — |
| 静态产物（可选） | `GET /data/{user_id}/output/{request_id}/{file}` | 挂载 `data/` 时可用 |

`{task}` 只接受 `graph` / `library` / `catalog` / `checklist` 四个值（路由表决定）；其它值返回 404。

### 0.2 任务线矩阵（速查）

| | `graph` | `library` | `catalog` | `checklist` |
|---|---|---|---|---|
| 必填 | `X-User-Id`、`docs` | `X-User-Id`、`extra.subject`、`docs` | `X-User-Id`、`extra.subject` | `X-User-Id`、`extra.subject`、`docs`(含 catalog json) |
| `docs` 语义 | 笔记 `.txt/.md`（图片会先 OCR） | 资料文件/图片（全部入库） | `.txt`=老师重点；其余=资料 | `.json`=目录文件（必含）；`.txt`=老师重点（可选） |
| 可否无输入 | 否 | 否 | **可以**（按已入库资料生成） | 否 |
| 落盘产物 | `graph.html` | 无 | 目录 json（`data/{user}/knowledge/catalogs/…`） | `checklist.html` + `result.md` |
| `data.file_name` | `graph.html` | `""` | 目录 json 文件名 | `checklist.html` |
| 下载/预览端点 | 有 | 无 | 无 | 有 |
| 典型耗时 | 秒~1 分 | 取决于图片数（OCR） | 1~3 分 | 1~3 分 |

### 0.3 鉴权与数据隔离

- **`X-User-Id` 必填**（四条线都要）。所有落盘按用户隔离在 `data/{user_id}/` 下：
  知识库 `knowledge/`、目录 `knowledge/catalogs/`、OCR 合并稿 `ocr/`、产物 `output/`、输入文件 `docs/`。
- **`extra.subject`**（学科，如 `物理` / `wuli`）必填于 `library` / `catalog` / `checklist`；
  服务端统一转拼音（`物理 → wuli`）作为目录名与检索维度，中文/拼音都能传。
- **`X-Request-Id` 可选**：不传则服务端生成 `request_` + 分布式数字 ID。它决定产物目录名
  `data/{user_id}/output/{request_id}/`，**下载/预览要用它**。自传请用安全字符（不含 `/`、`\`、`..`）。

### 0.4 两种调用方式怎么选

| | 同步（第 4 节） | 异步（第 5 节） |
|---|---|---|
| 适合 | 交互式、等待可接受（几秒~3 分） | 长任务、批量、要进度与断线重连 |
| 返回 | 直接给结果（`data.text`） | 立即给 `job_id`，之后轮询状态/取结果/订阅事件 |
| 执行位置 | 请求进程内 | `inline`：API 进程后台；`queue`：独立 worker（见 5.7） |

### 0.5 手把手：三条命令跑通全流程

```bash
# ① 资料入库（图片/文档放进 data/1/docs/ 后按文件名传）
curl -s -X POST http://127.0.0.1:8000/api/v1/notes/library \
  -H 'Content-Type: application/json' -H 'X-User-Id: 1' \
  -d '{"docs":["第一讲.pptx","U202314751_1.jpg"],"extra":{"subject":"物理"}}'

# ② 生成知识目录（记下响应 data.file_name，例如 20260916_075615_986.json）
curl -s -X POST http://127.0.0.1:8000/api/v1/notes/catalog \
  -H 'Content-Type: application/json' -H 'X-User-Id: 1' \
  -d '{"extra":{"subject":"物理"}}'

# ③ 基于该目录生成复习清单（docs 传目录文件名，可再带一个老师重点 .txt）
curl -s -X POST http://127.0.0.1:8000/api/v1/notes/checklist \
  -H 'Content-Type: application/json' -H 'X-User-Id: 1' -H 'X-Request-Id: demo-1' \
  -d '{"docs":["20260916_075615_986.json"],"extra":{"subject":"物理"}}'
# ④ 取页面版产物（浏览器直接打开）
#    http://127.0.0.1:8000/api/v1/notes/checklist/preview?request_id=demo-1&user_id=1
```

---

## 1. 健康检查与静态目录

### `GET /api/v1/health`

不需要任何请求头。用于探活与自检，**返回任务线清单与执行模式**（领域装配失败时降级报告）。

```json
{
  "status": "ok",
  "run_mode": "inline",
  "task_lines": {
    "meeting": ["actions", "consensus_decision", "minutes", "minutes_styles", "minutes_trace", "risks"],
    "notes": ["catalog", "checklist", "graph", "library"]
  }
}
```

| 字段 | 含义 |
|---|---|
| `status` | `ok`；若某域装配失败为 `degraded`（并附 `degraded: ["notes: …"]`） |
| `run_mode` | 异步任务在哪执行：`inline`（API 进程内）/ `queue`（独立 worker）。见 5.7 |
| `task_lines` | 各域**已装配**的任务线（以代码注册为准；缺任务线说明该域装配有问题） |

> 排查顺序：`/health` 看 `task_lines` 是否齐全 → 缺线说明域加载失败（看日志 traceback）；异步任务异常先看 `run_mode` 是否符合预期。

### `GET /data/...`（静态挂载，可选）

服务启动时若存在 `data/` 目录，会挂到 `/data`。于是页面版产物可以**绕过 preview 端点**直接取：

```
http://127.0.0.1:8000/data/1/output/demo-1/checklist.html
```

适合本地调试；生产建议用 preview 端点（它做 `data/{user_id}/output/{request_id}/` 的路径校验，不暴露整棵 `data/` 树）。

---

## 2. 通用约定

### 2.1 请求头

| 头 | 必填 | 说明 |
|---|---|---|
| `X-User-Id` | **是**（四条线） | 用户标识；缺失 → 400 `"{task} 需要 X-User-Id（用户标识：数据目录和知识库按用户隔离）"` |
| `X-Request-Id` | 否 | 调用方追踪 ID，同时是**产物目录名**。缺省服务端生成 `request_…` |
| `Content-Type` | POST 必填 | `application/json` |
| `Accept` | 否 | 流式接口返回 `application/x-ndjson` |

### 2.2 请求体（TaskRequest）

```json
{
  "texts": {"transcript": "", "keypoints": "", "notes": ""},
  "docs": ["文件或图片名", "…"],
  "extra": {"template": "", "profile": "", "project": "", "subject": "", "style": "", "memory": false},
  "time": ""
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `texts` | `dict[str,str]` | 三个固定 key：`transcript` / `keypoints` / `notes`（多段用 `\n` 拼）。**出现未知 key → 422** |
| `docs` | `list[str]` | 文件名（相对 `data/{user_id}/docs/`），语义**按任务线不同**（见 0.2 矩阵与第 3 节） |
| `extra.subject` | `str` | 学科；`library`/`catalog`/`checklist` 必填，中文自动转拼音 |
| `extra.profile` | `str` | 视角模板名（如 `product_manager`、`developer`、`object`）；空 = 客观全员视角。非法名 → 400 |
| `extra.template` | `str` | 模板 `{场景ID}_{模板ID}`；空 = 不套模板。非法 → 400 |
| `extra.memory` | `bool` | 是否启用跨会话增量（`graph` 用：命中历史图谱时只并新增节点并高亮） |
| `extra.project` | `str` | 项目标识（记忆/档案维度，notes 域一般留空） |
| `extra.style` | `str` | 组织模式，**仅 meeting 域的 `minutes_styles` 使用**；notes 域传了会被忽略 |
| `time` | `str` | 任务时间（会议场景）；notes 域一般留空 |

> notes 域的正文来源优先 `docs`：`texts` 里的 `keypoints`/`notes` 在 notes 域基本不用
> （老师重点走 `docs` 的 `.txt`，见 3.3/3.4）。历史客户端若仍带 `domain`/`task` 字段会被静默忽略。

### 2.3 `extra` 字段语义速查

| 字段 | 谁在用 | 不传时 | 传错时 |
|---|---|---|---|
| `subject` | `library` / `catalog` / `checklist` | 400（必填） | 空串=同上；非法字符被转拼音清洗 |
| `profile` | 四条线（视角建模） | 客观全员视角 | 400 `extra.profile 非法：…` |
| `template` | 四条线（模板渲染） | 不套模板 | 400 `extra.template 非法：…（格式为 {场景ID}_{模板ID}）` |
| `memory` | `graph`（跨会话增量） | 不启用 | 非 bool → 422 |
| `project` | 记忆维度 | 空 | — |
| `style` | meeting 的 `minutes_styles` | — | notes 域忽略 |

### 2.4 成功响应体（TaskResponse，同步）

```json
{
  "code": 0,
  "request_id": "request_1_1758000000000_1",
  "message": "success",
  "monitor": {"token_usage": 15234, "cache_hit": 4096, "cost_time": 62.4},
  "data": {"text": "# …（Markdown 正文）", "file_name": "checklist.html"}
}
```

| 字段 | 说明 |
|---|---|
| `code` | `0` = 成功；非 0 时等于 HTTP 状态码（错误路径见 2.5） |
| `request_id` | 本次请求 ID（下载/预览要用）；未传 `X-Request-Id` 时是服务端生成的 |
| `message` | 成功为 `success`；失败为原因（人可读） |
| `monitor.token_usage` / `cache_hit` | 本次消耗的 token / 命中缓存的 token |
| `monitor.cost_time` | 服务端墙钟耗时（秒，保留 1 位） |
| `monitor.catalog` | **仅 `catalog`** 追加的目录体检指标（见 3.3） |
| `data.text` | 产物正文（Markdown）。`catalog` 是目录树；`checklist` 是**精简摘要**；`library` 是入库报告 |
| `data.file_name` | 产物文件名（矩阵见 0.2）。下载/预览时原样回填 |

### 2.5 错误约定

| HTTP | 触发 | 响应体 |
|---|---|---|
| 400 | 缺 `X-User-Id` / 缺 `extra.subject` / 必填项缺失 / `docs` 扩展名不符 / 取值非法 | `{"code":400,"request_id":"…","message":"…"}` |
| 404 | `{task}` 不存在；产物文件不存在；checklist 指定的 catalog json 不存在 | 同上（404） |
| 422 | 请求体不符合模型（`texts` 未知 key、类型错误） | **FastAPI 默认体**：`{"detail":[{"loc":[…],"msg":"…","type":"…"}]}` |
| 500 | 运行期异常（LLM 抖动、依赖不可用等） | `{"code":500,"request_id":"…","message":"服务内部错误：…"}` |
| 503 | 异步接口在 `queue` 模式下 Redis 不可用/入队失败 | `{"code":503,"message":"…"}`（异步错误体**无** `request_id`/`data`/`monitor`） |

- 同步错误体**不带** `monitor`/`data`（省去全 0 与空字段）。
- 400 是**秒回**的：必填校验在触达 LLM 之前完成，缺项会一次列全（`"{task} 缺少必填项：A、B"`）。
- 异步接口失败不抛 HTTP 错误，而是 `status="failed"` + `message`（见 5.4）。

### 2.6 产物与目录布局

```
data/{user_id}/
  docs/                                   ← 输入文件（请求里 docs 只传文件名）
  ocr/{学科拼音}/ocr_{时间戳}.md            ← 图片 OCR 合并稿（library / graph 使用）
  knowledge/
    chromadb/                             ← 向量库（library 写入；catalog/checklist 检索）
    catalogs/{学科拼音}/{时间戳}.json       ← 知识目录（catalog 产物，checklist 的输入）
  output/{request_id}/
    result.md                             ← 文本产物（catalog / checklist；library/graph 无）
    checklist.html / graph.html            ← 页面版产物（下载/预览的目标）
```

- **产物目录名 = `request_id`**：同一 `request_id` 重复调用会**覆盖**同名产物（不是追加）。
- `library` 与 `graph` **不落 `result.md`**；`graph` 只有 `graph.html`。
- `catalog` 的 `data.file_name` 指向 `knowledge/catalogs/…` 的 json，**不在** `output/` 目录里。

### 2.7 流式事件协议（同步 `/stream`）

响应是 NDJSON（每行一个 JSON，`Content-Type: application/x-ndjson`）：

| `type` | 字段 | 说明 |
|---|---|---|
| `phase` | `node` | 图内节点完成（如 `catalog_agent`、`checklist_supervisor`），用于进度提示 |
| `chunk` | `line` / `title` / `text` | 渲染文本增量：`line` 是任务线，`title` 是展示标题，`text` 是本次块 |
| `done` | `code` / `request_id` / `message` / `quality_warning` / `monitor` / `data` | 结束标记，**与同步响应同构**（含 `data.text`、`data.file_name`） |
| `error` | `code` / `message` | 失败；`code` 4xx = 输入类错误（重试无意义），5xx = 可重试 |

```text
{"type":"phase","node":"checklist_agent"}
{"type":"chunk","line":"checklist","title":"复习清单","text":"# 量子力学与统计物理 · 复习清单\n"}
{"type":"done","code":0,"request_id":"demo-1","message":"success","quality_warning":null,
 "monitor":{"token_usage":15234,"cache_hit":4096,"cost_time":62.4},
 "data":{"text":"# …","file_name":"checklist.html"}}
```

> 增量 `chunk` 只对**渲染文本**有意义；结构化结果以 `done.data` 为准。
> `quality_warning` 非空表示输出降级（例如模板门禁未通过），**仍会正常落盘**，建议前端提示"请结合原文核对"。

### 2.8 必填字段矩阵（与代码一致）

| `{task}` | 必填项（缺任一即 400，一次列全） |
|---|---|
| `graph` | `X-User-Id`、`docs`（笔记 `.txt/.md`，或图片） |
| `library` | `X-User-Id`、`extra.subject`、`docs` |
| `catalog` | `X-User-Id`、`extra.subject`（`docs` 可省，见 3.3） |
| `checklist` | `X-User-Id`、`extra.subject`、`docs`（须含一个 `.json`） |

另外：`graph`/`library` 还要求 `texts` 或 `docs` 至少给一个；`catalog`/`checklist` 豁免（无输入也能跑）。

---

## 3. 四条任务线详解

### 3.1 `graph` —— 知识图谱

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/notes/graph` |
| 流式 | `POST /api/v1/notes/graph/stream` |
| 下载 | `GET /api/v1/notes/graph/file/{request_id}/graph.html` |
| 预览 | `GET /api/v1/notes/graph/preview?request_id=&user_id=` |

**入参**：

- `docs`：笔记 `.txt/.md`（读正文）；**图片**（`.jpg/.png…`）会先走「OCR + 整理审校」得到 md 再解析图谱——
  这条路径**不入知识库**（与 `library` 不同），适合"只想看图谱、不想入库"的场景。
- 图片与非图片可混传：图片走 OCR，其余走文本预览，按顺序拼进正文。
- `extra.subject`：按「用户 + 学科」做图谱**增量合并**（复用历史节点）；`extra.memory=true` 时跨会话增量并高亮新节点。
- `extra.profile`：视角模板（如 `product_manager`）会改变抽取侧重；不传为客观全员。

**出参**：

- `data.text`：图谱报告文本（概念清单 + 关系列表）。
- `data.file_name`：`graph.html`（Cytoscape 交互页，样式自包含单文件）。
- **无 `result.md` 落盘**：下载 `result.md` 会 404（用 `graph.html`）。

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/notes/graph \
  -H 'Content-Type: application/json' -H 'X-User-Id: 1' -H 'X-Request-Id: g-1' \
  -d '{"docs":["notes_第1讲.md"],"extra":{"subject":"物理","memory":true}}'
```

### 3.2 `library` —— 资料入库

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/notes/library` |
| 流式 | `POST /api/v1/notes/library/stream` |
| 下载/预览 | **不提供**（无落盘产物、无页面版） |

**入参**：`extra.subject`（必填）、`docs`（PPT / PDF / docx / xlsx / txt / 图片）。

- 图片：先 OCR（并发识别 → 逐图自适应页眉页脚剔除 → 逐页整理 → 审校）合成 `ocr/{学科}.md`，再入库；
  并发识别但**按 `docs` 顺序拼接**，请自行按页码数字序排好（`_10` 会被字符串排序排到 `_2` 前面）。
- 其余文档：解析文本后直接入库。
- 入库粒度：按用户 + 学科分库，写向量索引；后续 `catalog`/`checklist`/检索问答都读它。

**出参**：`data.text` 是入库报告（成功：`入库成功，导入图片 N 张，文档 M 份，{学科}新增知识单元 K 个。`；
失败：`入库失败：…`）。`data.file_name` 为 `""`。

> 图片 OCR 失败**不阻断**非图片入库：报告会写 `图片 OCR 失败，非图片资料已继续入库：<原因>`，
> 且 `image_count` 计 0。原因会带完整堆栈进服务端日志（含 `library ingest ocr failed`）。

### 3.3 `catalog` —— 知识目录

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/notes/catalog` |
| 流式 | `POST /api/v1/notes/catalog/stream` |
| 下载/预览 | **不提供**（`file_name` 指向知识目录 json，不在 `output/` 目录） |

**入参的三种形态**：

| 场景 | 传什么 | 效果 |
|---|---|---|
| 按已入库资料生成 | 只传 `extra.subject` | 从知识库/OCR 合并稿取原文骨架生成目录 |
| 带老师重点 | `docs` 加一个 `.txt` | 该 txt 作为「老师重点」注入（影响 importance/考法，不改顺序） |
| 带新资料 | `docs` 传其它文件（图片会先 OCR） | 资料并入正文参与生成 |

**关键行为**：

- **顺序跟随原文**：章 / 主题 / 知识点按「文件 → 页码 → 块序」排列，**不按重要性重排**；
  生成后还有一道确定性保序兜底（含增量合并后的再保序）。
- **增量更新**：同一 `user + subject` 复用已有目录的节点 ID，`version` 递增，只补新增内容；
  本次资料里没有的历史遗留章节排在末尾。
- **目录层级**取自 OCR 合并稿的标题结构（章 = 一级标题、主题 = 二级、知识点 = 三级）。

**出参**：

- `data.text`：目录树 Markdown（`章 → 主题 → 知识点`）。
- `data.file_name`：目录 json 文件名（如 `20260916_075615_986.json`），落盘在
  `data/{user_id}/knowledge/catalogs/{学科拼音}/{file_name}`；**下一步 `checklist` 要传它**。
- 同时落盘 `output/{request_id}/result.md`（不经下载端点，直接读文件即可）。

**`monitor.catalog`（目录体检，零 LLM，一眼验收）**：

| 指标 | 含义 | 期望 |
|---|---|---|
| `coverage` | 原文骨架被覆盖的比例（`命中/总数`，含"降级为 items""主题被合并"两种合法情况） | 越高越好，低于 100% 看缺口项 |
| `order_violations` | 同级乱序条数 | 0 |
| `restored` / `complemented` | 程序按骨架补回的 / 候选池补缺的节点数 | 正常会有少量 |
| `demoted` / `merged` / `llm_added` | 降级进 items / 合并的节点 / 模型新增（骨架外）节点数 | `llm_added` 应接近 0 |
| `max_kp_per_topic` | 单主题下知识点数上限（层级是否被压平的哨兵） | ≤ 5~7 |
| `relations_ratio` | 有关系的 KP 占比（前置或相关） | > 0 才有图谱骨架 |
| `importance_single_ratio` | `importance` 单值占比（结构信号塌陷哨兵） | < 0.6 |
| `verified_items` / `unverified_items` | 内容可核率（逐字/概述可对上原文的条目） | `unverified` 越低越好 |
| `misplaced_nodes` / `generic_nodes` / `label_items` | 整节串门节点 / 占位名节点 / 被当成条目的标签词 | 都应为 0 |
| `skeleton_kind` | 骨架来源：`md`（原文合并稿）/ `metadata`（知识库回退） | 正常应为 `md` |
| `fake_heading_chunks` | 疑似"句子型伪标题"的入库块数（回归哨兵） | 0 |

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/notes/catalog \
  -H 'Content-Type: application/json' -H 'X-User-Id: 1' \
  -d '{"extra":{"subject":"物理"}}' | python -m json.tool
```

### 3.4 `checklist` —— 复习清单

| 形态 | 方法与路径 |
|---|---|
| 普通 | `POST /api/v1/notes/checklist` |
| 流式 | `POST /api/v1/notes/checklist/stream` |
| 下载 | `GET /api/v1/notes/checklist/file/{request_id}/checklist.html`（也可取 `result.md`） |
| 预览 | `GET /api/v1/notes/checklist/preview?request_id=&user_id=` |

**入参**：`extra.subject`（必填）+ `docs`：

- **必须包含一个 catalog 的 `.json` 文件名**（取 `catalog` 响应的 `data.file_name`）；服务端会到
  `data/{user_id}/knowledge/catalogs/{学科拼音}/` 下找它，找不到 → 404 `catalog 文件不存在：…`。
- 可再追加一个**老师重点 `.txt`**（同样从 `data/{user_id}/docs/` 读）。
- 其它扩展名 → 400 `checklist 的 docs 应为 catalog 文件名（.json）或老师重点文件（.txt）`。

**分档规则**：S（核心）/ A（重点）/ B（简要）/ C（补充）。由目录里的 `importance`、`foundational_level`、
难度、老师重点等综合分按分位切档（**与目录顺序无关**）；分档退化成"全是核心"时会在日志打
`checklist grades:` 便于发现。

**出参**：

- `data.text`：**精简摘要**（档位分布 + 卡片清单：名称 / 星级 / 所属章节），适合列表展示，**不含卡片正文**。
- `data.file_name`：`checklist.html`（完整页面：导图 + 分层知识图谱 + 卡片 + 行动清单）。
- `output/{request_id}/result.md`：完整 Markdown（含卡片正文、易错点、溯源）。

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/notes/checklist \
  -H 'Content-Type: application/json' -H 'X-User-Id: 1' -H 'X-Request-Id: ck-1' \
  -d '{"docs":["20260916_075615_986.json","老师划重点.txt"],"extra":{"subject":"物理"}}'
```

### 3.5 依赖关系与推荐顺序

```
library（入库，可选） ──┐
                        ├─→ catalog（生成目录，得 json 文件名） ──→ checklist（生成清单）
graph（独立，可随时跑） ─┘                                          └─ 需要上面的 json 文件名
```

- `catalog` 不强依赖 `library`：没有入库资料时会用候选池/元数据骨架（质量取决于已入库内容）。
- `checklist` **强依赖** `catalog`：没有目录文件就别调（会 400/404）。
- `graph` 与其它三条线无依赖，可独立使用。

---

## 4. 同步接口

### 4.1 普通接口 `POST /api/v1/notes/{task}`

请求头：`X-User-Id`（必填）、`X-Request-Id`（可选）、`Content-Type: application/json`。

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/notes/checklist \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: 1' \
  -H 'X-Request-Id: demo-1' \
  -d '{"docs":["20260916_075615_986.json"],"extra":{"subject":"物理","profile":"","template":""}}'
```

返回：**2.4 的 TaskResponse**。注意：

- `data.text` 可能很大（catalog 目录树、checklist 摘要都随数据量增长）；只要文件不要正文时，
  建议改用**异步接口 + 状态轮询**，或直接用 `file_name` 下载。
- 同一 `request_id` 重复调用会覆盖产物目录里的同名文件（产物不追加历史版本）。

### 4.2 流式接口 `POST /api/v1/notes/{task}/stream`

请求体与普通接口完全一致，响应是 NDJSON 事件流（协议见 2.7）。

```bash
curl -N -s -X POST http://127.0.0.1:8000/api/v1/notes/checklist/stream \
  -H 'Content-Type: application/json' -H 'X-User-Id: 1' -H 'X-Request-Id: ck-stream-1' \
  -d '{"docs":["20260916_075615_986.json"],"extra":{"subject":"物理"}}'
```

```text
{"type":"phase","node":"checklist_agent"}
{"type":"chunk","line":"checklist","title":"复习清单","text":"…"}
{"type":"done","code":0,"request_id":"ck-stream-1","message":"success","quality_warning":null,
 "monitor":{"token_usage":15234,"cache_hit":4096,"cost_time":62.4},
 "data":{"text":"…","file_name":"checklist.html"}}
```

- 流式接口**不支持断点续传**（同步流）；需要断线重连请用异步接口的事件流（5.5，支持 `cursor`）。
- 参数校验失败（400/404）在**开流之前**返回普通 HTTP 错误，不会先 200 再报错。

### 4.3 下载接口 `GET /api/v1/notes/{task}/file/{request_id}/{file_name}`

只对 `graph` / `checklist` 注册（其它 `{task}` 返回 404 路由不存在）。

| 参数 | 说明 |
|---|---|
| `request_id`（路径） | 生成时的 `X-Request-Id`（或响应里的 `request_id`） |
| `file_name`（路径） | 取响应 `data.file_name`；也可显式取 `result.md` |
| `?user_id=` 或 `X-User-Id` | **必填其一**，都没有 → 400 `缺少 user_id（URL 参数 ?user_id= 或 X-User-Id 请求头）` |

响应：`application/octet-stream` + `Content-Disposition: attachment`（强制下载）。
文件不存在 / 非法路径 → 404 `产物文件不存在：output/{request_id}/{file_name}`。

```bash
# 下载页面版
curl -s -o checklist.html "http://127.0.0.1:8000/api/v1/notes/checklist/file/demo-1/checklist.html?user_id=1"
# 下载完整 Markdown
curl -s -o result.md      "http://127.0.0.1:8000/api/v1/notes/checklist/file/demo-1/result.md?user_id=1"
```

### 4.4 预览接口 `GET /api/v1/notes/{task}/preview?request_id=&user_id=`

返回 `{task}.html`（如 `checklist.html` / `graph.html`），`Content-Type: text/html`，浏览器直接渲染。

```text
http://127.0.0.1:8000/api/v1/notes/checklist/preview?request_id=demo-1&user_id=1
```

- `user_id` 可走 query（浏览器打不了请求头）或 `X-User-Id`；都没有 → 400。
- 只允许定位 `data/{user_id}/output/{request_id}/` 内的文件（路径含 `/`、`..` 一律拒绝）。
- `catalog` / `library` 没有页面版产物 → 它们的 `/preview` 路由不存在（404）。

---

## 5. 异步接口（`domain=notes`）

四个接口**共用同一份任务快照**，差别只在填充程度：提交=零值、状态=实时进度、结果=带正文。

### 5.1 统一响应体（8 字段）

```json
{
  "code": 0,
  "job_id": "job_1_1758000000000_1",
  "request_id": "request_1_1758000000000_2",
  "status": "queued",
  "message": "queued",
  "text": null,
  "file_name": "",
  "monitor": {"token_usage": 0, "cache_hit": 0, "cost_time": 0.0}
}
```

| 字段 | 提交 | 状态 | 结果 | 事件流 |
|---|---|---|---|---|
| `job_id` | ✔ | ✔ | ✔ | ✔（每行都有） |
| `request_id` | ✔ | ✔ | ✔ | ✔（`queued` / `done` 行） |
| `status` | `queued` | `queued`/`running`/`failed` | 同左 | 每行同步反映 |
| `message` | `queued` | `running:<节点>` 或渲染标题 | 失败原因 / `success` | 视 `type` |
| `text` | `null` | `null`（轮询不背大文本） | 成功时给正文 | 仅 `done` 行 |
| `file_name` | `""` | 成功后有值 | ✔ | 仅 `done` 行 |
| `monitor` | 全 0 | 实时 `cost_time` | 最终消耗 | 仅 `done` 行 |
| `quality_warning` | — | — | 降级时出现 | 仅 `done` 行 |

**失败语义**：`status="failed"` + `message` 为具体原因（不再用 409）；HTTP 仍是 200。

### 5.2 提交 `POST /api/v1/tasks`

请求体 = TaskRequest **加两个字段**：`domain`（`notes`）、`task`（`graph`/`library`/`catalog`/`checklist`）。

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/tasks \
  -H 'Content-Type: application/json' -H 'X-User-Id: 1' -H 'X-Request-Id: job-demo-1' \
  -d '{"domain":"notes","task":"checklist",
       "docs":["20260916_075615_986.json"],"extra":{"subject":"物理"}}'
```

- 响应即上面的快照，`status="queued"`（**任务已受理**，不代表开始执行）。
- 校验：`domain` 必须是 `meeting`/`notes`（否则 400）；`task` 必须属于该域（否则 404）；缺 `X-User-Id` → 400。
- `queue` 模式下入队失败会**立即返回 503**（并把 job 标失败，避免留一个永远 queued 的任务）。

### 5.3 查询状态 `GET /api/v1/tasks/{job_id}`

```bash
curl -s "http://127.0.0.1:8000/api/v1/tasks/job_1_1758000000000_1" | python -m json.tool
```

- 不返回正文（`text` 恒为 `null`），轮询体量小。
- `message` 取值：`queued` / `running` / `running:<节点>`（如 `running:checklist_agent`）/
  渲染阶段为展示标题（如 `复习清单`）/ `requeued(attempt N)` / 失败原因 / `success`。
- 任务不存在 → 404 `任务不存在：{job_id}`。

### 5.4 获取结果 `GET /api/v1/tasks/{job_id}/result`

- 成功：快照带 `text` + `file_name`（+ 可能的 `quality_warning`）。
- **未完成 / 失败也返回 200**，靠 `status` 判断（不必处理 409）；失败原因在 `message`。
- 拿到 `request_id` 后即可用第 4.3/4.4 的下载与预览端点取产物。

### 5.5 事件流 `GET /api/v1/tasks/{job_id}/stream?cursor=0`

NDJSON，每行是任务事件（`type` + 统一字段）：

| `type` | 附加字段 | 说明 |
|---|---|---|
| `queued` | `request_id` | 已受理 |
| `started` | `attempt` | worker 开始执行（第 N 次尝试） |
| `phase` | `message="running:<节点>"` | 图内节点完成 |
| `chunk` | `message=标题`、`text=增量` | 渲染文本增量（可边收边显示） |
| `requeued` | `attempt`、`status="queued"` | 可重试失败被重排 |
| `error` | `code`、`message` | 失败事件（4xx 不可重试 / 5xx 可重试） |
| `done` | `text`、`file_name`、`monitor`、`quality_warning` | 结束，**与结果接口逐字一致** |

- **断线重连**：带上次收到的行数 `?cursor=N` 续订，服务端从第 N 条事件继续发。
- 服务端 0.5 秒轮询一次事件表；任务进入终态且无新事件后自动结束流。
- `done` 行先落事件、后翻状态，所以**订阅到 done 就一定拿得到结果**。

### 5.6 状态机 / 重试 / 租约 / 回收

```
submit ──► queued ──► running ──┬──► succeeded
            ▲                   ├──► failed（不可重试，或次数用尽）
            └── requeued(attempt N) ◄┘（可重试且 attempts < AGENTFLOW_JOB_MAX_ATTEMPTS）
```

| 概念 | 默认 | 说明 |
|---|---|---|
| 最大尝试次数 | 2（`AGENTFLOW_JOB_MAX_ATTEMPTS`） | 同一个 job 最多执行几次（含首次） |
| 重试判定 | 4xx 不重试 / 5xx 与未捕获异常重试 | 输入类错误（缺必填、文件不存在）重试无意义 |
| 执行租约 | 60s（`AGENTFLOW_LEASE_SECONDS`） | worker 超过该时长没续期 → 判定失联并回收重排 |
| 续期间隔 | 10s（`AGENTFLOW_HEARTBEAT_SECONDS`） | 需明显小于租约时长 |
| 任务 TTL | 7 天（`AGENTFLOW_JOB_TTL_SECONDS`） | 任务状态与事件流的过期时间 |
| Redis 键 | `agentflow:job:{job_id}`、`…:events`、`agentflow:queue`、`agentflow:leases` | 运维排查用 |

- 回收由**每个 worker** 周期扫描过期租约完成：在跑的任务被收回后按重试策略处理
  （可重试则 `requeued`，次数用尽判 `failed`）。这是"进程被杀后任务卡死"的解法。
- `inline` 模式的任务**不参与租约回收**（避免切到 queue 后被 worker 误判失联而重跑）。

### 5.7 执行模式与部署

| 模式 | 开启方式 | 行为 | 适用 |
|---|---|---|---|
| `inline`（默认） | 无需配置 | 提交后本进程 `BackgroundTasks` 执行；失败即终态（不重试） | 单机、本地调试 |
| `queue` | `.env` 里 `AGENTFLOW_RUN_MODE=queue` | 提交只落 Redis + 入队；由独立进程消费 | 生产、多机、需要重启不丢任务 |

```bash
# worker（可多开、可设并发；全局并发 = 各 worker 并发之和）
python -m app.worker --concurrency 4 --grace 300
#   等价环境变量：AGENTFLOW_WORKER_CONCURRENCY=4 / AGENTFLOW_WORKER_GRACE=300
#   优雅停机：SIGTERM/SIGINT 后不再取新任务，把手上的跑完；超过 grace 由租约兜底重排
```

- `queue` 模式必须能连 Redis（`.env` 的 `REDIS_URL`，默认 `redis://127.0.0.1:6379/0`）；Redis 不可用 → 提交 503、查询 503。
- 多节点扩展：多个 API 实例共用同一 Redis，worker 数量按机器加；任务不会重复执行（出队即加租约）。

### 5.8 完整示例（提交 → 轮询 → 取结果）

```python
import json, time, urllib.request

BASE = "http://127.0.0.1:8000"
HDR = {"Content-Type": "application/json", "X-User-Id": "1", "X-Request-Id": "job-demo-1"}

def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers=HDR)
    return json.loads(urllib.request.urlopen(req).read())

def get(path):
    return json.loads(urllib.request.urlopen(urllib.request.Request(BASE + path, headers=HDR)).read())

job = post("/api/v1/tasks", {
    "domain": "notes", "task": "checklist",
    "docs": ["20260916_075615_986.json"], "extra": {"subject": "物理"},
})
print("job_id:", job["job_id"], "status:", job["status"])

while True:
    snap = get(f"/api/v1/tasks/{job['job_id']}")
    print(snap["status"], "|", snap["message"], "|", snap["monitor"]["cost_time"], "s")
    if snap["status"] in {"succeeded", "failed"}:
        break
    time.sleep(2)

result = get(f"/api/v1/tasks/{job['job_id']}/result")
print("file_name:", result["file_name"], "| text 长度:", len(result.get("text") or ""))
print("预览:", f"{BASE}/api/v1/notes/checklist/preview?request_id={result['request_id']}&user_id=1")
```

---

## 6. 环境变量速查（notes 相关）

| 分类 | 变量 | 默认 | 作用 |
|---|---|---|---|
| 服务/异步 | `REDIS_URL` | `redis://127.0.0.1:6379/0` | 任务状态、事件流、发号器 |
| | `AGENTFLOW_RUN_MODE` | `inline` | `inline` / `queue`（见 5.7） |
| | `AGENTFLOW_JOB_TTL_SECONDS` | 604800 | 任务与事件流 TTL |
| | `AGENTFLOW_JOB_MAX_ATTEMPTS` | 2 | 最大尝试次数 |
| | `AGENTFLOW_LEASE_SECONDS` / `AGENTFLOW_HEARTBEAT_SECONDS` | 60 / 10 | 租约与续期 |
| | `AGENTFLOW_WORKER_CONCURRENCY` / `AGENTFLOW_WORKER_GRACE` | 1 / 300 | worker 并发与停机宽限 |
| OCR | `OCR_ENGINE` | `serverocr`（代码兜底） | `rapidocr` / `paddleocr` / `serverocr`（别名见 `tools/ocr/engines.py`；以 `.env` 为准） |
| | `OCR_PARALLEL` / `LIGHT_OCR_BATCH` / `OCR_ITEM_TIMEOUT` | 4 / 8 / 180 | 并发路数 / 批大小 / 单张超时 |
| | `OCR_PAGE_CHROME` | `1` | 逐图页眉页脚剔除开关（`0` 关闭） |
| | `OCR_PAGE_RECONSTRUCT` / `OCR_PIPELINE_OVERLAP` / `OCR_REVIEW` | 1 / 1 / 1 | 页级整理 / 组间重叠 / 审校轮（`0` 关） |
| | `OCR_COMPLETENESS_FIX` / `OCR_FORMULA_MISS_CHECK` | 1 / 1 | 漏行补写 / 公式缺失判据 |
| | `OCR_UPSCALE`(+`_LONG`/`_MAX_PIXELS`) | 0 | 识别前放大预处理 |
| | `PADDLE_OCR_*` / `SERVER_OCR_*` | — | 各引擎自己的参数（设备/模型池/超时/压缩等） |
| 知识库 | `KNOWLEDGE_EMBEDDING_MODEL` / `KNOWLEDGE_EMBEDDING_BASE_URL` | `BAAI/bge-m3` / 硅基流动 | 向量化 |
| | `KNOWLEDGE_CHUNK_SIZE` / `_OVERLAP` / `KNOWLEDGE_TOP_K` | 500 / 100 / 5 | 切块与检索 |
| | `KNOWLEDGE_MIN_SCORE` / `KNOWLEDGE_HYBRID_SEARCH` | 0.50 / 1 | 检索质量阈值与混合召回 |
| | `KNOWLEDGE_PERSIST_DIR` | `data/knowledge/chromadb` | **单租户**统一库（不设则按用户隔离 `data/{user_id}/knowledge/chromadb`） |
| 目录/清单 | `CATALOG_COMPLEMENT_MAX` | 内部默认 | 候选池补缺上限 |
| | `CATALOG_PLACEHOLDER_RE` / `CATALOG_ITEM_MARKS` / `CATALOG_TITLE_MARKS` / `CATALOG_FINE_GRAIN_MARKS` / `CATALOG_FINE_SUFFIX_MARKS` | 代码默认 | 占位名/条目词/标题词/细粒度词表（形态规则，可覆盖） |
| | `CHECKLIST_LLM_BATCH_SIZE` / `CHECKLIST_LLM_PARALLEL` | 9 / 4 | 清单分批调用：每批卡片数 / 并发批数 |
| | `CHECKLIST_TOKENS_PER_CARD_S` / `_A` | 900 / 700 | 按档位的单卡 token 预算 |
| 模型 | `LLM_BACKEND` | — | `vllm` 时复用 `LLM_VLLM_*`；否则 DeepSeek |
| | `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` / `DEEPSEEK_API_KEY` | — | 默认后端 |
| | `LLM_VLLM_BASE_URL` / `_MODEL` / `_API_KEY` | — | vLLM 后端 |

> 改这些值请改项目根 `.env`（`app/config.py` 首次加载后进程内生效）。

---

## 7. FAQ

**Q1：`library` 的 `data.file_name` 是空串、也没有下载端点？**
入库不产生页面版或 Markdown 产物，结果只在 `data.text`（统计 + 文本）；数据实际进了知识库（向量索引），
供检索问答与 `catalog`/`checklist` 使用。要核对入库结果就看 `data.text` 的统计与文件列表。

**Q2：`catalog` 为什么不能下载/预览？**
它没有页面版产物，且 `data.file_name` 指向**知识目录 json**（在 `knowledge/catalogs/` 下，不在 `output/`）。
要取 json 直接读文件：`data/{user_id}/knowledge/catalogs/{学科拼音}/{file_name}`。
（同一请求的 `output/{request_id}/result.md` 是目录树文本，可直接读文件，不走下载端点。）

**Q3：`graph` 的 `result.md` 下载 404？**
`graph` **无 md 落盘**：正文（图谱报告）在 `data.text`，页面版是交互式 `graph.html`。
要文件就下载/预览 `graph.html`。

**Q4：`checklist` 的 `data.text` 为什么不完整？**
它是**精简摘要**（档位分布 + 卡片清单：名称/星级/所属章节），为的是接口返回轻量。
完整卡片内容在 `result.md` 与 `checklist.html`（用 4.3 下载或 4.4 预览）。

**Q5：`checklist` 的 `docs` 到底填什么？**
**必须**填一个 catalog 的 json 文件名（`catalog` 响应的 `data.file_name`），可再追加一个老师重点 `.txt`。
填别的扩展名 → 400；json 不存在 → 404。没有目录文件就先跑一次 `catalog`。

**Q6：老师重点怎么传？**
`catalog` 与 `checklist` 用 `docs` 里的 `.txt`（服务端从 `data/{user_id}/docs/` 读其内容，作为「老师重点」注入，
影响 importance/考法但不改目录顺序）；`graph` 的 `.txt` 是笔记正文（不是老师重点）。
`texts.keypoints/notes` 在 notes 域一般不用。

**Q7：图片顺序会被打乱吗？**
不会。多张图片并发识别，但**按 `docs` 顺序拼接**（与完成先后无关）。请按**页码数字序**排好再传——
服务端只保证不重排，不会替你排序（按文件名字符串排会把 `_10` 排到 `_2` 前面）。

**Q8：同一学科反复调用 `catalog` 会怎样？**
是**增量更新**：复用已有目录的节点 ID，只补新增内容，`version` 递增；历史遗留章节（本次资料里没有的）排末尾。

**Q9：`graph` 的 `extra.memory=true` 有什么用？**
按「用户 + 学科」跨会话增量：命中历史图谱时只并入新增节点，并在产物里高亮新节点。

**Q10：`catalog` 的顺序为什么和笔记原文一致？我想按重要性排。**
顺序是**有意跟随原文**的（文件 → 页码 → 块序），因为用户对照笔记时顺序不一致会困惑；
重要性不体现在顺序上，而是体现在每个知识点的 `importance` / `foundational_level` 字段
（`checklist` 就是按这些字段分档的，与顺序无关）。

**Q11：`monitor.catalog` 里哪个指标最该盯？**
先看 `coverage`（覆盖率）和 `order_violations`（乱序）；再扫 `generic_nodes`（占位名，应为 0）、
`importance_single_ratio`（>0.6 说明结构信号塌陷）、`max_kp_per_topic`（过大说明层级被压平）。
这几个异常通常意味着上游 OCR 稿的标题层级或入库切块有问题，而不是目录生成本身。

**Q12：异步任务提交后一直 `queued` 不动？**
① `/health` 看 `run_mode`：若是 `queue`，确认 worker 在跑（`python -m app.worker`）；
② 看 Redis 是否连得上（`REDIS_URL`）、队列里是否有积压；
③ 若任务是被回收后重排，`message` 会显示 `requeued(attempt N)`。

**Q13：异步任务失败了，为什么 HTTP 还是 200？**
异步接口用 `status` 表达结果：失败时 `status="failed"`、`message` 是原因（不再用 409）。
只有**提交阶段**的错误（参数、Redis 不可用）才是 4xx/5xx。

**Q14：任务会不会被重复执行？**
不会。出队即登记执行租约（ZSet，score=到期时间），worker 每 10s 续期；
只有租约过期（进程被杀/挂死）才会被**另一个** worker 回收重排——这正是重试语义的来源。

**Q15：`X-Request-Id` 能不能重复用？**
可以，但要清楚后果：产物目录就是 `output/{request_id}/`，重复使用会**覆盖**上次的同名产物，
事件流/下载也会指向同一目录。批量场景建议每个任务一个唯一 ID（或干脆不传，让服务端生成）。

**Q16：`texts` 里传了别的 key 会怎样？**
422（pydantic 校验失败），响应体是 FastAPI 默认形状 `{"detail":[…]}`，与业务错误体（`code`/`message`）不同。

**Q17：`extra.template` / `extra.profile` 写错了会怎样？**
400（`extra.template 非法：…（格式为 {场景ID}_{模板ID}）` / `extra.profile 非法：…`），
不会静默忽略——避免"以为套了模板其实没套"。

**Q18：产物可以直接用 `/data/...` 打开吗？**
服务启动时若存在 `data/` 目录会挂到 `/data`，所以本地调试可以直接
`http://127.0.0.1:8000/data/1/output/{request_id}/checklist.html`。
生产建议走 preview 端点（做路径校验，不暴露整棵 `data/` 树）。

---

## 8. 附录

### 8.1 `data.file_name` 与产物矩阵

| 任务线 | `data.file_name` | `output/{request_id}/` 里有什么 | 下载端点 |
|---|---|---|---|
| `graph` | `graph.html` | `graph.html`（无 md） | ✔ |
| `library` | `""` | 无 | ✗ |
| `catalog` | `{时间戳}.json` | `result.md` | ✗ |
| `checklist` | `checklist.html` | `checklist.html` + `result.md` | ✔ |

### 8.2 事件类型速查

| 场景 | 事件（同步 `/stream`） | 事件（异步 `/tasks/{id}/stream`） |
|---|---|---|
| 受理 | — | `queued` |
| 开始执行 | — | `started`（带 `attempt`） |
| 阶段完成 | `phase` | `phase`（`message=running:<节点>`） |
| 文本增量 | `chunk`（`line`/`title`/`text`） | `chunk`（`message=标题`、`text=增量`） |
| 重排 | — | `requeued`（`attempt`） |
| 失败 | `error`（`code`/`message`） | `error`（`code`/`message`） |
| 结束 | `done`（= 同步响应） | `done`（= 结果接口） |

### 8.3 状态码速查

| 码 | 含义 | 典型原因 |
|---|---|---|
| 200 | 成功 | 同步成功；异步任何状态（含 `failed`） |
| 400 | 输入类错误 | 缺 `X-User-Id`/`extra.subject`/必填项、docs 扩展名不符、取值非法 |
| 404 | 找不到 | `{task}` 不存在、产物文件不存在、catalog json 不存在、job 不存在 |
| 422 | 请求体不合模型 | `texts` 未知 key、字段类型错 |
| 500 | 运行期异常 | LLM/OCR/依赖抖动（异步里表现为 `status=failed` + 可重试） |
| 503 | 依赖不可用 | `queue` 模式下 Redis 不可用 / 入队失败 |

### 8.4 与总文档的分工

- 本文：notes 域四条线的**完整用法**（含每条线的坑与验收指标），可独立使用。
- [api.md](api.md)：全局约定（启动方式、meeting 域六条线、异步接口的原始契约）、以及两域共用的字段定义。
- 自动文档：服务启动后 `http://127.0.0.1:8000/docs`（Swagger UI，可直接试调，注意填 `X-User-Id`）。
