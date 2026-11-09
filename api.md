## 1 URL 

| 端点形态 | 路径 | 方法 | 说明 |
|---|---|---|---|
| 普通 | `/api/agent/v1` | POST | 请求体 `DomainTaskRequest`，返回 TaskResponse |
| 流式 | `/api/agent/v1/stream` | POST | NDJSON 事件流，请求体与普通接口一致（2.5.2） |
| 下载 | `/api/agent/v1/file/{request_id}/{file_name}` | GET | 附件下载，`file_name` 取响应 `data.file_name`|

## 2 请求
### 2.1 请求头

| 头 | 必填 | 适用 | 说明 |
|---|---|---|---|
| `X-Request-Id` | POST 可选 | 普通 / 流式 | 调用方追踪 ID。产物目录以最终 request_id 为名：`data/{user_id}/output/{request_id}/`；下载、结果核对靠它定位。|
| `X-User-Id` | POST 必填 | 普通 / 流式 / 下载| 用户标识。知识库、知识目录、记忆、产物全部按用户隔离在 `data/{user_id}/` 下。|
| `Content-Type` | POST 必填 | 普通 / 流式 | `application/json` |

### 2.2 请求体

普通 / 流式两个 POST 的请求体 = 任务参数（`TaskRequest`）+ `domain` / `task` 两个**必填**定位字段：

```jsonc
{
  "domain": "meeting",              // 必填：meeting / notes
  "task": "minutes",                // 必填：该域的任务线名，如 minutes / actions / graph
  "memory": false ,                 // 是否写入跨会话记忆（notes 图谱/目录与会议记忆相关任务生效）
  "texts": {                        // 三类固定 key 的文本（多段用 \n 拼接）
    "transcript": "",               //   正文：会议转写 / 笔记原文 / 老师重点全文
    "keypoints": "",                //   用户重点（部分任务线的必填溯源材料）
    "notes": ""                     //   用户笔记（部分任务线的必填溯源材料）
  },
  "docs": [],                       // 文件名列表（须已存在于服务端 data/{user_id}/docs/ 或 catalog 目录）
  "extra": {
    "template": "",                 // 输出模板（纪要线可空=自动套用「通用纪要」；其它线可空=不套模板）
    "profile": "",                  // 用户画像选档：空=默认档（客观全员）；user=真人 user.json；见下方说明
    "project": "",                  // 项目绑定（会议记忆按项目聚合时使用；可空）
    "subject": "",                  // 学科（notes 域知识相关任务必填；中文自动转拼音，如 物理→wuli）
    "style": "",                    // 仅 minutes_styles 使用（见 2.6.4）
    "time": ""                      // 任务时间（会议开始/转录完成时刻）；可为空
  }
}
```

### 2.3 响应体

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

### 2.4 三种类型
#### 2.4.1 普通接口（同步 POST）

```
POST /api/agent/v1
```

完整示例（`meeting` + `minutes`）：

```bash
curl -s -X POST http://10.33.240.226:8003/api/agent/v1 \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 1" \
  -H "X-Request-Id: $(uuidgen)" \
  -d '{"domain":"meeting","task":"minutes","memory": false ,"texts":{"transcript":"<会议转写文本>"},"docs":[],"extra":{}}'
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

#### 2.4.2 流式接口（POST NDJSON）

```
POST /api/agent/v1/stream
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
curl -N -X POST http://10.33.240.226:8003/api/agent/v1/stream \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: $(uuidgen)" -H "X-User-Id: 1" \
  -d '{"domain":"meeting","task":"minutes","memory": false ,"texts":{"transcript":"<会议转写文本>"},"docs":[],"extra":{}}'
# 输出示例（每行一个事件，phase 节点名随任务不同）：
# {"type": "phase", "node": "<编排节点名>"}
# {"type": "chunk", "line": "minutes", "title": "会议纪要", "text": "# …"}
# {"type": "done", "code": 0, "request_id": "…", "quality_warning": null, "monitor": {…}, "data": {…}}
```

#### 2.4.3 下载接口（GET 附件）

```
GET /api/agent/v1/file/{request_id}/{file_name}
```

- `request_id` = 普通/流式接口响应里的 `request_id`，`file_name` = 响应里的 `data.file_name`。
- 域与任务名**不需要**：产物目录 `data/{user_id}/output/{request_id}/` 由 `request_id` 唯一确定，
  同一产物既能取 `.html` 页面版，也能取 `result.md` Markdown。

```bash
curl -OJ "http://10.33.240.226:8003/api/agent/v1/file/<request_id>/minutes.html?user_id=1"
```

## 3 接口详情

### 3.1 meeting 下 八个接口
#### 3.1.1 会议纪要 `minutes`

| 形态 | 方法与路径 |
|---|---|
| 普通 / 流式 | `POST /api/agent/v1`、`POST /api/agent/v1/stream`（请求体 `"domain":"meeting","task":"minutes"`） |
| 下载 | `GET /api/agent/v1/file/{request_id}/{file_name}`（ |

- 必填：`texts.transcript`（会议转写文本）。
- `extra.profile`（"user" 默认读取 data/{user_id}下的user.json，生成个人视角纪要）。
- `memory=true` 时：命中历史会议记忆则正文带来源标注并写入会议记忆。
  不传 `extra.project` 时按项目核心名 / 近期唯一项目 / 向量唯一赢家自动归并（标题变体仍应接到同一项目）；绑定时 headline 只作展示名、不参与身份。`time` 非空时作为会议发生时间并生成「第 N 场」；为空则时间未知，不用生成时刻冒充。显式 project 与本场内容无重叠时，响应 `quality_warning` 会提示确认。
- 产物：`minutes.html`（页面版）+ `result.md`。

```jsonc
// 请求
{ "domain": "meeting", "task": "minutes",
  "memory": false, "texts": { "transcript": "<会议转写文本>", "keypoints": "", "notes": "" },
  "docs": [], "extra": { "template": "", "profile": "", "project": "", "subject": "", "style": "", "time": "" } }
