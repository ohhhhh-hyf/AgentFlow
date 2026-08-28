# 笔记域复习清单分档与知识可视化优化指导

> 范围：notes 域三条链路：`library` 知识入库、`catalog` 知识目录、`checklist` 复习清单。  
> 目标：不改变后端请求字段和返回字段，只优化内部逻辑、HTML/Markdown 产物与 Agent 输入策略。

## 1. 当前链路定位

### 1.1 知识入库 library

`library` 是资料底座，不承担复习优先级判断。

当前职责：

- 接收文档、图片、OCR 结果并入库；
- 生成 chunk、metadata、source/page/heading 等检索信息；
- 提取本次新增的可编目知识单元；
- 输出入库报告。

保持原则：

- 不在 `library` 阶段生成 S/A/B/C；
- 不在 `library` 阶段生成复习路线；
- 可以继续增强 chunk 的结构化 metadata，例如 `content_fingerprint`、`heading_path`、`source_role`，供 catalog/checklist 零成本复用。

### 1.2 知识目录 catalog

`catalog` 是长期知识结构，不应保存“本次复习优先级”。

当前核心字段：

- `importance`：长期重要性，1-5；
- `difficulty`：长期难度，1-5；
- `foundational_level`：基础程度，1-5；
- `teacher_emphasis`：老师强调程度，0-3；
- `exam_signal`：考试信号，`none / weak / medium / strong`；
- `review_weight`：程序计算的复习权重，0-1；
- `teacher_focus_items` / `teacher_evidence`：老师重点命中依据；
- `sources` / `source_chunk_ids` / `evidence`：知识库溯源。

保持原则：

- `catalog` 不直接产生 S/A/B/C；
- `importance / difficulty / review_weight` 是后续 checklist 分档的基础；
- 不传老师重点文本时，`teacher_emphasis=0`，不生成老师依据；
- 传老师重点文本时，通过 KP 名称、别名、knowledge_items 匹配老师原话，回填 `teacher_emphasis / teacher_focus_items / teacher_evidence`；
- 老师重点只能提高目录信号，不能凭空生成资料里没有的长期知识点。

### 1.3 复习清单 checklist

`checklist` 是本次 session 的复习计划，S/A/B 应该只在这里生成。

当前逻辑：

- 无老师重点文本：按目录 `importance / review_weight` 激活 KP，只出 S/A/B；
- 有老师重点文本：老师命中目录 KP 后生成 session 信号，再分 S/A/B/C；
- 当前分档以分位为主：前 20% S、20%-60% A、60%-90% B、后 10% C 或 DROP；
- 当前饼图展示优先画 S/A，较小扇区按章合并。

优化方向：

- 保留“本次优先级”的概念，但改为动态评分与动态数量控制；
- 对用户主展示只保留 S/A/B，C 最多作为内部补充或折叠区；
- 移除饼图，用更适合学习决策的结构总览替代。

## 2. 当前问题

### 2.1 分档过度依赖固定分位

固定分位在目录规模变化时容易失真：

- 小目录会被硬切出 S/A/B，显得过度设计；
- 大目录会产生过多重点，清单膨胀；
- 同一门课不同章节颗粒度不同，细拆章节天然占更多位置；
- 老师重点文本强弱不同，但分位切割无法充分表达“老师明确强调”和“老师只是顺带提到”的差异。

### 2.2 C 档用户语义不稳定

无老师重点时，C 没有清晰语义，因此当前代码已经在无老师场景中把后 10% 设为 DROP。

有老师重点时，C 表示“补充了解”，但如果直接主展示，容易让用户误解为“老师点了但不重要”。因此建议：

- 用户主流程只展示 S/A/B；
- C 可作为内部缓冲档；
- 如果保留 C，只放在折叠的“补充了解”区，不进入核心总览。

### 2.3 饼图不适合复习决策

饼图适合展示占比，不适合展示学习优先级。

当前 checklist 更需要回答：

- 今天先复习哪些？
- 哪些是老师明确强调？
- 哪些是目录长期重要？
- 哪些只是前置补齐？
- 这些点属于哪一章、哪一个知识块？

饼图的问题：

