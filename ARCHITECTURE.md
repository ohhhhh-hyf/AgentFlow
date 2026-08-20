# AgentFlow 系统架构说明

> 面向周报/汇报的架构文档。覆盖：总体分层、一次任务的执行流、契约驱动开发、
> 领域与任务线生成、图编排、记忆系统、知识库 RAG、聊天组件、数据隔离与监控。

---

## 1. 项目概览

AgentFlow 是一套**多 Agent 任务系统**：会议纪要 / 笔记知识整理 / 知识目录 / 复习清单 /
自测题 / 知识图谱等多条任务线并行执行，每条线独立走「生成 → 审核 → 渲染」流水线，
互不阻塞。系统同时具备**跨会话记忆**、**知识库检索问答（RAG）**与**对话式知识问答**，
所有用户数据（知识 / 记忆 / 聊天 / 产物）按用户物理隔离。

- 语言：Python ≥ 3.10
- 编排：LangGraph（图状态机 + 流式输出）
- 向量库：ChromaDB；LLM：DeepSeek（HTTP）等，可切换 WebSocket 后端
- Web UI：Gradio（4.x–6.x 兼容）；另有终端聊天入口

---

## 2. 总体架构

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              入口层（3 个入口）                             │
│                                                                              │
│  bootstrap.py（CLI）      gradio_app.py（Web UI）        chat.cli（终端问答）  │
│  --domain --task --file   · 任务面板/记忆/监控/聊天       --user --subject     │
│  --user_id --subject      · scope 字段（user/subject）    --session（会话恢复） │
└──────────────┬──────────────────────────┬─────────────────────────────────────┘
               ▼                          ▼
┌────────────────────────────┐  ┌────────────────────────────────────────────┐
│  tools/runner（CLI 组装）   │  │  web/app.py（Gradio Blocks）                │
│  · 参数/模板/输入/画像收集   │  │  · 任务执行（复用 runner.run）               │
│  · DomainContext（领域加载）│  │  · 产物/监控/记忆展示（按 user 读取）         │
└──────────────┬─────────────┘  └────────────────────────────────────────────┘
               ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                            编排层（LangGraph 图）                           │
│  tools/domain_engine.py（通用引擎）+ domain/{meeting,notes}/orchestrator    │
│                                                                              │
│  START ──► core 层（共享，并行）                                            │
│             ├─ 会议理解 / 笔记理解    （结构化事实底座：purpose/topics/决策） │
│             └─ 视角建模（perspective，按线按需：客观/真人/职业模板）          │
│                │                                                             │
│                ▼ 汇合到各任务线                                               │
│   {line}_agent（LLM 生成草稿）                                               │
│        │                                                                      │
│   {line}_supervisor（LLM 审核：approve/revise/reject）                       │
│        │ 条件路由                                                             │
│        ├─ 通过 ──► render（程序拼装 / 模板填充 / 篇幅自检）──► 产物          │
│        ├─ 返工 ──► revision（带审核意见重试，次数上限）                      │
│        └─ 降级 ──► fallback（确定性兜底，不依赖 LLM）                        │
│                                                                              │
│  输出：run_streaming 流式事件（chunk / done）——各线 producer 并行，Queue 合并 │
└──────────────┬─────────────────────────────────────────────────────────────┘
               ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                          能力层（tools/，跨域复用）                          │
│                                                                              │
│  · knowledge/    知识库：入库（切块+embedding+增量同步）→ 向量检索 → RAG 问答 │
│  · memory/       跨会话记忆：records(JSON 事实) + chromadb(向量) + 检索/写回  │
│  · monitor/      监控：LLM token / 缓存命中 / embedding / 按层耗时 / 库计数   │
│  · template_router/ 模板路由：占位符/格式规范/自然语言三类模板分派与编译       │
│  · outputs.py    产物落盘（HTML/MD/JSON）+ 思维导图/知识图谱导出              │
│  · llm_client/   LLM 客户端（HTTP/WebSocket）+ token/缓存/延迟统计            │
│  · perspective/  视角建模（跨域公共组件）+ profiles/（客观/职业模板画像库）      │
│  · supervisor/   全局监督标准（prompt 注入，不单独调 LLM）                    │
│  · scripts/      开发脚手架（sync_domain / register_domain / register_task） │
└──────────────┬─────────────────────────────────────────────────────────────┘
               ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                             数据层（按用户物理隔离）                          │