// 响应 data
{ "text": "# 会议纪要标题\n…", "file_name": "minutes.html" }
```


#### 3.1.2 待办 `actions`

| 形态 | 方法与路径 |
|---|---|
| 普通 / 流式 | `POST /api/agent/v1`、`POST /api/agent/v1/stream`（请求体 `"domain":"meeting","task":"actions"`） |
| 下载 | `GET /api/agent/v1/file/{request_id}/{file_name}`（无需域与任务名） |

- 必填：`texts.transcript`。从会议中提取待办与分工（含负责人、时间要求）。
- 产物：`actions.html` + `actions.md`。

#### 3.1.3 风险 `risks`

| 形态 | 方法与路径 |
|---|---|
| 普通 / 流式 | `POST /api/agent/v1`、`POST /api/agent/v1/stream`（请求体 `"domain":"meeting","task":"risks"`） |
| 下载 | `GET /api/agent/v1/file/{request_id}/{file_name}`（无需域与任务名） |

- 必填：`texts.transcript`。输出风险条目（描述/严重度/来源/应对/负责人）。
- 产物：`risks.html` + `risks.md`。

#### 3.1.4 多样式纪要 `minutes_styles`

| 形态 | 方法与路径 |
|---|---|
| 普通 / 流式 | `POST /api/agent/v1`、`POST /api/agent/v1/stream`（请求体 `"domain":"meeting","task":"minutes_styles"`） |
| 下载 | `GET /api/agent/v1/file/{request_id}/{file_name}`（无需域与任务名） |

- 必填：`texts.transcript`、`extra.style`（组织模式，取值：`brief` 高管速览 / `topic` 业务归类 /
  `review` 方案权衡 / `retro` 复盘攻坚 / `alignment` 多方对齐）。
- 产物：`minutes_styles.html` + `minutes_styles.md`。

#### 3.1.5 溯源纪要 `minutes_trace`

| 形态 | 方法与路径 |
|---|---|
| 普通 / 流式 | `POST /api/agent/v1`、`POST /api/agent/v1/stream`（请求体 `"domain":"meeting","task":"minutes_trace"`） |
| 下载 | `GET /api/agent/v1/file/{request_id}/{file_name}`（无需域与任务名） |


- 必填：`texts.transcript`（会议事实）+ `texts.keypoints`（用户重点）+ `texts.notes`（用户笔记）。
- 用户重点/笔记作为溯源材料参与对齐；输出结论、风险、行动均带原文溯源钉。
- 产物：`minutes_trace.html`（左正文 / 右证据审阅栏）+ `minutes_trace.md`。

#### 3.1.6 思维导图 `mindmap`

| 形态 | 方法与路径 |
|---|---|
| 普通 / 流式 | `POST /api/agent/v1`、`POST /api/agent/v1/stream`（请求体 `"domain":"meeting","task":"mindmap"`） |
| 下载 | `GET /api/agent/v1/file/{request_id}/{file_name}`（无需域与任务名） |


- 必填：`texts.transcript`（会议事实）。
- 产物：`mindmap.html`（思维导图展示）+ `mindmap.md`(思维导图md形式)。

#### 3.1.7 议题纪要 `agenda_minutes`

| 形态 | 方法与路径 |
|---|---|
| 普通 / 流式 | `POST /api/agent/v1`、`POST /api/agent/v1/stream`（请求体 `"domain":"meeting","task":"agenda_minutes"`） |
| 下载 | `GET /api/agent/v1/file/{request_id}/{file_name}`（无需域与任务名） |


- 必填：`texts.transcript`（会议事实）+ `docs`（议题图片、议题文档）。
- 产物：`agenda_minutes.html`（按议题输出的纪要）+ `agenda_minutes.md`。

#### 3.1.8 共识决策 `consensus_decision` 决策是怎么再沟通中确定的，一致赞同还是有条件的赞同

| 形态 | 方法与路径 |
|---|---|
| 普通 / 流式 | `POST /api/agent/v1`、`POST /api/agent/v1/stream`（请求体 `"domain":"meeting","task":"consensus_decision"`） |
| 下载 | `GET /api/agent/v1/file/{request_id}/{file_name}`（无需域与任务名） |


- 必填：`texts.transcript`（会议事实）。
- 产物：`consensus_decision.html`（共识决策）+ `consensus_decision.md`。

### 3.2 note 下 四个接口

#### 3.2.1 笔记知识图谱 `graph`

| 形态 | 方法与路径 |
|---|---|
| 普通 / 流式 | `POST /api/agent/v1`、`POST /api/agent/v1/stream`（请求体 `"domain":"notes","task":"graph"`） |
| 下载 | `GET /api/agent/v1/file/{request_id}/{file_name}`（无需域与任务名） |

- 必填：`docs`（`data/{user_id}/docs/` 下的笔记 `.txt/.md` 文件；图片会先 OCR + 审校再解析）。
- `extra.subject` 用于按用户+学科做图谱增量合并；`extra.memory=true` 时跨会话增量（新增节点高亮）。
- 产物：交互式 `graph.html`（Cytoscape.js，自包含单文件）；无 md 落盘（正文在 `data.text`）。


#### 3.2.2 资料入库 `library`

| 形态 | 方法与路径 |
|---|---|
| 普通 / 流式 | `POST /api/agent/v1`、`POST /api/agent/v1/stream`（请求体 `"domain":"notes","task":"library"`） |
| 下载 | 不提供（无落盘产物） |

- 必填：`extra.subject`、`docs`（文档/图片全量入库：PPT/PDF/docx/xlsx/txt/图片）。
- 入库后资料进入该用户该学科的知识库（向量索引），供检索与带出处问答。
- **无落盘产物文件**：结果文本与统计只在响应 `data.text` 中返回，`data.file_name` 为空串。

#### 3.2.3 知识目录 `catalog`

| 形态 | 方法与路径 |
|---|---|
| 普通 / 流式 | `POST /api/agent/v1`、`POST /api/agent/v1/stream`（请求体 `"domain":"notes","task":"catalog"`） |
| 下载 | 不提供（`file_name` 指向知识目录 json，不在 output 目录） |

- 必填：`extra.subject`（学科，中文自动转拼音）。
- `docs` 中 `.txt` 会作为老师重点读取；无输入文本时按该学科已入库资料生成/增量更新目录。
- **顺序跟随原文**：章 / 主题 / 知识点按资料原文（文件 → 页码 → 块序）的先后顺序排列，
  不按重要性或主题聚类重排（生成后还有一道确定性保序兜底）。增量更新时，
  本次资料里没有的历史遗留章节排在末尾。
- 产物：目录数据 json 写入 `data/{user_id}/knowledge/catalogs/{学科拼音}/{时间戳}.json`
  （`data.file_name` 返回该文件名）；`data.text` 为目录树 Markdown；同时落盘 `result.md`。

#### 3.2.4 复习清单 `checklist`

| 形态 | 方法与路径 |
|---|---|
| 普通 / 流式 | `POST /api/agent/v1`、`POST /api/agent/v1/stream`（请求体 `"domain":"notes","task":"checklist"`） |

- 必填：`extra.subject`、`docs`——docs 里**必须包含一个 catalog json 文件名，即catalog返回的文件名**
  （catalog 响应 `data.file_name`），可再追加一个老师重点 `.txt`。
- 任务基于指定/最新的知识目录生成复习清单：高优先知识点为完整卡片，低优先为简要条目。
- `data.text` 为**精简摘要**（统计 + 卡片列表，每条只有名称与所属章节，**不含卡片正文**）；
  完整 Markdown 落盘 `result.md`，页面版 `checklist.html`（推荐用预览/下载查看全量）。


#### 剩下三个接口需要按顺序（入库 → 目录 → 清单）

```bash
# 1) 资料入库（docs 在 data/1/docs/ 下）
curl -X POST http://10.33.240.226:8003/api/agent/v1 -H "Content-Type: application/json" \
  -H "X-Request-Id: $(uuidgen)" -H "X-User-Id: 1" \
  -d '{"domain":"notes","task":"library","docs":["<文件名.docx>"],"extra":{"subject":"<学科>"}}'
# 2) 生成/更新知识目录 → 响应 data.file_name 为目录 json 文件名
curl -X POST http://10.33.240.226:8003/api/agent/v1 -H "Content-Type: application/json" \
  -H "X-Request-Id: $(uuidgen)" -H "X-User-Id: 1" \
  -d '{"domain":"notes","task":"catalog","docs":["<老师重点.txt(可选)>"],"extra":{"subject":"<学科>"}}'
# 3) 基于目录生成复习清单（docs 填第 2 步的 file_name）
curl -X POST http://10.33.240.226:8003/api/agent/v1 -H "Content-Type: application/json" \
  -H "X-Request-Id: $(uuidgen)" -H "X-User-Id: 1" \
  -d '{"domain":"notes","task":"checklist","docs":["<catalog文件名.json>"],"extra":{"subject":"<学科>"}}'
