# AgentFlow HTTP 接口文档（完整版）

FastAPI 后端接口。所有接口走 `/api/v1`，一次请求对应一条任务线，**共用同一份请求体结构**。

- 启动：`uvicorn app.main:app --host 0.0.0.0 --port 8000`（或 `python -m app.main`）
- 交互文档：`http://127.0.0.1:8000/docs`（Swagger UI）/ `/redoc`
- OpenAPI：`/openapi.json`（可导入 Apifox/Postman）

---

## 一、接口总览（10 个）

| # | 域 | 接口 | 方法 | 路径 | 用途 |
|---|---|---|---|---|---|
| 1 | meeting | minutes | POST | `/api/v1/meeting/minutes` | 会议纪要提取（根据会议转写文本生成结构化纪要） |
| 2 | meeting | actions | POST | `/api/v1/meeting/actions` | 待办提取（抽出带负责人和时限的待办清单） |
| 3 | meeting | risks | POST | `/api/v1/meeting/risks` | 风险识别（抽出风险条目，标注严重度与应对） |
| 4 | meeting | minutes_styles | POST | `/api/v1/meeting/minutes_styles` | 多样式纪要（按组织模式重写纪要：时间线/总分/因果等） |
| 5 | meeting | minutes_trace | POST | `/api/v1/meeting/minutes_trace` | 溯源纪要（纪要段落回指原文 + 用户重点/笔记挂载） |
| 6 | notes | graph | POST | `/api/v1/notes/graph` | 知识图谱（笔记概念抽取 → 交互 HTML/学习地图） |
| 7 | notes | library | POST | `/api/v1/notes/library` | 资料入库（图片 OCR / 文档解析 → 知识库） |
| 8 | notes | catalog | POST | `/api/v1/notes/catalog` | 知识目录（按已入库资料生成知识目录） |
| 9 | notes | checklist | POST | `/api/v1/notes/checklist` | 复习清单（按知识目录与重点生成复习清单） |
| 10 | - | health | GET | `/api/v1/health` | 健康检查 + 任务线清单 |

> 接口名与内部任务线名保持一致，例如 `minutes`、`actions`、`risks`、`minutes_styles`、`graph`。调用方只需要使用上表中的接口路径与任务名。
>
> **流式版本**：每个业务接口都有 `/stream` 后缀的流式端点（NDJSON 事件流，实时感知任务进度），请求体与同步接口一致，见第十章。

---

## 二、请求头（HTTP Headers）

| Header | 必填 | 类型 | 说明 |
|---|---|---|---|
| `Content-Type` | 是 | string | 固定 `application/json` |
| `X-User-Id` | **是** | string | 用户标识。**所有接口必填**。决定数据目录 `data/{user_id}/`；`minutes`/`minutes_styles`/`graph` 关联跨会话记忆（落盘 `data/{user_id}/memory/`）；`library`/`catalog`/`checklist` 按用户隔离知识库 |
| `X-Request-Id` | **是** | string | 调用方追踪 ID，**建议用 UUID**（如 `550e8400-e29b-41d4-a716-446655440000`）。透传到响应 `request_id`；产物目录 `data/{user_id}/output/{request_id}/` 以它为名。缺了返回 400 |
| `Authorization` | 否 | string | `Bearer <token>`，预留认证，本期不校验 |

---

## 三、请求体总览（一份通用 JSON）

```json
{
  "domain": "meeting",
  "task": "minutes",
  "texts": {
    "transcript": "会议记录全文……",
    "teacher_focus": "老师划重点……",
    "keypoints": "用户关键点……",
    "notes": "用户笔记……"
  },
  "docs": ["photo_1.jpg", "board.png", "spec.pdf"],
  "extra": {
    "template": "meeting_minutes_team_meeting",
    "profile": "developer",
    "project": "P-1001",
    "subject": "数学",
    "style": "time"
  }
}
```

> 所有字段均可省略/置空；`X-User-Id` 除外（在请求头）。

---

## 四、请求字段详解