│                                                                              │
│  data/{user_id}/                                                            │
│   ├─ knowledge/   chromadb（向量库）+ catalogs/（知识目录 JSON）             │
│   ├─ memory/      records/{domain}/projects/{pid}/record.json + chromadb    │
│   ├─ profile/     {uid}.json 用户画像（对话提取：姓名/职业/偏好 + 模板关联）  │
│   └─ chat/        {session_id}/{history.jsonl, facts.json}                  │
│  output/{user_id}/{domain}/{task}/...（产物） + monitor/（监控 JSON）        │
└────────────────────────────────────────────────────────────────────────────┘
```
1. bootstrap/gradio → tools/runner.run(ctx, file, profile, user_id, ...)
2. runner 加载领域上下文（DomainContext：orchestrator/模型/注册表）
3. 构造 LangGraph 图：
   core（会议理解 + 视角建模）→ minutes_generation 线
4. graph.ainvoke 并行执行 core → agent 生成草稿 → supervisor 审核
   （不通过 → revision 返工 / fallback 兜底）
5. run_streaming 流式产出：render 层把草稿拼成最终文本/模板填充
6. 产物落盘（output/{uid}/meeting/minutes_generation/...）+ 监控采集
7. 记忆写回：persist（若带记忆）
```

关键设计：**图外渲染（produce_line）与图内审核分离**，渲染异常有兜底不阻断流程；
`_produce` 异常会进队列并打日志（不再静默卡死）。

---

## 4. 契约驱动开发：类定义契约 → 生成模型

系统采用**契约 → 生成**的开发模式：业务模型由 `contracts.py` 声明，`sync_domain.py`
一次性生成（生成区标注 "do not edit"）。

### 4.1 契约是什么

契约 = **对 LLM 结构化输出（及审核结论）的字段级声明**，三份职责合一：

1. **生成 prompt 的 JSON 模板**（`to_output_contract()` → 告诉 LLM 输出什么结构）
2. **生成 Python 数据类的字段定义**（`sync_domain` 消费 → `models.py`）
3. **运行期校验的规则来源**（`validate()` 浅校验：字段白名单 + 类型 + 枚举）

### 4.2 可继承的类体系（组成自己的契约）

**字段基类 `Field`**（声明"一个字段长什么样"）：

| 类 | 作用 | 校验规则 |
|---|---|---|
| `StrField` | 字符串字段 | 必须是 str（可空） |
| `EnumField` | 枚举字段 | 值必须在给定 choices 内 |
| `StrListField` | 字符串数组 | 必须是 list[str] |
| `ObjField` | 嵌套对象 | 必须是 dict |
| `ObjListField` | 嵌套对象数组 | 必须是 list[dict]，元素按子字段递归 |

**契约容器类**（组装字段，可继承）：

```python
# 1) 生成契约：声明"LLM 生成什么结构"
class MyLineContract(GenerationContract):     # 继承 GenerationContract
    fields = [
        StrField("title", "标题"),
        StrListField("items", "条目列表"),
        EnumField("level", ["S", "A", "B", "C"], "优先级"),
        ObjListField("details", [
            StrField("name", "名称"),
            StrField("note", "说明"),
        ]),
    ]
# sync_domain 据此生成 models.py 中的 MyLine 数据类 + validate()（浅校验）

# 2) 审核契约：声明"审核结论长什么样"
class MySupervisorContract(SupervisorContract):   # 继承 SupervisorContract
    decision = Decision(choices=["approve", "revise", "reject"])
    feedback = Feedback(...)     # 返工意见（字段白名单/非空规则）
    checks = [Check("facts", "是否锚定原文"), ...]   # 审核维度
# 类定义时自动注册 {线名大写}_SUPERVISOR_OUTPUT_CONTRACT 常量
```

### 4.3 严格校验的三层

