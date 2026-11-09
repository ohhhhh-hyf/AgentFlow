# 会议纪要任务 (minutes) 专有接口规范文档

本文档专为 **会议纪要任务 (`domain="meeting"`, `task="minutes"`)** 定制编写，剥离了与笔记域（`notes`）及其他任务线无关的字段（如 `subject`, `style`, `catalog` 等），全面梳理并深度呈现了 **当前请求体中所有对 minutes 任务真实生效的字段**，包含新增的 **多源视觉文本 (`texts.vision_info`)**、**结构化议程大盘快捷通道 (`extra.agenda_plan`)**、**多语种支持 (`lang`)**、**长记忆开关 (`memory`)** 以及 **视角门禁机制**。

---

## 1. 接口概览与端点定义

会议纪要服务对外提供三种调用形态，所有 POST 请求体结构完全同构：

| 端点形态 | 请求方法 | 路径 | 适用场景与说明 |
|---|---|---|---|
| **普通同步** | `POST` | `/api/agent/v1` | 阻塞等待纪要生成完成，直接返回最终 Markdown 正文与页面文件名。 |
| **实时流式** | `POST` | `/api/agent/v1/stream` | 返回 `application/x-ndjson` 事件流（阶段变更 `phase`、增量打字机 `chunk`、最终完成 `done`）。 |
| **异步任务** | `POST` | `/api/agent/v1/async` | 异步提交任务并立即返回 `job_id`，配合轮询或事件监听获取结果。 |
| **产物下载** | `GET` | `/api/agent/v1/file/{request_id}/{file_name}` | 下载生成的 HTML 页面版或 Markdown 源文件。 |

---

## 2. 请求头规范 (HTTP Headers)

| 请求头字段 | 必填性 | 类型 | 说明与作用 |
|---|---|---|---|
| `Content-Type` | **必填** | `string` | 固定为 `application/json`。 |
| `X-User-Id` | **必填** | `string` | 租户/用户唯一标识。用于服务端多租户目录隔离（材料读取路径 `data/{user_id}/docs/`、个人画像 `data/{user_id}/user.json`、会议记忆库隔离与产物归档）。 |
| `X-Request-Id` | 可选 | `string` | 调用方链路追踪 ID。产物目录以此命名（`data/{user_id}/output/{request_id}/`）；若不传，系统将自动生成分布式唯一 ID（形如 `request_...`）。 |

---

## 3. 请求体全量字段生效矩阵 (专属于 minutes)

以下为专属于 `minutes` 任务的有效请求体完整示例（已剔除无关冗余字段）：

```jsonc
{
  "domain": "meeting",                    // [必填] 固定为 "meeting"
  "task": "minutes",                      // [必填] 固定为 "minutes"
  "lang": "zh",                           // [可选] 语种控制：仅支持 "zh"(中文) 或 "en"(英文)，缺省默认 "zh"
  "memory": false,                        // [可选] 系统级长记忆能力开关：true 开启历史会议关联对比与记忆沉淀
  "texts": {                              // [核心] 多源文本集合（仅以下 4 个 key 对 minutes 有效）
    "transcript": "会议录音语音转写全文...",   // [条件必填] 会议语音转写原文（与 notes 至少提供一个）
    "vision_info": "屏幕截图/PPT/白板的OCR识别文本...", // [可选·新增] 视觉材料识别后的纯文本，组装入辅助参考
    "keypoints": "用户标记的核心重点...",    // [可选] 用户在会中手动勾选或收藏的核心关键点
    "notes": "用户速记内容或划线笔记..."       // [可选] 用户笔记，支持 '原话 -> 备注' 语法；transcript 为空时可作为底座
  },
  "docs": [                               // [可选] 存放于服务端 data/{user_id}/docs/ 下的文件名列表
    "既定议程单.png",                      // 支持图片/文档，可触发议程探测；未识别为议程时自动静默回退并入转写
    "参考资料.pdf"
  ],
  "extra": {                              // [扩展] minutes 专有控制参数
    "agenda_plan": {                      // [可选·新增] 结构化议程大盘快捷通道（优先级高于 docs，直接直传 JSON）
      "meta": {
        "theme": "技术研讨与量产评审会",
        "attendees": "张三；李四；王五"
      },
      "items": [
        {
          "seq": "01",
          "title": "自研芯片二期量产与良率评估",
          "presenters": ["张三"],
          "time_range": "14:00-14:30"
        }
      ]
    },
    "template": "",                       // [可选] 模板选择：留空自动识别匹配场景；或显式指定模板 ID / 中文名
    "profile": "",                        // [可选] 视角控制：空=客观全员视角；"user"=个人专属视角（注：与议程模式互斥）
    "time": "2026-08-29 10:00",           // [可选] 会议召开时间，用于长记忆时序锚定与「第 N 场」推断
    "project": "小艺慧记"                  // [可选] 项目绑定名，memory=true 时驱动会议记忆按项目聚合
  }
}
```