- 长知识点名称可读性差；
- 扇区不利于精确比较；
- 无法表达复习顺序；
- 层级结构弱；
- 小扇区即使按章合并，仍然像统计图，不像学习路线图。

## 3. 新的 S/A/B 动态分档设计

### 3.1 分档语义

建议把用户可见档位统一为三档：

- S：核心突破。本次必须优先掌握，数量少，内容厚。
- A：重点巩固。本次需要认真复习，内容中等偏厚。
- B：简要过一遍。用于结构补齐、前置补齐、低风险了解。

C 的建议定位：

- 不作为用户主展示档位；
- 有老师重点文本时，可作为内部缓冲；
- 渲染时默认折叠为“补充了解”，或合并进 B 的尾部；
- 无老师重点文本时不生成 C。

### 3.2 session_score

分档前先为每个激活 KP 计算 `session_score`。这个字段可以只存在于内部 row，不进入外部返回字段。

推荐评分：

```text
session_score =
  importance_score
  + review_weight_score
  + teacher_mention_score
  + teacher_strength_score
  + exam_signal_score
  + weakness_score
  + prerequisite_bonus
  + practice_signal_bonus
  - low_value_penalty
```

建议权重：

```text
importance_score        = importance * 10
review_weight_score     = round(review_weight * 30)
teacher_mention_score   = 12 if 被老师点名 else 0
teacher_strength_score  = session_emphasis * 10
exam_signal_score       = none 0 / weak 6 / medium 12 / strong 20
weakness_score          = min(15, note_missing_items 数量 * 5)
prerequisite_bonus      = 8 if 是 S/A 的前置知识 else 0
practice_signal_bonus   = 6 if 老师给出题量/书写要求 else 0
low_value_penalty       = 10 if importance <= 2 且未被老师点名 else 0
```

设计原则：

- 老师信号很重要，但不能完全压过目录结构；
- 目录长期重要性是底盘；
- `review_weight` 负责融合难度、考试信号、依赖关系；
- 前置知识可以进 B，但不应轻易挤进 S；
- 无依据的老师强信号不能生成。

### 3.3 无老师重点文本时的分档

输入依据：

- `importance`
- `difficulty`
- `review_weight`
- `exam_signal`
- `note_missing_items`
- `prerequisites / related_points`

激活规则：

```text
激活条件：
importance >= 3
或 review_weight >= 0.4
或 exam_signal in {medium, strong}
```

分档建议：

```text
S：
  session_score >= 70
  或 importance >= 5 且 review_weight >= 0.65

A：
  session_score >= 50
  或 importance >= 4
  或 review_weight >= 0.55

B：
  已激活但未进入 S/A
  或 S/A 的必要前置知识
```

数量控制：

```text
激活数 <= 8：
  S 1-2 个
  A 2-3 个
  其余 B

激活数 9-18：
  S 2-4 个
  A 4-6 个
  B 6-8 个

激活数 > 18：
  S 最多 10 个
  A 最多 10 个
  B 最多 10 个
```

硬约束：

- 无老师文本时不生成 C；
- `importance < 3` 且 `review_weight < 0.4` 不进入清单；
- S 至少 1 个，除非目录为空；
- S 不超过总激活数的 25%；
- B 超限时直接丢弃最低分，不降为 C。

### 3.4 有老师重点文本时的分档

输入依据：

- 老师原话命中句；
- `session_emphasis`
- `session_exam_signal`
- `session_quotes`
- 目录长期字段；
- 笔记缺项和题量/书写要求。

激活规则：

```text
激活条件：
被老师点名
或 importance >= 3
或 review_weight >= 0.4
```

分档建议：

```text
S：
  老师强强调 + importance >= 4
  或 session_exam_signal == strong 且 importance >= 4
  或 session_score >= 80

A：
  被老师点名且 session_emphasis >= 2
  或 medium/strong 考试信号
  或 session_score >= 58

B：
  老师轻提
  或 S/A 的前置知识
  或目录长期重要但本轮未点名
```

内部 C：

```text
C：
  低分但被激活的补充项
  或 B 超限后的尾部
```

用户展示建议：