```
第一层 浅校验（生成区 validate）：
  tools/validation.py：_exact_fields（字段白名单，多余字段报错）
                        _string / _string_list / _choice / _review_check / _action
第二层 语义校验（审核结论）：
  validate_supervisor_semantics：decision 合法 / feedback 字段白名单 /
                                  reject 必须有意见等
第三层 领域后处理归一化（如 catalog）：
  normalize_catalog_enums：中英枚举映射、数值钳制到合法范围
  （LLM 偶发输出"概念"而非 concept、越界数值 → 归一到标准值）
```

### 4.4 生成与校验闭环

```bash
python tools/scripts/sync_domain.py --write    # 生成全部生成区（models.py）
python tools/scripts/sync_domain.py --check    # 校验生成区与契约一致（CI 用）
```

- 运行时 `client.structured(prompt, user, MyLine, MyLineContract.to_output_contract())`
  → 返回 `MyLine` 实例（经 validate 浅校验）；非法输出走 `schema_repair` 修复或降级
- 契约即文档：字段的 desc 会进入 prompt，约束 LLM 的输出语义

---

## 5. 领域生成（register_domain）

新建一个领域（如 meeting / notes）由脚本脚手架完成：

```bash
python tools/scripts/register_domain.py --domain english
```

自动生成：
```
domain/english/
├── __init__.py / models.py / orchestrator.py / factory.py / domain_config.py
├── english_core/         # 领域核心理解（可选）
├── tasks/                # 任务线目录
└── samples/              # 样例输入
```

然后内部调用 `sync_domain` 填充生成区。领域通过 `domain_config.py` 声明
`STATE_CLASS / LINE_CN_NAMES / 注册表`，编排层通用逻辑在 `tools/domain_engine.py`
（领域只覆写钩子，如 `_shared_context` / `_build_core`）。

---

## 6. 任务线生成（register_task）

在领域内新增一条任务线：

```bash
python tools/scripts/register_task.py --domain meeting --task risk --name "风险分析"
```

自动创建（不覆盖已有代码）：
```
domain/meeting/tasks/risk/
├── contracts.py    # 生成契约 + 审核契约
├── prompts.py      # 系统提示（生成/审核）
├── steps/
│   ├── agent.py        # 生成节点（LLM → 草稿）
│   ├── supervisor.py   # 审核节点（LLM → 通过/返工/拒绝）
│   └── render.py       # 渲染节点（程序拼装/模板填充）
└── __init__.py
```

- 任务线在 `TASK_LINES` 注册表声明（agent_attr/supervisor_attr/empty_draft 等）
- **同构节点工厂**：`_make_agent_node / _make_supervisor_node / _make_route`
  从注册表生成 LangGraph 节点，新线无需手写图样板
- 可选择 `kind`：`llm_document`（LLM 生成）/ `llm_extract` / `deterministic_pipeline`（纯程序）

---

## 7. 图编排（LangGraph）

- **core 层**：共享节点（会议理解/笔记理解 + 视角建模），按领域/任务按需构建
  （如 notes 的 library/catalog/checklist 不建视角建模、不消费视角——省时省 token）
- **任务线**：`agent → supervisor → 条件路由（通过/返工/降级）`
- **状态**：TypedDict 共享（transcript / user / perspective_profile / lines / templates…）
- **流式**：`run_streaming` 并行启动各线 producer，通过 asyncio.Queue 合并逐块推送
- **异常兜底**：core/agent 异常 → 空草稿 + quality_degraded；producer 异常 → 日志 + 队列终止

---

## 7.5 输出模板路由（tools/template_router）

用 `--{线名}_template` 指定某条线的渲染模板后，系统自动**判型**并按最优路径处理。模板分为三类：

| 类型 | 识别特征 | 处理方式 | fill_mode |
|---|---|---|---|
| **占位符模板** | 含 `[占位描述]`（`\[([^\[\]]+)\]`） | 固定文字**逐字符保留**，LLM 只填占位符 → 程序化组装 | `assemble` |
| **格式规范模板** | 格式说明 + 输入/输出示例（如 JSON 数组） | 指令/示例分离，示例作 few-shot，LLM 自由渲染 | `freeform` |
| **自然语言描述** | 无占位符的自然语言（如"第一行是标题，括号里跟时间和人物"） | LLM 先**编译**成占位符模板 → 人可编辑预览 → 确认后填充 | `assemble`（编译后） |