---

## 4. 字段详细规范与逻辑说明

### 4.1 顶层核心控制字段

| 字段名 | 类型 | 必填 | 默认值 | 详细逻辑与生效规则 |
|---|---|---|---|---|
| **`domain`** | `string` | **是** | - | 必须严格为 `"meeting"`。若传入其他值或不存在的值，系统在接入层直接拦截并返回 400/404。 |
| **`task`** | `string` | **是** | - | 必须严格为 `"minutes"`。声明运行常规/议题会议纪要任务线。 |
| **`lang`** | `string` | 否 | `"zh"` | **顶层语种控制字段**。仅支持 `"zh"`（中文）或 `"en"`（英文，大小写不敏感，支持 `"english"` 自动归一化）。<br>影响范围：下游 Prompt 语言、渲染模板匹配（`resources/templates/{lang}/`）、议题探测分词规则等。若传入其他不支持语言将触发 422 校验失败。 |
| **`memory`** | `boolean` | 否 | `false` | **系统级跨会话长记忆开关**。<br>• 设为 `true`：系统自动检索该用户历史会议记忆库，若命中同项目或强相关前序会议，正文会生成「历史对比/决议承接」标注，并在任务完成后自动将本场会议核心决策写回记忆图谱。<br>• 设为 `false`：单场独立执行，不检索也不写回历史记忆。 |

---

### 4.2 多源文本输入 (`texts` 对象)

`texts` 为多源纯文本键值字典。Pydantic 模型对 `texts` 设置了严格白名单，传入未知 key 会直接被拦截抛出 422 错误。

专属于 `minutes` 任务的有效字段如下：

| 字段名 | 类型 | 必填 | 详细作用与处理逻辑 |
|---|---|---|---|
| **`transcript`** | `string` | **条件必填** | **会议录音转写主文本**。<br>• 会议事实的核心载体，记录全场发言人声纹及时间序列对话。<br>• 若 `transcript` 为空但 `notes` 存在，系统会自动将 `notes` 作为输入正文兜底；若二者均为空且 `docs` 也无有效内容，接口返回 400 错误。 |
| **`vision_info`** | `string` | **可选**<br>*(新增核心)* | **视觉材料 OCR/VLM 识别文本**。<br>• **注意**：必须为**字符串文本**（前端或上游 VLM 对屏幕截图、PPT 幻灯片、白板、报表、架构图等完成识别后的纯文本），**绝不能传入图片文件路径或二进制**。<br>• 后端**不会再对其调用 OCR/VLM**，而是将其组装为 `【视觉信息参考(OCR)】` 辅助材料注入纪要生成上下文，有效弥补口语讨论中未提及的详细图表数据、指标数值与架构细节。<br>• **注意**：`vision_info` 仅作为辅助事实材料，**不会触发议题增强模式**（议题增强仅由议程触发）。 |
| **`keypoints`** | `string` | 可选 | **用户核心关注点**。<br>• 会议进行中用户手动标记、高亮或收藏的要点纯文本。<br>• 后端组装为 `【用户核心关键点】` 注入上下文，引导模型重点关注该部分内容。 |
| **`notes`** | `string` | 可选 | **用户划线笔记与速记**。<br>• 支持普通纯文本，亦支持带有原话引用的语法：`原话 -> 笔记备注`（系统会自动解析为结构化的 `【用户划线原话与笔记】` 注入模型上下文）。<br>• 当 `transcript` 为空时，可作为纪要事实的兜底来源。 |