### 4.1 顶层字段

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `domain` | string | 否 | 不传 | 冗余校验字段：填了必须与 URL 路径一致（meeting/notes），否则返回 400 |
| `task` | string | 否 | 不传 | 冗余校验字段：填了必须与 URL 路径一致（如 minutes），否则返回 400 |
| `texts` | object | 否* | `{}` | 文本对象（四类 key，见 4.2）。`catalog`/`checklist` 可整体缺省（基于已有知识库生成） |
| `docs` | array | 否* | `[]` | 文件名列表（图片/文档/笔记，.png/.jpg/.jpeg/.txt/.md/.pdf/.docx/.pptx/.xlsx/.json），服务端从 `data/{user_id}/docs/` 取，按扩展名分派（图片 OCR、文本直读、文档解析、json=catalog） |
| `extra` | object | 否 | `{}` | 任务差异参数，见 4.4 |

\* `texts`/`docs` 至少提供一个（`catalog` 除外，可完全依赖已入库资料；`checklist` 需要 `docs` 传 catalog 文件名，见 6.9）。

### 4.2 `texts` 对象（四个固定 key）

`texts` 是对象，key 固定四选一，值为字符串（多段用 `\n` 拼接）；出现未知 key → 422。

| key | 中文名 | 语义 | 用途 |
|---|---|---|---|
| `transcript` | 会议转写文本 | 会议记录 / 笔记原文，主输入 | 所有任务的主文本来源 |
| `teacher_focus` | 老师重点文本 | 老师划重点内容，主输入 | `catalog`/`checklist` 传老师划重点 |
| `keypoints` | 用户重点文本 | 用户关键点 | `minutes_trace` 溯源材料（**必填**） |
| `notes` | 用户笔记文本 | 用户笔记 | `minutes_trace` 溯源材料（**必填**） |

- `transcript` 与 `teacher_focus` 都算**主输入**，按 `transcript` → `teacher_focus` 顺序拼成主文本（各自内部多段用 `\n`）。
- `keypoints`/`notes` 是 `minutes_trace` 的**溯源材料**，不并入主文本；**`minutes_trace` 必填二者**（缺任一返回 400）。
- 未提供的 key 省略即可（缺省为空）。
- 未知 key → 422。

### 4.3 `docs[]`（按扩展名分派）

- 元素为**文件名**（带扩展名），不带路径。
- 服务端查找链：`data/{user_id}/docs/{name}` → `data/docs/{name}`（公共兜底）。
- 图片走 OCR（引擎由 `.env` 的 `OCR_ENGINE` 决定），OCR 文本并入主输入。
- 文档：`.txt/.md` 直读；`.pdf/.pptx/.docx/.xlsx` 走知识库解析；`library` 任务直接入库。
- **`graph` 必填 `docs`**（笔记 `.txt/.md` 文件，缺了返回 400）。
- 文件不存在 → 404；文件名含路径分隔符/`..` → 400。

### 4.4 `extra` 对象字段

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `template` | string | `""` | 输出模板，见 4.5；**空 = 不套模板**，用任务默认输出 |
| `profile` | string | `""` | 视角，见 4.6；**空 = 客观全员** |
| `project` | string | `""` | 会议关联项目 ID（minutes/minutes_styles 开项目记忆） |
| `subject` | string | `""` | 学科/课程名（library 可选；catalog/checklist **必填**；graph **记忆增量必需**，见 6.6） |
| `style` | string | `""` | 多样式纪要组织模式，见 4.7；仅 `minutes_styles` 生效，其余任务忽略；**`minutes_styles` 必填**（缺了返回 400） |

非法 `template`/`profile`/`style` → 400。

### 4.5 `extra.template` 可填值（29 个，格式 `{场景ID}_{模板ID}`）

**会议（meeting_minutes）**

| template 值 | 中文名 |
|---|---|
| `meeting_minutes_team_meeting` | 团队例会 |
| `meeting_minutes_project_progress` | 项目进度会 |
| `meeting_minutes_decision_review` | 决策评审会 |
| `meeting_minutes_workshop_session` | 工作研讨会 |
| `meeting_minutes_retrospective_session` | 总结复盘会 |
| `meeting_minutes_exchange_forum` | 沟通交流会 |