**判型与分派**（`detect_template_kind`）：
```
自然语言描述 → 无 [占位符] → natural
含 [占位符]  → placeholder（默认按占位符处理；有示例标记 → spec）
```

- **占位符路径**：`fill_placeholder_template` 让 LLM 只输出字段 JSON（`{"fields": {"占位": "内容"}}`），
  程序按占位符顺序组装正文——LLM 不直接写全文，结构由模板保证
- **自然语言路径**：`maybe_compile_natural_template` 先让 LLM 把自然语言描述编译成占位符模板；
  用户可在 Web 端编辑（`preview_to_readable` / `readable_to_template` 双向转换），确认后再填充——
  防止用户改过的模板被重新编译回首稿
- **环境开关**：`TEMPLATE_ROUTER=off` 一键关闭路由，回退旧行为；任何判型/填充异常回退旧路径

**渲染后的强执行**（`tools/hard_execution.py` + `_gate`，`fill_mode` 演进）：
```
freeform（LLM 渲染）
  → 字数预算检查（全文「合计约 N 字」/ 段落级）：超限 → 压缩修订（repair），过短 → 扩写
  → 表格行数按置信度取舍（「约 N 行」→ 保高置信行）、空表写占位行、粘连行修复
  → 门禁（gate）：残留占位符 / 固定文字丢失 / 空表 → 标记硬伤，尝试 repair
  → 仍超限 → 句子级截断兜底（保完整句）
```
- 三类失败回退：占位符填充失败 → 走 LLM 渲染；门禁不过 → 尝试修复（最多两轮）；最终不过 → 该线降级
- 输出附只读校验：残留占位符 / JSON 合法性 / 行数（记录到 `render_gate_ok` / `render_gate_issues`）

---

## 8. 记忆系统（tools/memory）

```
data/{user_id}/memory/
├── records/{domain}/projects/{project_id}/record.json   # 事实本体（人可读 JSON）
│     └─ history.jsonl                                    # 每次运行的场次历史
└── chromadb/                                            # 向量索引（可从 records 重建）
```

### 8.1 写入闭环（一次带记忆的任务）

```
resolve（绑定/新建档案）
  → materialize（初始化档案结构）
  → merge（把 决策/风险/待办/未决/议题 合并进档案，run_count+1，events 追加）
  → persist（写回 record.json + 向量同步到 chromadb）
```

### 8.2 会议记忆的检索（resolve / inject 时）

会议记忆检索是**「实体规则 + 向量语义」双通道**：

```
输入（本次会议原文）
  │
  ├─ 通道① 实体召回（build_entity_recall，确定性规则）
  │    从原文提取实体（人名/项目名/关键词）→ 与已有档案的 project_key/别名/实体
  │    做规则匹配打分（强命中/弱命中）→ 唯一达标才绑定
  │
  └─ 通道② 向量语义（_semantic_hits / search_entries）
       原文 embedding → chroma 查询 → 命中该项目历史条目
       （目的/议题/决策/风险 等，带 seq/title/at/etype/score）
  │
  └─ 合并 → 注入历史（inject_meeting）：
       强相关（语义分高/实体强命中）→ 详细注入
       弱相关 → 概要注入
       均不可用 → 不注入（零记忆场景）
```

- 向量检索入口：`search_projects`（档案级，按 owner 隔离）→ `search_entries`（条目级）
- 记忆检索**不消耗 LLM**（纯向量/规则），成本来自 embedding（独立通道）

### 8.3 与知识库检索的差异

| 维度 | 会议记忆（memory） | 知识库（knowledge） |
|---|---|---|
| 检索对象 | 历史会议档案（结构化：决策/风险/议题） | 资料文档块（笔记/课件/讲义） |
| 组织单位 | user 下的 project（档案）→ 条目 | user 下的 subject（学科）→ 块 |
| 主通道 | **实体规则 + 向量语义**双通道 | **向量检索**（chroma query） |
| 用途 | 任务注入上下文 / 聊天"我记得…" | RAG 问答 / 目录骨架 / 复习清单 |
| 输出 | 注入文本（带场次/来源标注） | 上下文块 + 出处（source 文件名） |

