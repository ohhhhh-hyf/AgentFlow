# AgentFlow 任务线说明（领域 × 任务）

两个领域共 **12 条任务线**，全部走同一条流水线：**核心理解 → 生成草稿 → 审核（approve/revise/reject，返工 ≤1 次）→ 渲染 → 落盘**，线与线并行、互不阻塞。审核不通过或异常时走**确定性降级**（不依赖 LLM）。

- 领域：`meeting`（会议）、`notes`（笔记）
- 入口：`python bootstrap.py --domain <域> --task <线> [--file ...] [--profile ...]`
- 产物：`output/{user_id}/{domain}/{task}/`（不传 user_id 时 `output/{domain}/{task}/`）

---

## 一、会议域（meeting）

共享底座：**会议理解**（会议目的 / 议题 / 决策 / 未决 / 风险，LLM 结构化提取）+ **视角建模**（客观全员 / 职业模板 / 真人个人）。

### 1. minutes_generation（纪要）
- **目的**：生成会议纪要（客观全量 / 个人视角裁剪）
- **输入**：会议原文（`.txt`）；可选用户画像、历史记忆注入
- **产出**：`headline` + 概述 / 关键决策 / 执行要点 / 风险阻塞 / 未决问题 / 历史对比（7 个结构化字段）
- **关键机制**：
  - **上游硬对齐**：决策/风险/未决字段强制取自会议理解（客观全量拷贝；职业/真人下采，只删不改）
  - 历史记忆注入时输出「与历史对比」（对照来源场次）
  - 支持输出模板（`--minutes_generation_template`）
- **示例**：`python bootstrap.py --task minutes_generation --file meeting_all.txt`

### 2. action_items（待办）
- **目的**：抽取行动项，分「我负责 / 委派他人 / 未分配」三组
- **输入**：会议原文
- **产出**：结构化待办列表（task / owner / deadline / priority / status / evidence / confidence）
- **关键机制**：客观视角 = 全员已分配 + 未分配；个人视角 = 本人职责相关；证据锚定原文
- **示例**：`python bootstrap.py --task action_items`

### 3. risk（风险分析）
- **目的**：提取风险与阻塞（等级 / 相关方 / 影响 / 应对）
- **输入**：会议原文
- **产出**：结构化风险列表（risk / severity / impact / owner / mitigation）
- **示例**：`python bootstrap.py --task risk`

### 4. mindmap（思维导图）
- **目的**：把会议内容整理成 Markdown 大纲，导出可交互思维导图
- **输入**：会议原文
- **产出**：`mindmap_时间戳.html`（markmap，离线单文件）+ `mindmap_时间戳.png`（Playwright 截图，可选）
- **关键机制**：大纲净化（表格转要点、公共前缀合并）；npx/playwright 缺失自动降级（只出 HTML 或跳过）
- **示例**：`python bootstrap.py --task mindmap`

### 5. multi_styles（多样式纪要）
- **目的**：按指定**组织模式**重写纪要，同一场会用不同叙事结构
- **模式**（`--multi_styles_mode`）：`time` 时间线 / `logic` 逻辑总分 / `causal` 因果推导 / `party` 主体责权 / `urgency` 决策时效
- **产出**：`mode` + `title` + `sections`（组织段落）+ `summary`
- **关键机制**：不同模式用不同骨架 prompt；草稿需通过结构门禁（sections 非空）才放行
- **示例**：`python bootstrap.py --task multi_styles --multi_styles_mode causal`

### 6. minutes_trace（溯源纪要）
- **目的**：生成纪要并**逐条对齐原文**（每句可溯源），供核对
- **输入**：会议原文 + 可选**溯源侧车文件**（`user_keypoints.txt` / `user_notes.txt`，会议文件同目录自动带）
- **产出**：`scene`（场景判定）+ `minutes_md`（正文）+ `alignments`（原文对齐条目）
- **关键机制**：`deterministic_pipeline`（程序落钉）+ sidecar；对齐不编出处——原文没有的不写
- **示例**：`python bootstrap.py --task minutes_trace`

---

## 二、笔记域（notes）

共享底座：**笔记理解**（主题 / 章节 / 术语 / 待澄清问题）。`library`/`catalog`/`checklist` 不建视角建模（客观内容处理）。

### 7. knowledge_graph（知识图谱）
- **目的**：从笔记提取概念节点与关系边，导出网状知识图谱 + 学习地图
- **输入**：笔记原文（`.txt`）
- **产出**：`knowledge_graph_时间戳.svg`（Graphviz）/ `.html`（Cytoscape 交互）/ 学习地图 `.md`
- **关键机制**：节点/边锚定原文 + evidence；悬空边自动过滤；同 user+subject **增量合并**图谱（记忆）；SVG 依赖系统 Graphviz，缺失时 HTML 仍生成
- **示例**：`python bootstrap.py --domain notes --task knowledge_graph --file student_math_notes.txt`