- S/A/B 主展示；
- C 不进入总览；
- C 可折叠为“补充了解”，或者合并到 B 尾部；
- 老师点名的 KP 最低为 B，不进入隐藏 C；
- 老师原话无法匹配目录 KP 时进入 `uncertain_quotes`，不生成卡片。

数量控制：

```text
S：建议 3-6 个，最多 10 个
A：建议 5-10 个，最多 10 个
B：建议 6-10 个，最多 10 个
C：内部缓冲，不主展示
```

硬约束：

- 老师强词不能单独决定 S，必须结合目录重要性或考试信号；
- `importance >= 5` 且老师强强调，可强制 S；
- 被老师点名但目录低重要，只能进入 A/B，除非有 strong exam signal；
- S/A 的前置知识补进 B，不抢 S/A 名额；
- 相似 KP 同档重复时，保留高分项，其余降档或回卷。

## 4. 取消饼图后的展示设计

### 4.1 页面模块替换

把当前“复习重点分布”的饼图区域改为“本次复习结构总览”。

推荐结构：

```text
一、全局导航
  1. 本次复习结构总览
     - 横向条形图
     - 语义回卷 Treemap
  2. 思维导图
  3. 考点知识图谱
  4. 动态表格
```

### 4.2 横向条形图

横向条形图回答：

```text
本次最值得复习的知识块是什么？
```

展示字段：

- 知识块名称；
- S/A/B 标签；
- review value；
- 老师命中标识；
- 所属章节；
- 简短原因。

示例：

```text
两个重要极限      ██████████  S  老师强强调 / 重要性5
导数定义          ████████    A  基础前置 / 重要性4
函数连续性质      ██████      B  结构补齐
```

排序：

```text
S → A → B
同档内按 session_score 降序
```

交互：

- 点击条形项过滤表格；
- 点击章节标签过滤同章；
- hover 显示 score 来源。

### 4.3 Semantic Roll-up Treemap

Treemap 回答：

```text
这些重点在整个知识结构里属于哪里？
```

不要固定展示某一层级，采用 `semantic_rollup_knowledge_visualization_design.md` 中的策略：

- 节点太粗：向下展开；
- 节点太碎：向上回卷；
- 优先回卷为有语义的父节点；
- 避免匿名“其他”；
- 最终可见节点控制在 4-8 个左右。

推荐参数：

```text
TARGET_MIN = 4
TARGET_IDEAL = 6
TARGET_MAX = 8
MIN_SLICE_RATIO = 0.05
MAX_SLICE_RATIO = 0.45
MAX_BAR_ITEMS = 12
MAX_TREEMAP_VISIBLE_LEAVES = 20
```

Treemap 节点字段：

```json
{
  "id": "kp_or_rollup_id",
  "name": "知识块名称",
  "value": 76,
  "ratio": 0.21,
  "depth": 2,
  "parent_id": "chapter_id",
  "source_node_ids": ["kp_001", "kp_002"],
  "aggregation_type": "none | rollup | partial_rollup",
  "session_priority": "S | A | B",
  "reason": "老师强强调 / 目录重要"
}
```

### 4.4 value 定义

不要使用“一个 KP = 一个单位”。

推荐：

```text
review_value = session_score
```

如果需要表达预计时间，可以派生：

```text
recommended_review_minutes =
  S: 18-25 分钟
  A: 10-15 分钟
  B: 4-8 分钟
```

Treemap 和条形图可以共用同一份聚合结果：

```text
leaf_value = session_score
parent_value = sum(children_value)
```

## 5. 数据结构建议

不改外部响应字段，只在 checklist draft 内部增加展示数据。

建议新增内部字段：

```json
{
  "review_overview": {
    "bar_items": [],
    "treemap": {},
    "rollup_items": []
  }
}
```

保留现有字段：

- `cards`
- `phases`
- `strategy`
- `uncertain_quotes`
- `checklist_html`
- `mindmap_outline`

兼容策略：

- Markdown 可直接渲染条形列表；
- HTML 使用 `review_overview.bar_items / treemap`；
- 旧的 `distribution()` 可以逐步废弃，先内部停用，不影响返回结构。