---

## 9. 知识库与 RAG（tools/knowledge）

```
data/{user_id}/knowledge/chromadb/   # 每用户独立向量库（subject 走 metadata where 过滤）
```

### 9.1 入库（library）

```
文件（txt/md/docx/pptx/pdf/xlsx）
  → process_file 切块（chunk_size + overlap）
  → 增量同步 sync_file（按 source 的 md5 计算 added/removed/unchanged）
  → embedding（硅基流动，独立通道）→ chroma upsert
```

### 9.2 检索（search）

```
question + user_id + subject
  → _scope 行级路由（固定统一库 + metadata where：owner=user_id, subject=subject）
  → embedding(query) → chroma query（cosine）→ top-k 块
  → SearchResult{text, metadata(source 文件名), score}
```

- **行级隔离**：owner（user）必过滤；subject（学科）可选过滤——同一用户多学科互不干扰
- **无库降级**：用户首次访问（库未创建）返回空，不抛异常

### 9.3 RAG 问答（ask / 聊天）

```
question
  → search 检索 top-k 块
  → _build_context 拼成【参考资料】（带来源标注）
  → LLM：system("严格根据参考资料回答") + user(context + question)
  → answer + sources（出处：文档名/片段）
```

- **出处纪律**：回答只标注"实际引用"的来源（**序号回指** `[1]`→资料块，文件名/标题原文兜底）；
  未命中按问题性质分流（知识导向如实说未找到 / 开放型自由简短回答）
- 聊天场景（chat/）：检索门控 → 多源聚合（知识库 + 会议记忆）→ 统一上下文 → LLM

---

## 10. 聊天组件（chat/）

终端与未来 Web 共用的多源问答。一次提问走「**检索门控 → 多源检索 → 出处标注 → 画像更新**」：

```
chat/
├── gate.py      # 检索门控：规则短路（寒暄/自我表露）→ LLM 门控（need_memory / need_knowledge 分开）
├── sources.py   # 多源检索聚合（知识库 + 会议记忆，按 need_* 按需跳过）
├── chat.py      # ChatSession：多轮历史 + 会话记忆(facts) + 用户画像 + 持久化
├── profile.py   # 用户画像档案：data/{uid}/profile/{uid}.json（对话提取 + base_template 关联职业模板）
├── prompts.py   # 系统提示（人设 + 三区规则 + 序号标注 + 纯文本输出）
├── store.py     # data/{uid}/chat/{sid}/{history.jsonl, facts.json}
└── cli.py       # python chat/cli.py --user 1 --subject math
```

### 10.0 检索门控（chat/gate.py）——"不是检索到了就展示，而是确实需要才检索"：
- 规则短路（零成本）：寒暄短句（"你好"）、自我表露（"我喜欢先给结论再说"）→ 直接不检索
- LLM 门控：`GateDecision{need_memory, need_knowledge, reason, confidence}` **分开判断**，
  只检索需要的源（问会议只搜记忆、问知识点只搜知识库），省一半检索
- 保守兜底：门控失败 / 低置信 → 默认两者都检索（宁可多搜，不漏检）

### 10.1 用户画像设计（chat/profile.py）

**动机**：chat 需要跨会话知道"用户是谁、是什么样的人"（姓名/职业/偏好），
且职业信息应能复用公共职业模板，而不是每个用户复制一份。

**数据模型**（`data/{uid}/profile/{uid}.json`，位置即身份——放在用户目录下天然是"用户本人"，无需类型标签）：

```json
{
  "user_id": "1",
  "name": "侯业飞",
  "role": "开发人员",
  "base_template": "developer",      // 可选：命中的公共职业模板（perspective/profiles/role/）
  "traits": {"做事风格": "先看结论"},  // 偏好/性格，固定三键
  "facts": [                          // 事实留痕：field+value 去重，值变更追加历史
    {"field": "role", "value": "开发人员", "updated_at": "..."}
  ],
  "updated_at": "..."
}
```