**学习（study_notes）**

| template 值 | 中文名 |
|---|---|
| `study_notes_class_transcript` | 课堂记录 |
| `study_notes_special_lecture` | 专题讲座 |
| `study_notes_group_seminar` | 小组讨论 |
| `study_notes_knowledge_memo` | 知识笔记 |
| `study_notes_debate_forum` | 辩论会 |

**访谈（dialogue_interview）**

| template 值 | 中文名 |
|---|---|
| `dialogue_interview_research_dialogue` | 调研访谈 |
| `dialogue_interview_interview_transcript` | 采访记录 |

**面试（job_interview）**

| template 值 | 中文名 |
|---|---|
| `job_interview_hiring_report` | 面试报告 |
| `job_interview_interview_debrief` | 面试复盘 |

**医疗问诊（medical_consultation）**

| template 值 | 中文名 |
|---|---|
| `medical_consultation_clinical_advisory` | 就医咨询 |
| `medical_consultation_psychological_session` | 心理咨询 |

**法律沟通（legal_consultation）**

| template 值 | 中文名 |
|---|---|
| `legal_consultation_legal_advisory` | 法律咨询 |
| `legal_consultation_court_transcript` | 庭审记录 |
| `legal_consultation_contract_vetting` | 合同审核 |

**新闻发布（press_conference）**

| template 值 | 中文名 |
|---|---|
| `press_conference_media_briefing` | 新闻发布 |
| `press_conference_product_launch` | 产品发布 |
| `press_conference_government_bulletin` | 政府报告 |
| `press_conference_media_qa_session` | 媒体问答 |

**日常记录（daily_journal）**

| template 值 | 中文名 |
|---|---|
| `daily_journal_general_minutes` | 通用纪要 |
| `daily_journal_personal_memo` | 个人备忘 |
| `daily_journal_conversation_transcript` | 对话记录 |
| `daily_journal_site_visit_tour` | 参观游览 |
| `daily_journal_home_school_liaison` | 家校沟通 |

### 4.6 `extra.profile` 可填值（7 个）

| profile 值 | 视角 |
|---|---|
| `""`（缺省/空） | 客观全员（默认） |
| `algorithm_engineer` | 算法人员 |
| `client_manager` | 客户经理 |
| `developer` | 开发人员 |
| `product_manager` | 产品经理 |
| `project_manager` | 项目经理 |
| `tester` | 测试人员 |

### 4.7 `extra.style` 可填值（5 个，仅 minutes_styles）

| style 值 | 组织模式 |
|---|---|
| `time` | 时间线（叙事节奏） |
| `logic` | 逻辑总分（归纳分类） |
| `causal` | 因果推导（风险与动因） |
| `party` | 主体责权（立场与博弈） |
| `urgency` | 决策时效（执行倒计时） |

---

## 五、返回字段解析（6 个字段）

**成功示例**：

```json
{
  "code": 0,
  "request_id": "req-0001",
  "message": "ok",
  "monitor": {
    "token_usage": 8231,
    "cache_hit": 1560,
    "cost_time": 12.5
  },
  "data": {
    "text": "# 项目例会：后端开发完成与上线测试环境安排\n\n本次会议……",
    "file_name": ""
  }
}
```

**失败示例**：

```json
{
  "code": 404,
  "request_id": "req-0001",
  "message": "本地文件不存在：docs/photo_1.jpg",
  "monitor": {
    "token_usage": 0,
    "cache_hit": 0,
    "cost_time": 0
  },
  "data": {
    "text": null,
    "file_name": ""
  }
}
```

### 5.1 字段说明