## 6. Agent 输入策略

### 6.1 checklist Agent 不负责分档

分档应由程序完成，Agent 只负责写卡片内容。

Agent 输入应包含：

- 已激活 KP；
- 已计算好的 `session_priority`；
- `session_score` 的短原因；
- 老师命中原话；
- 知识库摘录；
- 笔记缺项。

Agent 不应该：

- 重新决定 S/A/B；
- 创造目录里不存在的 KP；
- 把未匹配老师原话硬塞进正文；
- 在无老师文本时写“老师强调”。

### 6.2 传给 Agent 的字段精简

每个 KP 建议只传：

```text
id
name
chapter/topic
knowledge_items
importance/difficulty/review_weight
session_priority
session_reason
session_quotes
evidence 摘录
note_missing_items
practice_type
completion_criteria
```

不必传：

- 全量 catalog；
- 全量知识库原文；
- 与该 KP 无关的 source；
- 前端图表数据。

### 6.3 策略与阶段尽量程序化

`strategy` 和 `phases` 应优先由程序根据 S/A/B、difficulty、practice_type、completion_criteria 组装。

LLM 只做轻量润色：

- 把复习顺序事实写成自然语言；
- 不新增顺序；
- 不暴露 S/A/B/KP 等内部术语给用户。

## 7. 落地步骤建议

### Step 1：重构分档函数

位置建议：

- `domain/notes/tasks/checklist/select.py`

动作：

- 新增 `_session_score(row)`；
- 用动态阈值替代固定分位主逻辑；
- 保留数量封顶；
- 无老师只出 S/A/B；
- 有老师允许内部 C，但用户主展示隐藏或折叠。

### Step 2：生成 review_overview

位置建议：

- `domain/notes/tasks/checklist/assemble.py`

动作：

- 生成 bar items；
- 基于 catalog path 和 cards 生成 rollup tree；
- 调用 semantic rollup 得到 treemap items。

### Step 3：替换 checklist HTML 的饼图区域

位置建议：

- `domain/notes/tasks/checklist/display.py`

动作：

- 删除或停用 pie HTML；
- 新增横向条形图；
- 新增 Treemap 容器；
- 保留表格筛选、排序、掌握度；
- 条形图/Treemap 点击后过滤表格。

### Step 4：Markdown 降级展示

Markdown 不需要复杂图，只输出：

```text
## 本次复习结构总览
- 核心：...
- 重点：...
- 简要：...

### 优先复习排序
1. ...
2. ...
```

### Step 5：prompt 精简

位置建议：

- `domain/notes/tasks/checklist/prompts.py`

动作：

- 明确 S/A/B 已由程序给定；
- Agent 只写卡片内容；
- 不要求 Agent 解释图表；
- 不要求 Agent 重新判断优先级。

## 8. 质量验收标准

### 8.1 无老师重点文本

应满足：

- 不出现老师原话；
- 不出现 `uncertain_quotes`；
- 不出现用户主展示 C；
- S/A/B 数量合理，不膨胀；
- 高 importance / 高 review_weight 能进入 S/A；
- 低价值 KP 不进入清单。

### 8.2 有老师重点文本

应满足：

- 老师强强调的高重要 KP 能进入 S；
- 老师点名 KP 最低进入 B；
- 未匹配老师原话进入 `uncertain_quotes`；
- 前置知识能补入 B；
- C 不干扰主学习路线；
- 页面能看出“老师重点集中在哪些知识块”。

### 8.3 展示体验

应满足：

- 不再展示饼图；
- 条形图能清楚表达排序；
- Treemap 能表达章节结构；
- 小节点优先语义回卷，不出现大量“其他”；
- 表格筛选与掌握度继续可用；
- HTML 和 Markdown 都能独立阅读。

## 9. 核心判断

这次优化的关键不是把饼图换成另一个图，而是把复习清单从“占比统计”改成“学习决策面板”。

推荐最终原则：

```text
library 负责资料事实；
catalog 负责长期知识结构；
checklist 负责本次复习决策；
S/A/B 是 session 级优先级；
可视化展示复习价值和目录位置，不展示抽象占比。
```