**提取链路**（每轮问答后，失败静默不阻断聊天）：
```
对话（最近 6 条用户消息）
  → client.structured（ChatProfileUpdate 契约：name / role / traits）
  → 校验白名单：traits 键只允许 做事风格 / 沟通偏好 / 性格（LLM 输出其它键丢弃）
  → merge_profile 合并：
      name / role 非空则覆盖；traits 键值合并；
      facts 按 field+value 全表去重（同值刷新时间、不同值追加记录变更史）
  → 落盘 data/{uid}/profile/{uid}.json
```

**职业模板两层关联**（模板存指针，不复制内容）：
| 环节 | 函数 | 行为 |
|---|---|---|
| 写入 | `match_role_template(role)` | 提取到"开发人员"→ 遍历 `perspective/profiles/role/*_profile.json`，按模板 `name`/`role`/文件名**包含匹配** → 命中写 `base_template: "developer"` |
| 读取 | `resolve_user_profile(uid)` | `base_template` 存在 → 加载 `developer_profile.json` 做基底，**用户字段覆盖模板**（一份模板可被任意多用户引用，改模板一次全体生效） |

**消费路径**：
- 新开/回到会话：`ChatSession.__init__` 先 `ensure_profile`（建文件 + user_id 字段），`ask()` 前注入【用户画像】区（name/role/traits）
- 画像只**内部使用**（影响回答风格），不主动说"我记得你"（除非用户询问）
- 未来任务线（会议纪要等）可复用 `resolve_user_profile` 加载职业化画像

**与会话级 facts 的分工**：
| 维度 | facts.json（会话级） | profile.json（用户级） |
|---|---|---|
| 提取 | 规则正则（"我是…"） | LLM structured（契约 + 白名单） |
| 作用域 | 当前 session | 跨 session 全局 |
| 内容 | 姓名/角色（轻量） | 姓名/角色/偏好/模板关联（完整画像） |

**边界与演进**：`facts` 带时间戳可追溯"用户信息何时变更"；`traits` 固定键保证存储稳定；
后续可扩充字段（如用户显式声明的 override 区，AI 推断不覆盖）。

### 10.2 出处机制
- 展示格式：`[文件名]`（知识库）、`{标题} · 第N场（{YYYY-MM-DD} 记录）`（会议记忆），每条一行
- 匹配以**序号回指**为主（回答里的 `[1][2]` → 对应资料块）、文件名/标题原文兜底——
  不依赖 LLM 复述文件名（英文文件名 / 简称场景下可靠，历史问题根因即此）
- 展示层剥离：正文中的序号标注与 Markdown 符号（`**`、`` ` ``、`#`）在展示前去掉，
  数学闭区间 `[0,1]`、乘号 `a*b` 不受影响

**"我是谁"记忆**：会话级规则提取（姓名/角色）存 facts.json；跨会话身份走用户画像（profile）
- **出处只展示"回答实际引用"的来源**（序号回指 + 原文兜底，避免检索命中但未使用的噪声出处）


---

## 11. 知识库存储与产物输出：按用户隔离

所有用户数据按 **user 顶层物理隔离**（多租户安全边界：删用户 = 删目录，误操作不串数据）。

```
data/{user_id}/
├── knowledge/                 # 知识库存储（该用户全部学科）
│   ├── chromadb/              #   向量库：每用户独立 chroma（subject 走 metadata where）
│   └── catalogs/              #   知识目录 JSON（如 1__math.json → 7 章）
├── memory/                    # 记忆存储
│   ├── records/{domain}/projects/{pid}/record.json + history.jsonl
│   └── chromadb/              #   记忆向量（每用户独立）
├── profile/{uid}.json         # 用户画像档案（对话提取：姓名/职业/偏好 + base_template）
└── chat/{session_id}/         # 聊天会话
    ├── history.jsonl
    └── facts.json

output/{user_id}/              # 产物与监控输出
├── {domain}/{task}/...        #   各线产物（HTML/MD/JSON/思维导图/图谱）
└── monitor/{task}_{ts}.json   #   任务监控
```

### 11.1 隔离的实现机制（路由函数）