| 字段 | 类型 | 成功 | 失败 |
|---|---|---|---|
| `code` | int | `0` | HTTP 状态码（见 5.2） |
| `request_id` | string | 与请求头 `X-Request-Id` 一致 | 同左 |
| `message` | string | `ok` | 错误原因（人类可读） |
| `monitor.token_usage` | int | 本次任务 LLM token 总消耗（prompt+completion） | `0` |
| `monitor.cache_hit` | int | 本次任务缓存命中的 token 数（服务端上下文缓存） | `0` |
| `monitor.cost_time` | float | 本次任务耗时（秒） | `0` |
| `data.text` | string/null | **该任务生成的 Markdown 文本**（含记忆溯源标准链接；`graph` 为学习地图；`library` 为入库报告） | `null` |
| `data.file_name` | string | 产物文件名：`catalog` 接口返回目录文件名（如 `20260827_223933_068.json`，存于 `data/{user_id}/knowledge/catalogs/{subject拼音}/`）；`checklist` 接口返回本次运行 HTML 文件名（`result.html`，存于 `data/{user_id}/output/{request_id}/`）；其他接口为空串 | `""` |

### 5.2 `code` 语义（与 HTTP 状态码一致）

| code | 含义 |
|---|---|
| `0` | 成功 |
| `400` | 请求参数错误：请求体非法、输入缺失、`extra` 非法、缺必填字段、`domain`/`task` 与路径不一致 |
| `401` | 未认证（预留） |
| `403` | 无权限（预留） |
| `404` | 资源不存在：任务线不存在、本地文件不存在 |
| `500` | 任务运行失败：LLM 调用 / 管线 / 超时 / 文件解析异常 |
| `503` | 服务不可用 |

### 5.3 `data.text`（Markdown 文本）内容说明

- **普通任务**：任务生成的最终文本。第一行 `# 标题` 为 LLM 根据会议内容总结的主题标题（如 `# 小艺慧记Agent开发进展阶段复盘`），不再是视角标题。
- **记忆溯源**（minutes/minutes_styles 命中历史记忆时）：正文命中处为**标准 Markdown 链接** `[被溯源文本](#memory-N)`，文末附 `## 历史记忆引用` 附录（`#### 溯源 memory-N` 标题 + 历史原句/时间/场次/来源会议）。前端渲染：markdown-it 默认配置即可，配 `markdown-it-anchor` 并 `slugify: (s) => s.replace(/^溯源\s+/, "")` 可实现点击跳转。
- **graph**：学习地图（按主题分组的文本学习路径）。
- **library**：入库报告（本次入库对知识库的改变：新增单元、来源文件等），**不是入库文件内容**。
- 长度：纪要已按 prompt 约束收紧（目标约为原文 1/3，去重），短会议仅 1–2 段。

---

## 六、各接口详解

### 6.1 `POST /api/v1/meeting/minutes` —— 纪要提取

- **用途**：把会议转写文本整理成结构化会议纪要（议题、结论、摘要、待办/风险概述）。默认客观全员视角；填 `X-User-Id` 关联历史记忆，命中历史会议会在对应内容标注溯源。
- **输入**：`texts`（transcript 必填）+ 可选 `docs`
- **生效的 extra**：`template` / `profile` / `project`

```json
{
  "texts": {
    "transcript": "会议记录全文……"
  },
  "extra": { "template": "meeting_minutes_team_meeting", "profile": "developer", "project": "P-1001" }
}
```

### 6.2 `POST /api/v1/meeting/actions` —— 待办提取

- **用途**：抽出带负责人和截止时间的待办清单，只认明确分工，不把口头讨论当已分派任务。
- **输入**：`texts`（transcript 必填）
- **生效的 extra**：`template` / `profile`

```json
{
  "texts": {
    "transcript": "会议记录全文……"
  }
}
```

### 6.3 `POST /api/v1/meeting/risks` —— 风险识别

- **用途**：把会上提到的风险抽成条目，标注严重度、责任人与应对提示，只依据本场原文。
- **输入**：`texts`（transcript 必填）
- **生效的 extra**：`template` / `profile`

### 6.4 `POST /api/v1/meeting/minutes_styles` —— 多样式纪要

- **用途**：同一场会按指定组织模式重写纪要（时间线/总分/因果/主体责权/决策时效）。
- **输入**：`texts`（transcript 必填）+ `extra.style`（**必填**，缺了返回 400）
- **生效的 extra**：`template` / `profile` / `project` / **`style`（必填）**