> [!NOTE]
> **关于 `actions_text` 字段**：虽然通用 Schema 允许在 `texts` 中传递 `actions_text`，但该字段为待办提取任务（`actions`）专享，**`minutes` 任务不会消费此字段**。

---

### 4.3 物理参考文档 (`docs` 数组)

`docs` 为文件名字符串数组，文件必须已预先上传存放在服务端的 `data/{user_id}/docs/` 目录下。

在 `minutes` 任务中，`docs` 具备**智能双模探测与自动回退机制**：

1. **议题增强自动探测（Agenda Mode）**：
   - 当 `docs` 中包含议程单图片（`.png`, `.jpg` 等）或文本（`.txt`, `.docx` 等）时，系统会优先提取议程骨架，并结合 `transcript` 进行现场讨论有效性探测（`probe_valid_agendas`）。
   - 一旦探测出现场确实开展了实质议题研讨，系统将**自动激活议题增强流水线**（议程单内容专供议题对齐，不掺入主会议录音文本）。
2. **常规参考资料静默回退（Normal Mode）**：
   - 若 `docs` 传入的是技术白皮书、财务报表、纯代码文件等非议程资料，或议程中的议题在现场全未讨论，系统会**自动静默回退至常规参考资料流程**：调用 OCR/文本提取后，拼接合并到 `transcript` 录音转写文本中作为事实底座。
3. **快捷通道优先级**：
   - 若同时传入了 `extra.agenda_plan`（见 4.4），系统将**优先使用 `agenda_plan`**，`docs` 仅作为普通参考材料或传空 `[]`。

---

### 4.4 扩展控制字段 (`extra` 对象)

| 字段名 | 类型 | 必填 | 详细规范与逻辑说明 |
|---|---|---|---|
| **`agenda_plan`** | `object` / `string`<br>*(新增核心)* | 可选 | **结构化议程大盘快捷通道**。<br>• 专为 VLM 团队或上游系统设计的结构化注入接口，支持直接传递符合契约的 `dict` 对象或已序列化的 JSON 字符串。<br>• **双通道优先级**：当传入 `extra.agenda_plan` 时，**`docs` 直接传空数组 `[]` 即可**，彻底跳过底层的图片落盘与 OCR/VLM 解析，大幅缩减链路耗时并达成 100% 结构字段保真。<br>• 字段格式兼容两种主流契约（详见下文 4.4.1）。 |
| **`template`** | `string` | 否 | **纪要渲染模板**。<br>• `""`（留空，默认）：系统前置场景分类器会根据会议主题与转写文本，**智能识别场景并自动套用**最适合的模板（如发布会套用 `media_briefing`，常规会套用 `general_minutes`）。<br>• 显式指定：可传模板 ID 或中文名，如 `"general_minutes"`（通用纪要）、`"media_briefing"`（新闻发布）、`"project_progress"`（项目进度）、`"decision_review"`（决策评审）、`"workshop_session"`（工作研讨）等。 |
| **`profile`** | `string` | 否 | **纪要生成视角（画像）**。<br>• `""`（留空，默认）：**客观全员视角 (`objective`)**，站在中立视角全面记录所有讨论、决定与待办。<br>• `"user"`：**个人专属视角 (`personal`)**。系统读取 `data/{user_id}/user.json` 生成带本人待办、风险与关注点的纪要。<br>• **⚠️ 核心门禁**：**议程增强模式下不支持 `profile="user"`**（个人视角与议题增强模式在架构上互斥），若在议程模式下传入 `"user"`，系统将直接拦截并返回 **HTTP 400** 错误（`AgendaPersonalUnsupported`）。<br>• 职业模板（如 `"pm"`, `"architect"`）：常规模式生效；在议程模式下自动安全降级为客观视角并附带警告。 |
| **`time`** | `string` | 否 | **会议召开时间**。<br>• 格式如 `"2026-08-29 10:00"` 或 `"2026-08-29"`。<br>• 供长记忆时序单调性校验、计算该项目的“第 N 场会议”、以及待办事项相对时间回填使用。若不传则时间未知，系统不会凭空伪造时间。 |
| **`project`** | `string` | 否 | **项目名称绑定**。<br>• 在 `memory=true` 时生效。指定本场会议关联的项目空间，驱动会议记忆跨会话精准聚合；可空，系统将根据内容自动归并。 |