| 数据 | 路由依据 | 实现 |
|---|---|---|
| 知识库向量 | user_id → `data/{uid}/knowledge/chromadb` | `persist_dir_for_user()` / `KnowledgeTool(user_id=...)` |
| 知识目录 | collection 名 `{uid}__{subject}` 解析 user | `_catalog_dir_for()` → `data/{uid}/knowledge/catalogs` |
| 记忆记录 | 函数级 user_id | `store.user_dir()` → `data/{uid}/memory/records/...` |
| 记忆向量 | user_id | `get_embedder(user_id)` 每用户实例 → `data/{uid}/memory/chromadb` |
| 聊天会话 | user_id + session_id | `chat.store.session_dir()` → `data/{uid}/chat/{sid}/` |
| 用户画像 | user_id → `data/{uid}/profile/` | `chat.profile.profile_path()` |
| 任务产物 | `DomainContext.user_id` | `task_output_dir()` → `output/{uid}/{domain}/{line}` |
| 监控 | user_id | `TaskMonitor(out_dir=output/{uid}/monitor)` |

### 11.2 隔离的关键设计

- **两层隔离叠加**：user 是**物理隔离**（目录/库分家）；subject 是**逻辑隔离**（同库内 metadata `where` 过滤）——知识库/记忆/聊天/产物四类数据互不串扰
- **user 名字安全化**：路径段经 `safe_id()`（非法字符替换、长度截断、Windows 保留名处理）
- **无 user 兼容**：不传 user_id 的旧调用回退旧路径（`output/{domain}/...`），不影响历史行为
- **Web 同步**：gradio 的产物列表/监控读取按当前 user 过滤（`_output_files`/`_latest_monitor` 带 user_id）
- **迁移能力**：脚本可将旧统一库按 `owner` 元数据拆到各用户目录（复用原 embeddings，不重新编码）

### 11.3 用户隔离的价值

1. **多租户安全**：A 用户无法检索/看到 B 用户的资料、记忆、产物
2. **生命周期管理**：删除用户 = 删除 `data/{uid}/` + `output/{uid}/`，干净彻底
3. **可迁移可备份**：目录级备份/迁移，不依赖数据库导出

---

## 12. 监控（tools/monitor）

每次任务产出监控 JSON（`output/{uid}/monitor/{task}_{ts}.json`）：

- LLM：prompt/completion token、**服务端缓存命中**（cache_hit_tokens，DeepSeek 自动缓存）
- **embedding**：调用次数 / 输入 token（与 LLM 分开统计）
- 按层耗时：core/agent/supervisor/render 各层延迟
- 知识库 / 记忆侧计数：入库块数、检索次数、记忆注入/写回、记忆向量命中

---

## 13. 测试

```
tests/
├── test_merge.py         # 目录合并（占位保留/新章 added/ID 分配）
├── test_distribution.py  # 重点分布（Top10+其他/总和 100%）
├── test_compact.py       # 审核草稿压缩（结构保留/截断/计数）
├── test_agent_stub.py    # LLM 桩测（FakeClient 隔离，测后处理链路）
└── test_syntax_310.py    # 全库 Python 3.10 语法兼容（拦截 f-string 类事故）
```

```bash
python -m pytest        # 21 个用例，秒级，零网络
```

- 纯函数单测 + **LLM 桩测**（FakeClient 返回预置响应，测 merge/归一化/组装逻辑）
- 3.10 语法兼容检查：上次 f-string 反斜杠导致的「任务静默卡死」事故由此类测试拦截

---

## 14. 目录结构速览

```
bootstrap.py / gradio_app.py / chat/      入口（CLI / Web / 终端问答；chat 含 gate.py / profile.py）
domain/{meeting,notes}/                   领域（orchestrator/factory/tasks/…）
tools/
  domain_engine.py / runner.py / outputs.py / io.py
  knowledge/ memory/ monitor/ template_router/
  scripts/{sync_domain,register_domain,register_task}.py
llm_client/  perspective/  supervisor/  schema_repair/
perspective/profiles/                    跨域公共画像（客观 + role/ 职业模板）
web/app.py + web/theme.py                 Gradio 界面
tests/                                     pytest（21 例）
data/{user_id}/…  output/{user_id}/…      用户数据与产物（隔离；含 profile/ 用户画像）
demo/ samples/                             示例数据（与业务代码解耦）
```