```json
{
  "texts": {
    "transcript": "会议记录全文……"
  },
  "extra": { "style": "causal" }
}
```

### 6.5 `POST /api/v1/meeting/minutes_trace` —— 溯源纪要

- **用途**：生成段落回指会议原文的溯源纪要，并叠上用户关键点与笔记（一条关键点可反复挂钉）。
- **输入**：`texts`（transcript **必填** + **`keypoints` / `notes` 必填**，缺任一返回 400）
- **生效的 extra**：`profile` / `project`

```json
{
  "texts": {
    "transcript": "会议记录全文……",
    "keypoints": "我关注的关键点……",
    "notes": "我的笔记……"
  }
}
```

### 6.6 `POST /api/v1/notes/graph` —— 知识图谱

- **用途**：把笔记概念抽成知识图谱（节点带定义/出处/关系），产出学习地图文本；交互 HTML 落盘。
- **输入**：`docs`（**必填**，笔记 `.txt/.md` 文件，从 `data/{user_id}/docs/` 取）
- **生效的 extra**：`template` / `profile` / `project` / **`subject`（记忆增量必需）**
- **记忆增量**：传 `X-User-Id` + **`extra.subject`（学科名）** 时，按学科绑定跨会话记忆档案（`data/{user_id}/memory/records/notes/projects/{学科}/`）——下次同学科调用会注入已积累图谱，同名节点/边合并，**新增节点在学习地图标"（新增）"**，交互 HTML 中新增橙色高亮、历史暗淡显示。**不传 `subject` 则每次都是独立单次运行**（不建档、不注入、无增量）。

```json
{
  "docs": ["gaoshu_limit_notes.txt"],
  "extra": { "subject": "数学" }
}
```

### 6.7 `POST /api/v1/notes/library` —— 资料入库

- **用途**：把图片（OCR）和文档（解析）入库到知识库，产出信息熵报告。图片 OCR 并行（4 路），合并为 md 后入库。
- **输入**：`docs`（必填，文件或图片）+ `texts`（可配）
- **生效的 extra**：`subject`（可选，建议填以按学科分类）
- **耗时**：多图 OCR 3–10 分钟，属正常。

```json
{
  "docs": ["chapter1.pdf", "lecture.pptx", "handwrite_01.jpg"],
  "extra": { "subject": "数学" }
}
```

### 6.8 `POST /api/v1/notes/catalog` —— 知识目录

- **用途**：按已入库资料（+ 可选老师划重点）生成知识目录。
- **输入**：可整体缺省；`texts`（teacher_focus 老师划重点）可选
- **生效的 extra**：`subject`（**必填**）

```json
{
  "texts": {
    "teacher_focus": "本章重点：极限与连续……"
  },
  "extra": { "subject": "数学" }
}
```

### 6.9 `POST /api/v1/notes/checklist` —— 复习清单

- **用途**：按已有知识目录和知识库（+ 可选老师划重点）生成复习清单。
- **输入**：`docs`（**必填**，catalog 文件名 `.json`，从 `data/{user_id}/knowledge/catalogs/{学科拼音}/` 取）+ `texts`（teacher_focus 老师划重点，可选）
- **生效的 extra**：`subject`（**必填**）

### 6.10 `GET /api/v1/health` —— 健康检查

- **用途**：服务状态 + 任务线清单。

```json
{
  "status": "ok",
  "task_lines": {
    "meeting": ["actions", "mindmap", "minutes", "minutes_styles", "minutes_trace", "risks"],
    "notes": ["catalog", "checklist", "graph", "library", "quiz", "review"]
  }
}
```

---

## 七、文件与产物

### 7.1 输入文件查找

```
docs[] 中的文件 →  data/{user_id}/docs/{name}  →  data/docs/{name}
（图片 OCR、文本直读、文档解析、.json 为 catalog 文件）
```

用户目录优先，公共目录兜底。防目录穿越（拒绝 `../`、绝对路径、路径分隔符）。

### 7.2 产物落盘

每次调用产物保存到 **`data/{user_id}/output/{request_id}/`**：