#### 4.4.1 `extra.agenda_plan` 的两种兼容格式

系统原生兼容以下两种 JSON 结构，上游无需做二次复杂转换：

**格式 A：标准契约格式（`meta` + `items` 推荐）**
```json
{
  "meta": {
    "theme": "技术研讨与量产评审会",
    "attendees": "张三；李四；王五"
  },
  "items": [
    {
      "seq": "01",
      "title": "自研芯片二期量产与良率评估",
      "presenters": ["张三"],
      "time_range": "14:00 ~ 14:30"
    },
    {
      "seq": "02",
      "title": "下一代低功耗架构方案审议",
      "presenters": ["李四"],
      "time_range": "14:30 ~ 15:15"
    }
  ]
}
```

**格式 B：VLM 扁平化格式（`theme` + `attendees` + `agenda_items`）**
```json
{
  "theme": "技术研讨与量产评审会",
  "attendees": ["张三", "李四", "王五"],
  "agenda_items": [
    {
      "seq": "01",
      "title": "自研芯片二期量产与良率评估",
      "presenters": ["张三"],
      "time_range": "14:00 ~ 14:30"
    }
  ]
}
```

---

### 4.5 对 minutes 任务无效的字段清单（可忽略）

在通用 `TaskRequest` 中定义的以下字段属于其他业务线，**在 `minutes` 任务中均不生效，调用方无需传入**：

| 字段位置 | 字段名 | 归属任务线 | minutes 任务的处理方式 |
|---|---|---|---|
| `texts` | `actions_text` | 专供待办任务（`actions`） | 忽略，不作为纪要辅助材料。 |
| `extra` | `subject` | 专供笔记领域（`notes` 下各知识任务） | 忽略。 |
| `extra` | `style` | 专供多样式纪要（`minutes_styles`） | 忽略。 |
| `extra` | `catalog` | 专供复习清单（`checklist`）定位目录版本 | 忽略。 |

---

## 5. 核心模式判定与门禁守卫

会议纪要任务在底层的决策流转路径如下：

```mermaid
flowchart TD
    Req[收到 minutes 请求] --> DetectAgenda{是否提供有效议程?<br>extra.agenda_plan 或 docs 议程单}
    
    DetectAgenda -- 否 (或未讨论) --> Normal[常规纪要模式 (Normal)]
    DetectAgenda -- 是 (且现场已研讨) --> Agenda[议题增强模式 (Agenda)]
    
    Normal --> CheckProfileNormal{extra.profile}
    CheckProfileNormal -- 空或默认 --> Mode1[客观全员常规纪要]
    CheckProfileNormal -- user --> Mode2[个人视角常规纪要]
    CheckProfileNormal -- 职业画像 --> Mode3[角色画像常规纪要]
    
    Agenda --> CheckProfileAgenda{extra.profile}
    CheckProfileAgenda -- 空或默认 --> Mode4[客观全员议题纪要]
    CheckProfileAgenda -- user --> Reject[❌ 拦截报错: HTTP 400<br>AgendaPersonalUnsupported]
    CheckProfileAgenda -- 职业画像 --> Fallback[⚠️ 降级为客观全员议题纪要<br>响应带 quality_warning]
```

