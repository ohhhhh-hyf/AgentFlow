# Review Checklist 行动清单优化指导

## 一、目标

本次优化 **只针对“行动清单”模块**。

不修改：

- 全局导航
- 复习重点分布
- 思维导图
- 考点知识图谱
- 核心知识点卡片
- 老师重点映射逻辑
- KP 筛选与优先级逻辑

在原有行动清单基础上，新增利用 Knowledge Catalog 中的 4 个字段：

```text
practice_type
completion_criteria
learning_role
risk_tags
```

目标是把原来的：

> 分阶段复习路径 + 一段复习策略

升级为：

> **阶段路线 + 可执行任务卡 + 过关标准 + 扫雷任务**

避免生成大段、泛化、冷冰冰的复习建议。

---

## 二、行动清单的输入

行动清单生成时使用：

### 1. Review Session 动态信息

```text
session_priority
session_emphasis
session_focus_items
session_exam_signal
session_error_signal
session_practice_count
session_special_requirement
```

这些信息来自老师本次重点。

### 2. Knowledge Catalog 原有字段

```text
importance
difficulty
foundational_level
prerequisites
related_points
note_missing_items
```

### 3. Knowledge Catalog 新增字段

```text
practice_type
completion_criteria
learning_role
risk_tags
```

---

## 三、行动清单生成原则

核心原则：

> **老师重点决定“本次重点做什么”，知识依赖决定“先做什么”，目录新增字段决定“怎么做、做到什么程度、重点防什么”。**

字段职责必须明确：

```text
session_priority
→ 本次优先级

prerequisites + foundational_level + learning_role
→ 阶段与顺序

practice_type
→ 具体复习任务

completion_criteria
→ 过关标准

risk_tags + session_error_signal + note_missing_items
→ 扫雷任务
```

不要让 LLM 自由发挥整个行动清单结构。

---

# 四、行动清单最终结构

行动清单建议固定为 4 部分：

```text
1. 复习路线
2. 阶段任务
3. 扫雷清单
4. 老师本次提醒
```

其中“复习策略”不再单独生成大段文字。

原来的复习策略信息应尽量拆入：

- 阶段任务
- 具体任务要求
- 扫雷清单
- 老师提醒

---

# 五、1. 复习路线

## 目标

告诉学生：

> **先做什么 → 再做什么 → 最后做什么**

不要只输出文字段落。

建议输出阶段节点：

```text
阶段 1 → 阶段 2 → 阶段 3 → 阶段 4
```

阶段名称根据当前 KP 动态生成，不强制固定数量。

推荐阶段语义：

```text
补前置
攻核心
做应用
综合串联
扫雷补漏
考前检查
```

但不要机械要求每次全部出现。

---

## 阶段划分规则

优先使用：

```text
learning_role
+
prerequisites
+
foundational_level
+
session_priority
```

### `foundation`

优先进入：

```text
补前置
```

仅加入本次重点知识真正依赖的必要前置。

不要把所有基础知识都塞进去。

### `core_concept`

优先进入：

```text
攻核心
```

用于本次必须理解、辨析或掌握的核心概念。

### `core_method`

优先进入：

```text
攻核心
```

用于本次重点方法、计算、证明和方法选择。

### `application`

优先进入：

```text
做应用
```

### `integration`

优先进入：

```text
综合串联
```

### 风险较高或笔记缺项明显的 KP

可以进入：

```text
扫雷补漏
```

---

## 顺序规则

阶段顺序不能只按 S / A / B 优先级排序。

必须优先满足知识依赖。

例如：

```text
A → B → C
```

即使 C 是老师本次强重点，也应保证必要的 A、B 在前。

原则：

> **老师重点决定目标，知识依赖决定路线。**

---

# 六、2. 阶段任务

每个阶段下面不要只罗列：

```text
覆盖：KP A、KP B、KP C
```

应转换为真正的任务卡。

推荐结构：

```text
阶段名称

阶段目标：

任务 1
- 知识点：
- 本次优先级：
- 任务类型：
- 具体任务：
- 过关标准：
- 风险提醒：

任务 2
...
```

---

## 任务卡字段生成规则

### 1. 本次优先级

直接使用：

```text
session_priority
```

可展示：

```text
S 核心
A 重点
B 简要
```

行动清单原则上主要展开 S / A。

B 级只在必要前置或关联时进入。

---

### 2. 任务类型

由：

```text
practice_type
```

直接决定。

映射规则：

```text
recall
→ 记忆 / 复述任务

distinguish
→ 概念辨析任务

calculate
→ 计算训练任务

prove
→ 证明训练任务

apply
→ 应用任务

choose_method
→ 方法识别与选择任务

mixed
→ 综合任务
```

---

## 具体任务生成

具体任务不要泛化为：

```text
复习这个知识点
认真掌握
多做练习
重点理解
```

必须是动作表达。

例如根据标签生成：

```text
recall
→ 复述核心定义 / 默写关键公式

distinguish
→ 对比易混概念并说清判断依据

calculate
→ 完成典型计算流程

prove
→ 独立写出完整证明结构

choose_method
→ 根据题目特征判断应使用的方法

apply
→ 完成知识到具体问题的应用
```

如果老师明确给出本次题量：

```text
session_practice_count
```

则写入任务。

例如：

```text
完成 10 道对应训练题
```