| 文件 | 内容 |
|---|---|
| `result.md` | 标准 Markdown 链接版（= 响应 `data` 内容），所有任务线都有 |
| `result.html` | 页面版（可直接打开/预览）。**仅以下线生成**：`minutes` / `minutes_trace`（记忆对照页，未命中记忆时为纯文本页）、`notes/graph`（交互图谱）、`notes/review` / `quiz` / `checklist`（各自交互页）；`actions` / `risks` / `minutes_styles` / `library` / `catalog` 不生成（产物目录只有 `result.md`） |

`request_id` 来自请求头 `X-Request-Id`（必填，建议 UUID）。未传 `X-User-Id` 时（实际必填，此仅为兜底）为 `data/output/{request_id}/`。

### 7.3 记忆落盘

`minutes`/`minutes_styles`/`graph` 任务命中记忆时，记忆写入 **`data/{user_id}/memory/`**（records/domain/projects/...），下次同用户任务自动命中历史并溯源。

### 7.4 catalog 目录存储

```
data/{user_id}/knowledge/catalogs/{subject拼音}/   ← 按学科分目录（数学 → shuxue）
    ├── 20260827_223121_828.json      ← 第 1 次生成（纯时间戳文件名）
    ├── 20260827_223136_584.json      ← 第 2 次（基于时间最近的 v1 增量，历史保留）
    └── ...
```

- 文件名 = 纯时间戳 `YYYYMMDD_HHMMSS_fff`（毫秒防同秒冲突），历史版本全保留。
- 增量：同一 user+subject 下次生成，取该目录时间最近的 json 作基线（`mode=incremental_update`）。
- `data.file_name` 返回最新文件名（如 `20260827_223136_584.json`）；checklist 的 `docs` 传它即可定位到该目录下的文件。

---

## 八、常见错误

| 场景 | HTTP / code | message 示例 |
|---|---|---|
| 缺 `X-User-Id` | 400 | `minutes 需要 X-User-Id（用户标识：会议纪要关联记忆、知识库按用户隔离）` |
| 缺 `X-Request-Id` | 400 | `缺少 X-Request-Id（调用方追踪 ID，建议用 UUID；产物目录 data/{user_id}/output/{request_id}/ 以它为名）` |
| texts/docs 全空 | 400 | `texts / docs 至少提供一个` |
| 缺必填字段 | 400 | `graph 缺少必填项：docs（笔记 .txt/.md 文件）` / `minutes_trace 缺少必填项：texts 中 keypoints（用户重点文本）、texts 中 notes（用户笔记文本）` / `minutes_styles 缺少必填项：extra.style（多样式纪要组织模式）` / `checklist 缺少必填项：docs（catalog 文件名，如 phy_8b4dccc8.json）` |
| catalog 缺 subject | 400 | `catalog 需要 extra.subject` |
| 非法 style | 400 | `extra.style 非法：bad（可选：causal/logic/party/time/urgency）` |
| 非法 template | 400 | `extra.template 非法：bad_value（格式为 {场景ID}_{模板ID}）` |
| 非法 profile | 400 | `extra.profile 非法：not_exist（可选：空=客观全员 或 职业模板名）` |
| domain/task 与路径不一致 | 400 | `请求体 domain='notes' 与路径不一致（应为 meeting）` |
| 本地文件不存在 | 404 | `本地文件不存在：docs/photo_1.jpg（请放入 data/1/docs/ 或 data/docs/）` |
| 任务运行失败 | 500 | `任务运行失败：LLM 调用超时` |

---

## 十、流式接口（NDJSON 事件流）

每个业务接口都有对应的流式版本：**路径加 `/stream` 后缀**（如 `POST /api/v1/meeting/minutes/stream`），
**请求体、请求头与同步接口完全一致**。响应为 `application/x-ndjson` 事件流（每行一个 JSON 对象），
调用方可在任务运行期间实时感知进度，无需等待任务结束。

### 10.1 端点列表

| 同步端点 | 流式端点 |
|---|---|
| `POST /api/v1/meeting/{minutes,actions,risks,minutes_styles,minutes_trace}` | 同路径 + `/stream` |
| `POST /api/v1/notes/{graph,library,catalog,checklist}` | 同路径 + `/stream` |

