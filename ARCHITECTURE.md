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
│  · perspective/  视角建模（跨域公共组件，三类画像）                           │
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

- **出处纪律**：回答只标注"实际引用"的来源（文件名/日期出现在回答中才亮）；
  未命中按问题性质分流（知识导向如实说未找到 / 开放型自由简短回答）
- 聊天场景（chat/）：多源聚合 = 知识库检索 + 会议记忆检索 → 统一上下文 → LLM

---

## 10. 聊天组件（chat/）

终端与未来 Web 共用的多源问答：

```
chat/
├── sources.py   # 多源检索聚合（知识库 + 会议记忆）
├── chat.py      # ChatSession：多轮历史 + 会话记忆(facts) + 持久化
├── prompts.py   # 系统提示（三区规则：会话内记忆不标出处 / 检索命中才标）
├── store.py     # data/{uid}/chat/{sid}/{history.jsonl, facts.json}
└── cli.py       # python -m chat.cli --user 1 --subject math
```

- **"我是谁"记忆**：从自我介绍提取姓名/角色（规则+排除疑问词），注入后续上下文；
  跨进程用同 `--session` 恢复
- **出处只展示"回答实际引用"的来源**（文件名/日期/标题出现在回答中才亮）

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
bootstrap.py / gradio_app.py / chat/      入口（CLI / Web / 终端问答）
domain/{meeting,notes}/                   领域（orchestrator/factory/tasks/…）
tools/
  domain_engine.py / runner.py / outputs.py / io.py
  knowledge/ memory/ monitor/ template_router/
  scripts/{sync_domain,register_domain,register_task}.py
llm_client/  perspective/  supervisor/  schema_repair/
web/app.py + web/theme.py                 Gradio 界面
tests/                                     pytest（21 例）
data/{user_id}/…  output/{user_id}/…      用户数据与产物（隔离）
demo/ samples/                             示例数据（与业务代码解耦）
```