如果老师未要求题量，不要自行编造固定题数。

---

# 七、3. 过关标准

过关标准主要来自：

```text
completion_criteria
```

不要让 LLM 临时编造模糊标准。

推荐映射：

```text
can_recall
→ 能独立复述 / 默写核心内容

can_explain
→ 能用自己的话解释核心原理和条件

can_distinguish
→ 能准确区分易混概念

can_apply
→ 能在典型场景中正确应用

can_choose_method
→ 能根据题目特征选择正确方法

can_solve_standard
→ 能独立完成标准题

can_solve_variant
→ 能处理常见变式

can_prove
→ 能独立写出完整证明过程
```

---

## 展示方式

建议以可勾选形式生成：

```text
过关标准

□ 能判断应该使用哪种方法
□ 能独立完成标准题
□ 能说明关键使用条件
```

不要只写：

> 掌握该知识点。

---

# 八、4. 扫雷清单

扫雷任务综合：

```text
risk_tags
+
session_error_signal
+
note_missing_items
```

优先级：

```text
老师本次明确提醒
>
Catalog risk_tags
>
学生笔记缺项
```

---

## `risk_tags` 映射

```text
condition_check
→ 检查是否遗漏使用条件

concept_confusion
→ 检查是否混淆相关概念

formula_misuse
→ 检查公式是否在错误场景使用

method_selection
→ 检查方法选择是否正确

calculation_error
→ 检查关键计算步骤

proof_format
→ 检查证明结构和书写规范

boundary_case
→ 检查边界和特殊情况
```

---

## 展示形式

建议集中生成：

```text
⚠️ 本轮重点扫雷

□ 使用前先检查条件
□ 不要混淆相关概念
□ 证明过程检查书写完整性
□ 检查特殊情况是否遗漏
```

不要把所有风险都重复塞进长段落。

---

# 九、老师本次提醒

原来“未匹配的老师原话”不要直接展示给用户。

对无法精确映射到某个 KP，但仍具有明确复习价值的老师信息，应整理为：

```text
老师本次提醒
```

例如老师明确提出：

- 题量要求
- 证明书写要求
- 选择填空重点
- 本次考试侧重
- 全局复习建议

都可以放入这里。

---

## 处理原则

能映射到具体 KP 的：

```text
进入对应任务卡
```

无法映射到单个 KP，但属于明确复习要求的：

```text
进入老师本次提醒
```

真正无法理解或没有行动价值的：

```text
后台保留为 unmatched
```

不要直接暴露“未匹配内容”给学生。

---

# 十、推荐最终展示形态

行动清单尽量呈现为：

```text
复习路线
↓
阶段任务卡
↓
过关标准
↓
扫雷清单
↓
老师提醒
```

示意结构：

```text
【复习路线】

① 补前置
      ↓
② 攻核心
      ↓
③ 做应用
      ↓
④ 扫雷补漏


【阶段 1 · 补前置】

任务 A
优先级：A
任务类型：概念复述

□ 复述核心定义
□ 说明使用条件

过关：
□ can_recall 对应标准
□ can_explain 对应标准


【阶段 2 · 攻核心】

任务 B
优先级：S
任务类型：计算 + 方法选择

□ 完成本次老师要求的训练
□ 判断不同题型应选什么方法

过关：
□ 能正确选方法
□ 能独立完成标准题

⚠️ 风险：
□ 检查使用条件
□ 检查方法误选


【本轮扫雷】

□ 概念易混
□ 条件遗漏
□ 证明书写


【老师本次提醒】

• ...
```

---

# 十一、不要生成的内容

行动清单中避免：

### 1. 大段复习策略

例如：

> 建议先把基础知识复习牢固，然后多做题，加强理解……

这种内容价值低。

### 2. 所有 KP 使用相同任务

不要全部生成：

```text
复习 + 做题 + 总结
```

必须根据 `practice_type` 区分。

### 3. 模糊完成标准

不要写：

```text
熟练掌握
基本理解
重点掌握
```

尽量转换为可验证能力。

### 4. 随意生成题量

只有老师明确提出题量时，才使用：

```text
session_practice_count
```

否则不要编造“做 5 道 / 10 道”。

### 5. 无视知识依赖直接按重要度排序

复习路线必须考虑：

```text
prerequisites
```

---

# 十二、行动清单生成逻辑总结

最终逻辑：

```text
老师本次重点
      ↓
session_priority
      ↓
确定本次目标 KP
      ↓
prerequisites + foundational_level + learning_role
      ↓
生成阶段与顺序
      ↓
practice_type
      ↓
生成具体任务
      ↓
completion_criteria
      ↓
生成过关标准
      ↓
risk_tags + session_error_signal + note_missing_items
      ↓
生成扫雷任务
```

---

# 十三、最终原则

本次优化只针对行动清单。

不要修改 Review Checklist 其他模块的结构和生成逻辑。

行动清单的目标从：

> **“告诉学生应该怎么复习”**

升级为：

> **“直接告诉学生下一步做什么，并且什么时候可以打勾完成。”**

四个新增 Catalog 字段的核心作用：

```text
learning_role
→ 决定阶段

practice_type
→ 决定任务

completion_criteria
→ 决定完成标准

risk_tags
→ 决定扫雷内容
```

最终输出应尽量做到：

> **有路线、能执行、可勾选、可验收。**