### 8. review（笔记审查）
- **目的**：审查笔记正确性，产出问题清单 + 订正后的笔记
- **输入**：笔记原文
- **产出**：`result_时间戳.md` / `.html`（审查报告）+ `result_*_corrected.md`（订正稿）；报告中的主张**挂知识库出处**
- **关键机制**：逐条主张溯源（quote → 知识库命中）；订正稿由用户确认后才接受（Web 端 rewrite 按钮）
- **示例**：`python bootstrap.py --domain notes --task review`

### 9. quiz（自测题）
- **目的**：基于笔记出推理题，并可从**高中题库**检索真题（按难度/题型）
- **输入**：笔记原文 + 可选 `--difficulty` / `--qtype`（搜题）
- **产出**：`result_时间戳.md` / `.html`（题干 + 参考得分点）；题库命中附真题
- **关键机制**：先对齐笔记知识点反推年级/版本 → 决定题库范围；`--level`/`--grade`/`--edition` 已弃用（自动反推）
- **示例**：`python bootstrap.py --domain notes --task quiz --file student_math_notes.txt --difficulty 适中 --qtype 单选题`

### 10. library（资料入库）
- **目的**：把 PPT/PDF/docx/xlsx/txt 切块 + embedding 写入知识库，报告**知识增量与冲突**
- **输入**：`--file` 可传多份文件
- **产出**：`result_时间戳.md` / `.html`（增量 / 冲突 / 每文件 added/removed/unchanged）
- **关键机制**：md5 增量同步（同文件更新只动变化块）；按 `user_id + subject` 行级入库；`deterministic_pipeline`（不调 LLM）
- **示例**：`python bootstrap.py --domain notes --task library --file a.pptx --file b.pdf --user_id 1 --subject 数学`

### 11. catalog（知识目录）
- **目的**：从知识库资料（课件/讲义/笔记 + 老师划重点）生成学科知识目录，支持**增量更新**
- **输入**：`--user_id` + `--subject`（必填，定位知识库）；可选老师划重点文本 `--file`
- **产出**：`result_时间戳.md` / `.html`（目录树 + 变更清单）；目录本体存 `data/{uid}/knowledge/catalogs/{学科}.json`
- **关键机制**：**首次 build / 后续 incremental_update**（ID 稳定、占位节点保留旧内容、新章 added）；枚举归一化（中文枚举→标准值）；文档角色分类（课件=骨架、笔记=覆盖、老师=重点）
- **示例**：`python bootstrap.py --domain notes --task catalog --user_id 1 --subject 数学 --file teacher_focus_limits.txt`

### 12. checklist（复习清单）
- **目的**：基于已生成的目录 + 老师本次划重点，生成本次复习卡片清单
- **输入**：`--user_id` + `--subject`（必填）+ 老师划重点文本 `--file`（必填）
- **产出**：`result_时间戳.md` / `.html`（复习卡片 S/A/B/C 分级 + 复习策略/阶段）
- **关键机制**：老师文本**激活**目录知识点（无匹配不编造）；卡片分优先级；主张溯源（老师原话 > 知识库 > 笔记，库空留空不编来源）
- **示例**：`python bootstrap.py --domain notes --task checklist --user_id 1 --subject 数学 --file teacher_focus_limits.txt`

---

## 三、共同机制（所有线通用）

| 机制 | 说明 |
|---|---|
| 审核返工 | 每线 supervisor 判 approve / revise / reject；revise 带反馈重跑（≤1 次），reject / 超限 → 确定性降级 |
| 确定性降级 | `FallbackRules` 声明式拼装（sections / join / 免责声明），不依赖 LLM，图异常也兜底 |
| 契约驱动 | 每条线 `contracts.py` 声明生成/审核契约，`sync_domain.py` 生成模型 + 校验；`--check` 校验一致性 |
| 模板路由 | `--{线名}_template`：占位符 / 格式规范 / 自然语言三类模板自动判型处理 |
| 视角系统 | `--profile` 客观（默认）/ 职业模板（`perspective/profiles/role/`）/ 真人个人，按线消费 |
| 记忆/知识库 | 纪要/多样式/知识图谱带记忆（跨场注入 + 写回）；chat 按 user 检索知识库 + 会议记忆 |
| 用户隔离 | 产物/数据按 `user_id` 顶层物理隔离（`output/{uid}/`、`data/{uid}/`） |

## 四、输出速查

| 任务线 | 主要产物 |
|---|---|
| minutes_generation / action_items / risk / multi_styles / minutes_trace | `report_时间戳.json` + `result_时间戳.md` |
| mindmap | `mindmap_时间戳.html` / `.png` |
| knowledge_graph | `knowledge_graph_时间戳.svg` / `.html` / 学习地图 `.md` |
| review | `result_时间戳.md` / `.html`（+ 订正稿） |
| quiz | `result_时间戳.md` / `.html` |
| library | `result_时间戳.md` / `.html`（增量报告） |
| catalog | `result_时间戳.md` / `.html` + `data/{uid}/knowledge/catalogs/` |
| checklist | `result_时间戳.md` / `.html` |
