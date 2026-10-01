# API 请求体字段重构与接口参数校验规范

> **状态**：设计完成 / 待实施验证  
> **适用版本**：AgentFlow v2 统一入口 (`/api/agent/v1` 及 `/api/agent/v1/stream`)  
> **核心目标**：彻底理顺请求体字段分层，终结“大杂烩 `extra`”与“`docs` 跨目录伪装传参”的历史包袱，建立 14 个任务线清晰严密的必传/可选字段前置校验矩阵。

---

## 目录
1. [背景与核心设计原则](#一背景与核心设计原则)
2. [第一部分：请求体数据结构重构方案](#二第一部分请求体数据结构重构方案)
   - 2.1 顶层请求体 `TaskRequest` 重构
   - 2.2 领域参数集 `Extra` 规范与新增 `extra.catalog`
   - 2.3 100% 向下兼容保障机制（Auto-Lifting）
3. [第二部分：全领域 14 个任务必传与可选字段矩阵](#三第二部分全领域-14-个任务必传与可选字段矩阵)
   - 3.1 全局底线通用规则
   - 3.2 会议领域（Meeting Domain · 8 个任务）
   - 3.3 笔记领域（Notes Domain · 6 个任务）
4. [第三部分：前置校验层（Fail-Fast）改造指引](#四第三部分前置校验层fail-fast改造指引)

---

## 一、背景与核心设计原则

### 1.1 历史痛点分析
1. **语义过载与职责越界**：
   - `docs: list[str]` 原本设计用于传递位于 `data/{user_id}/docs/` 下的用户物理材料（PDF、图片、录音转写文稿等）。
   - 但在旧版实现中，`checklist` 任务为了指定目录版本，把 `20261001_100000.json` 强行塞进 `docs`，导致后端在处理时必须写死 `if name.endswith('.json')` 去翻 `knowledge/catalogs/` 目录；
   - `catalog` 任务也把老师重点 `.txt` 混在 `docs` 里，依靠后缀做逻辑分流。代码充满猜谜式的特判。
2. **层级倒置与“垃圾桶”现象**：
   - `time`（实际为会议召开时间 `meeting_time`）摆在顶层，导致笔记域任务面对一个毫无意义的 `time`；
   - `memory` 作为**系统级长记忆能力总开关**，却被塞在 `extra.memory` 的底层小参数集里；
   - `extra` 承担了系统能力（`memory`）、空间隔离（`project`/`subject`）、认知视角（`profile`）和任务专属微调（`template`/`style`/`agenda_txt`）四类异构概念，权责不清。

### 1.2 核心设计原则
1. **正交分层原则（Orthogonal Layering）**：
   - **顶层**：只保留跨全领域普适的通用元字段（领域、任务、输入文本、物理附件、系统长记忆开关）。
   - **`extra` 内部**：承载领域专属空间与任务个性化微调参数。
2. **职责纯化原则（Pure Responsibility）**：
   - `docs` 从此 100% 纯化为“用户真实材料附件列表”，严禁承载任何系统控制参数或历史版本引用。
   - 知识目录版本明确由 `extra.catalog` 承载，后端自动定位目录库，语义明牌化。
3. **零破坏渐进演进（Zero Breaking Changes）**：
   - 利用 Pydantic v2 的前置校验器自动做向上提升（Auto-Lifting），老客户端按旧格式传参依然 100% 兼容。

---

## 二、第一部分：请求体数据结构重构方案

### 2.1 顶层请求体 `TaskRequest` 重构

```python
class TaskRequest(BaseModel):
    """通用请求体（统一入口 /api/agent/v1 顶层契约）。
    
    顶层仅包含全领域绝对通用的 5 大核心属性：
    - domain / task: 路由定位
    - memory: 系统级长记忆总开关
    - texts: 纯文本内联载荷
    - docs: 物理附件文档列表
    - extra: 领域与任务专属参数
    """
    domain: str = Field(..., description="业务领域: meeting | notes")
    task: str = Field(..., description="任务线代码标识")
    
    # 🔥【提升至顶层】系统级长记忆能力开关（语义与 stream / tools 等能力开关对齐）
    memory: bool = Field(default=False, description="是否启用长记忆上下文检索与跨调用持久化")
    
    # 纯文本输入（固定三类 key：transcript / keypoints / notes）
    texts: dict[str, str] = Field(default_factory=dict, description="内联文本字典")
    
    # 物理附件文件列表（纯化：严格仅代表 data/{user_id}/docs/ 下的文件/图片）
    docs: list[str] = Field(default_factory=list, description="用户物理附件文件名列表")
    
    # 差异与微调参数集
    extra: Extra = Field(default_factory=Extra, description="领域专属空间与任务微调参数")
```

---

### 2.2 领域参数集 `Extra` 规范与新增 `extra.catalog`

```python
class Extra(BaseModel):
    """领域专属空间与任务微调参数。"""

    # ── 1. 领域空间维度（各领域专属的数据分区键）──
    project: str = ""        # 会议域专属：项目空间（用于会议记忆与纪要归档隔离）
    subject: str = ""        # 笔记域专属：学科/课程（如 physics，用于定位知识库与目录）
    
    # ── 2. 会议专属业务上下文（原顶层 time 下沉）──
    time: str = ""           # 会议域专属：会议召开时间（如 "2026-06-15 10:00"，用于记忆溯源）
    
    # ── 3. 全局认知视角模型 ──
    profile: str = ""        # 视角设定（objective=客观全员, user=个人视角, 职业名称等）

    # ── 4. 任务专属选项 ──
    template: str = ""       # 纪要任务模板（如 project_progress）
    style: str = ""          # 多样式纪要组织风格（time | logic | causal | party | urgency）
    agenda_txt: str = ""     # 议程驱动纪要的文本补充（可与 docs 图片/文档智能合并）
    
    # 🔥【全新显式字段】知识目录版本文件名
    catalog: str = ""        # 笔记域专属：显式指定使用的知识目录文件名（如 "20261001_100000.json"）
```

#### `extra.catalog` 的底层运作逻辑：
- **语义**：显式声明当前任务（如 `checklist`）希望以哪一份目录快照作为基线。
- **自动寻址**：后端直接根据 `user_id`、`extra.subject` 和 `extra.catalog` 拼装安全路径：
  `data/{user_id}/knowledge/catalogs/{subject_pinyin}/{extra.catalog}`。
- **缺省降级**：若未传 `extra.catalog`（为空），底层自动检索该学科目录下 `mtime` 最新的一个 `.json` 文件，实现“开箱即用取最新”。
- **收益**：`docs` 再也不需要接纳任何 `.json` 文件，代码中所有 `if name.endswith('.json')` 的特判嗅探彻底废弃。

---

### 2.3 100% 向下兼容保障机制（Auto-Lifting）

为了确保现有前端脚本、测试用例无感知平滑过渡，在 `TaskRequest` 与 `Extra` 中设置双向自动映射：

```python
class TaskRequest(BaseModel):
    ...
    @model_validator(mode="before")
    @classmethod
    def _compat_legacy_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            extra = data.get("extra")
            if isinstance(extra, dict):
                # 1. 兼容老客户端把 memory 放在 extra 内部的情况：自动提升到顶层
                if "memory" in extra and "memory" not in data:
                    data["memory"] = extra["memory"]
                # 2. 兼容老客户端把 time 传在顶层的情况：自动下沉到 extra.time
                if "time" in data and "time" not in extra:
                    extra["time"] = data.pop("time")
                # 3. 兼容老客户端把 catalog 文件传在 docs[0] 的情况
                if not extra.get("catalog") and data.get("docs"):
                    jsons = [f for f in data["docs"] if str(f).lower().endswith(".json")]
                    if jsons:
                        extra["catalog"] = jsons[0]
                        data["docs"] = [f for f in data["docs"] if not str(f).lower().endswith(".json")]
        return data
```

---

## 三、第二部分：全领域 14 个任务必传与可选字段矩阵

### 3.1 全局底线通用规则
对所有任务进行前置校验时，必须满足：
1. **`X-User-Id` 请求头**（或 URL 参数 `?user_id=`）：**全量 14 个任务强制必传**。未提供直接响应 HTTP 400（数据安全与租户物理隔离红线）。
2. **`domain` & `task`**：必须在合法白名单内，非法直接响应 HTTP 404。

---

### 3.2 会议领域（Meeting Domain · 8 个任务）

会议域所有任务紧密围绕会议转写实录展开，`texts.transcript` 是大部分任务的基石：

| 序号 | 任务标识 (`task`) | 任务中文名 | 必传字段清单（缺失直接 400 秒回） | 可选增强字段 | 缺省行为 / 降级说明 |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **1** | **`minutes`** | 通用/视角纪要 | `texts.transcript` | `memory`<br>`extra.template`<br>`extra.profile`<br>`extra.project`<br>`extra.time`<br>`docs` | - `template` 缺省自动匹配通用或个人默认模板<br>- `profile` 缺省为 `objective`（客观全员视角） |
| **2** | **`actions`** | 待办事项 | `texts.transcript` | `memory`<br>`extra.project`<br>`extra.time` | 必须依赖转写全文提炼行动项四要素（任务、责任人、截止日、交付物）。 |
| **3** | **`risks`** | 风险议题 | `texts.transcript` | `memory`<br>`extra.project`<br>`extra.time` | 识别争议、技术瓶颈与进度风险。 |
| **4** | **`mindmap`** | 会议脑图 | `texts.transcript` | `memory`<br>`extra.project` | 生成 Markmap 结构大纲与交互 HTML。<br>*(注：旧版校验遗漏了此项，现行规范正式确立其必传 transcript)* |
| **5** | **`consensus_decision`**| 决议共识 | `texts.transcript` | `memory`<br>`extra.project`<br>`extra.time` | 锁定拍板决策与全员共识。 |
| **6** | **`agenda_minutes`** | 议程驱动纪要 | `texts.transcript` | `extra.agenda_txt`<br>`docs` (议程图/文档)<br>`memory`<br>`extra.project`<br>`extra.time` | **议程单为可选增强**：<br>- 支持 `extra.agenda_txt` 纯文本输入；<br>- 支持 `docs` 图片/文档自动 OCR；<br>- 两者都有时自动拼接；<br>- 若都不传，退化为由转写全文自动提取大纲议题。 |
| **7** | **`minutes_styles`** | 多风格纪要 | `texts.transcript`<br>`extra.style` | `memory`<br>`extra.project`<br>`extra.time` | **`extra.style` 必传**，且必须严格受限于枚举：`time`（时序）、`logic`（逻辑）、`causal`（因果）、`party`（责任方）、`urgency`（紧迫度）。非法值报 400。 |
| **8** | **`minutes_trace`** | 事实溯源纪要 | `texts.transcript`<br>`texts.keypoints`<br>`texts.notes` | `memory`<br>`extra.project`<br>`extra.time` | **三项文本全必传**：必须同时提供转写原文、用户关键点、速记笔记，才能进行严格的事实三方交叉锚定。 |

---

### 3.3 笔记领域（Notes Domain · 6 个任务）

笔记域涉及知识库持久化与知识树演进，核心校验在于 **`extra.subject`** 与 **输入材料的存在性**：

| 序号 | 任务标识 (`task`) | 任务中文名 | 必传字段清单（缺失直接 400 秒回） | 可选增强字段 | 缺省行为 / 降级说明 |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **1** | **`library`** | 资料入库 | `extra.subject`<br>`docs` (至少传 1 个文件) | 无 | **ETL 数据管道任务**：必须指定学科名，且 `docs` 必须包含待处理的真实物理文件（图片或文档）。不接收 `texts` 输入。 |
| **2** | **`catalog`** | 知识目录 | `extra.subject` | `docs` (老师重点.txt)<br>`texts` (补充说明) | **`docs` 和 `texts` 均为可选**！<br>其核心数据源来自本用户该学科**已入库的向量切块**。若传了老师划重点文档，则加权引导大纲权重。 |
| **3** | **`checklist`** | 复习清单 | `extra.subject` | `extra.catalog`<br>`docs` (老师重点.txt)<br>`texts` (补充说明) | **`extra.subject` 必传**。<br>- `extra.catalog` 不传则系统默认自动定位该学科时间戳最新的目录 JSON；<br>- 老师重点文档可选辅助。 |
| **4** | **`graph`** | 知识图谱 | 材料二选一：<br>`texts` 或 `docs` 至少其一 | `extra.subject`<br>`memory` | 知识概念实体抽取与拓扑构建。<br>- 可直接在 `texts.transcript` 或 `texts.notes` 贴文本；<br>- 也可通过 `docs` 上传笔记文档/板书图片。 |
| **5** | **`review`** | 笔记审查 | 材料二选一：<br>`texts` 或 `docs` 至少其一 | `extra.subject`<br>`extra.profile`<br>`memory` | 学生笔记审查与纠错。<br>- 强烈推荐传 `extra.subject`，以便命中对应学科知识库做准确核对；<br>- 支持内联贴笔记或传笔记文档。 |
| **6** | **`quiz`** | 随堂自测 | 材料二选一：<br>`texts` 或 `docs` 至少其一 | `extra.subject`<br>`extra.profile`<br>`memory` | 测验卷生成。<br>- 支持根据课本转录文本出题，或根据笔记材料出题；<br>- `profile` 可控制出题难易度与题型侧重。 |

---

## 四、第三部分：前置校验层（Fail-Fast）改造指引

### 4.1 校验层执行顺序
所有的任务调用在进入 `core.runner` 之前，必须在 `app/tasks.py:_prepare` 头部依次执行三道门禁：

```
[HTTP 请求]
     │
     ▼
【门禁 1：全局基础校验】───► 校验 user_id 是否非空；domain/task 是否合法有效。
     │ (通过)
     ▼
【门禁 2：必传字段表校验】─► 匹配 REQUIRED_FIELDS：缺必填项直接收集清单，一次性报 400。
     │ (通过)
     ▼
【门禁 3：业务参数合法性】─► 检查 extra.style 枚举、extra.catalog 文件是否存在、docs 物理文件是否存在。
     │ (通过)
     ▼
[进入 Agent 流水线执行]
```

### 4.2 统一错误响应规范
当门禁拦截失败时，必须统一以 HTTP 400 状态码返回结构化错误，避免给调用方造成困惑：

```json
{
  "code": 400,
  "request_id": "req-20261001-err01",
  "message": "minutes_styles 缺少必填项：texts 中 transcript（会议转写文本）、extra.style（多样式纪要组织模式）",
  "monitor": { "token_usage": 0, "cache_hit": 0, "cost_time": 0.0 },
  "data": { "text": null, "file_name": "" }
}
```

---

## 五、总结与价值

1. **统一优雅**：请求体顶层不再出现任何具有偏向性的特定领域参数，通用骨架立竿见影。
2. **彻底解耦**：新增 `extra.catalog` 字段直接宣告了“用 docs 偷传目录 JSON”时代的终结，路径查找逻辑全部归位。
3. **安全健壮**：补齐了 `mindmap` 漏校验等历史死角，纠正了 `graph` 和 `checklist` 过于严苛的传参限制，使系统在“严格拦截缺失项”与“支持灵活调用”之间取得了最科学的平衡。