---

## 6. 典型场景请求报文示例

### 场景 1：最简标准会议纪要（仅会议录音转写）
```bash
curl -s -X POST http://127.0.0.1:8000/api/agent/v1 \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user_123" \
  -H "X-Request-Id: req_norm_001" \
  -d '{
    "domain": "meeting",
    "task": "minutes",
    "texts": {
      "transcript": "张三：今天我们主要讨论第三季度研发进度。李四：核心算法已完成自测，良率达到 92%..."
    }
  }'
```

---

### 场景 2：多源融合纪要（转写 + 视觉 OCR 纯文本 + 划线笔记 + 重点）
适用于会中有 PPT 演示板书或屏幕共享，且用户有划线和标记的场景：
```bash
curl -s -X POST http://127.0.0.1:8000/api/agent/v1 \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user_123" \
  -d '{
    "domain": "meeting",
    "task": "minutes",
    "texts": {
      "transcript": "张三：大家看这页大盘，流片测试良率我们已经拉升到了目标线以上...",
      "vision_info": "【PPT第4页-流片良率汇总表】批次: LOT-202608，样本量: 1200 片，一次良率: 91.5%，综合良率: 94.2%。",
      "keypoints": "流片良率突破91.5%，达到出货基准",
      "notes": "下半年做好去库存准备 -> 供应链需同步跟进\n下周一启动封测"
    }
  }'
```

---

### 场景 3：议题增强模式（通过 `extra.agenda_plan` 快捷通道直传）
VLM 团队无需存储图片文件，直接传议程 JSON，秒级启动议题对齐：
```bash
curl -s -X POST http://127.0.0.1:8000/api/agent/v1 \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user_123" \
  -d '{
    "domain": "meeting",
    "task": "minutes",
    "texts": {
      "transcript": "王海涛 10:00：各位早上好，由我汇报 Agent 长期记忆与用户个性化进展...\n刘雨桉 10:30：接下来进入第二项议题，递归演进技术探讨..."
    },
    "docs": [],
    "extra": {
      "time": "2026-08-29 10:00",
      "agenda_plan": {
        "meta": {
          "theme": "AI前沿早读-月度洞察会",
          "attendees": "涂丹丹；任昊宇；汪海洋"
        },
        "items": [
          {
            "seq": "01",
            "title": "Agent长期记忆与用户个性化",
            "presenters": ["王海涛"],
            "time_range": "10:00 ~ 10:30"
          },
          {
            "seq": "02",
            "title": "智能跃迁：智能体RSI递归自我演进技术洞察",
            "presenters": ["刘雨桉"],
            "time_range": "10:30 ~ 11:00"
          }
        ]
      }
    }
  }'
```

---

### 场景 4：个人专属视角纪要（`profile="user"`）
为特定用户提取专属关注点、待办与风险（读取服务端 `data/{user_id}/user.json`）：
```bash
curl -s -X POST http://127.0.0.1:8000/api/agent/v1 \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user_123" \
  -d '{
    "domain": "meeting",
    "task": "minutes",
    "texts": {
      "transcript": "李总：张三下周要把系统联调测试方案发我，王五配合提供测试用例..."
    },
    "extra": {
      "profile": "user"
    }
  }'
```

---

### 场景 5：启用跨会话长记忆（`memory=true` + `project`）
```bash
curl -s -X POST http://127.0.0.1:8000/api/agent/v1 \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user_123" \
  -d '{
    "domain": "meeting",
    "task": "minutes",
    "memory": true,
    "texts": {
      "transcript": "张三：上次会议定下来的双周交付目标，今天我们来核对落实情况..."
    },
    "extra": {
      "project": "小艺慧记Agent",
      "time": "2026-09-01 14:00"
    }
  }'
```