### 10.2 事件协议（每行一个 JSON）

| type | 字段 | 说明 |
|---|---|---|
| `phase` | `node` | 图内某节点完成（如 `meeting_understanding` / `minutes_agent` / `minutes_supervisor`），用于感知阶段进度；节点名 = 领域节点名 |
| `chunk` | `line` / `title` / `text` | 渲染文本增量：`line` = 线名、`title` = 展示标题、`text` = 文本块（逐块追加即完整正文） |
| `done` | `code` / `request_id` / `message` / `quality_warning` / `monitor` / `data` | 最终结果，字段与同步响应同构（`data.text` = 完整 Markdown、`data.file_name` 同同步接口） |
| `error` | `code` / `message` | 任务运行失败（准备或执行阶段异常） |

**示例事件流**（minutes）：

```jsonc
{"type": "phase", "node": "meeting_understanding"}
{"type": "phase", "node": "minutes_agent"}
{"type": "phase", "node": "minutes_supervisor"}
{"type": "chunk", "line": "minutes", "title": "客观会议纪要", "text": "# 会议纪要\n本次会议……"}
{"type": "chunk", "line": "minutes", "title": "客观会议纪要", "text": "会议明确……"}
{"type": "done", "code": 0, "request_id": "req-0001", "message": "ok", "quality_warning": null,
 "monitor": {"token_usage": 53268, "cache_hit": 24320, "cost_time": 42.9},
 "data": {"text": "# 会议纪要\n本次会议……", "file_name": ""}}
```

### 10.3 行为约定

- **参数校验失败（400/404）仍直接返回 HTTP 错误**，不走流（与同步接口一致）；
- 流开始后任务失败：HTTP 保持 200，流内推 `error` 事件（业务错误在事件里）；
- 产物落盘与同步接口一致：`data/{user_id}/output/{request_id}/result.md` / `result.html`；
- `done` 事件里的 `monitor` / `data` 字段与同步响应完全同构，调用方可直接复用解析逻辑。

### 10.4 调用示例（Python）

```python
import json, requests

with requests.post(
    "http://127.0.0.1:8000/api/v1/meeting/minutes/stream",
    headers={"X-User-Id": "u1"},
    json={"texts": {"transcript": "会议记录全文……"}},
    stream=True, timeout=600,
) as r:
    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue
        event = json.loads(line)
        if event["type"] == "phase":
            print("阶段:", event["node"])
        elif event["type"] == "chunk":
            print(event["text"], end="")
        elif event["type"] == "done":
            print("\n完成:", event["monitor"], event["data"]["text"][:50])
        elif event["type"] == "error":
            print("失败:", event["message"])
```

> 前端可用 `fetch` + `ReadableStream` 逐行解析 NDJSON；若经 Nginx 反代，需关闭缓冲（`proxy_buffering off`）保证事件实时到达。

---

## 九、完整调用示例

**curl（会议纪要，含模板与视角）**：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/meeting/minutes \
  -H "Content-Type: application/json" \
  -H "X-User-Id: u1" \
  -H "X-Request-Id: req-0001" \
  -d '{
    "texts": {
      "transcript": "会议记录全文……"
    },
    "extra": { "template": "meeting_minutes_team_meeting", "profile": "developer" }
  }'
```

**响应**：

```json
{
  "code": 0,
  "request_id": "req-0001",
  "message": "ok",
  "monitor": {
    "token_usage": 8231,
    "cache_hit": 1560,
    "cost_time": 12.5
  },
  "data": {
    "text": "# 项目例会：后端开发完成与上线测试环境安排\n\n……",
    "file_name": ""
  }
}
```

**前端接入要点**：
- `data.text` 为 md 文本，用 markdown-it（默认配置即可）渲染；记忆溯源为标准链接，配 anchor 插件可点击跳转。
- 下载：`data` 内容直接 Blob 存 `.md`；html 预览走 `data/{user_id}/output/{request_id}/result.html`。
- 长文本用 `JSON.stringify` 序列化，避免裸换行导致的 422。