---

## 7. 响应报文规范

### 7.1 同步响应体 (`TaskResponse`)

```jsonc
{
  "code": 0,                           // 0=成功；非 0 表示异常业务码
  "request_id": "req_norm_001",        // 请求追踪 ID
  "message": "success",                // 状态描述
  "quality_warning": null,             // 仅在任务发生降级时返回（如角色画像降级为客观全员纪要）
  "monitor": {
    "token_usage": 14250,              // 本次调用消耗总 Token
    "cache_hit": 6144,                 // 缓存命中 Token
    "cost_time": 11.2                  // 耗时（秒）
  },
  "data": {
    "text": "# 会议纪要标题\n\n## 会议概况\n...", // 渲染完成的 Markdown 正文
    "file_name": "minutes.html"        // 对应的 HTML 页面文件名，可用于下载定位
  }
}
```

---

### 7.2 流式事件协议 (`POST /api/agent/v1/stream`)

响应 Content-Type 为 `application/x-ndjson`，每一行为一个独立的 JSON 事件对象：

1. **阶段流转事件 (`type="phase"`)**：
   ```json
   {"type": "phase", "node": "draft"}
   {"type": "phase", "node": "supervisor"}
   {"type": "phase", "node": "render"}
   ```
2. **打字机文本增量 (`type="chunk"`)**：
   ```json
   {"type": "chunk", "line": "minutes", "title": "会议纪要", "text": "## 核心决议\n- 团队一致决定..."}
   ```
3. **完成事件 (`type="done"`)**：
   ```json
   {
     "type": "done",
     "code": 0,
     "request_id": "req_norm_001",
     "message": "success",
     "quality_warning": null,
     "monitor": {"token_usage": 14250, "cache_hit": 6144, "cost_time": 11.2},
     "data": {
       "text": "# 会议纪要完整Markdown...",
       "file_name": "minutes.html"
     }
   }
   ```
4. **异常事件 (`type="error"`)**：
   ```json
   {"type": "error", "code": 400, "message": "texts 中 transcript（会议转写文本）"}
   ```

---

### 7.3 产物下载规范 (`GET /api/agent/v1/file/{request_id}/{file_name}`)

生成的完整排版页面和纯 Markdown 源文件均支持直接下载：

- **下载 HTML 排版页面**：
  ```bash
  curl -OJ "http://127.0.0.1:8000/api/agent/v1/file/<request_id>/minutes.html?user_id=user_123"
  ```
- **下载 Markdown 源文件**：
  ```bash
  curl -OJ "http://127.0.0.1:8000/api/agent/v1/file/<request_id>/result.md?user_id=user_123"
  ```

---

## 8. 常见状态码与错误排查指南

| HTTP 状态码 | 业务场景 | 原因与解决方案 |
|---|---|---|
| `400 Bad Request` | 缺少必要参数 | 缺少 `texts.transcript`（或 `notes`），或 `user_id` 为空。 |
| `400 Bad Request` | **视角与议程冲突** | **`AgendaPersonalUnsupported`**：在议程模式（传入有效 `agenda_plan` 或议程 `docs`）下指定了 `extra.profile="user"`。解决方案：议题纪要必须使用客观全员视角（`profile=""`）。 |
| `422 Unprocessable`| 非法参数或类型错误 | • `texts` 中传入了未定义字段（如非法 key）。<br>• `lang` 传入了非 `"zh"` / `"en"` 的值。<br>• `agenda_plan` 传入了无法解析的错误 JSON 字符串。 |
| `404 Not Found` | 路由不存在 | `domain` 或 `task` 拼写错误。 |
| `500 Server Error` | 执行异常 | LLM 上游接口超时或严重网络异常。 |
