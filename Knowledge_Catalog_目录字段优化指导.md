# Knowledge Catalog 字段优化指导

## 一、目标

在现有 Knowledge Catalog 基础上，新增少量长期稳定字段，使后续能够更稳定地生成：

- 分阶段复习路径
- 可执行任务卡
- 明确的过关标准
- 易错扫雷任务

核心原则：

> **Catalog 保存“这个知识通常应该怎么学”，老师本次重点决定“这次重点学什么、练什么”。**

不要把本次题量、考试时间、老师临时要求等 Session 信息永久写入 Knowledge Catalog。

---

## 二、现有字段继续保留

现有字段继续沿用，不新增语义重复的评分字段：

- `importance`
- `difficulty`
- `teacher_emphasis`
- `exam_signal`
- `foundational_level`
- `knowledge_type`
- `prerequisites`
- `related_points`
- `note_coverage`
- `note_missing_items`
- `evidence`
- `confidence`

这些字段主要用于判断：

- 哪些知识重要
- 哪些知识较难
- 哪些属于基础前置
- 哪些存在考试信号
- 哪些需要优先复习
- 学生笔记有哪些缺口

---

## 三、新增 4 个字段

### 1. `practice_type`

表示这个 KP 最适合通过什么方式进行复习和巩固。

推荐枚举：

```text
recall          记忆 / 复述
distinguish     概念辨析
calculate       计算训练
prove           证明训练
apply           应用训练
choose_method   方法选择
mixed           综合训练
```

允许一个 KP 对应多个类型。

例如：

```json
"practice_type": [
  "calculate",
  "choose_method"
]
```

作用：

> **决定行动清单中的“具体怎么复习”。**

生成规则：

- 概念、定义类知识优先使用 `recall` / `distinguish`
- 计算方法类知识优先使用 `calculate` / `choose_method`
- 定理证明类知识根据内容使用 `prove` / `apply`
- 应用型知识优先使用 `apply`
- 同时包含多种明显训练方式时使用多个标签或 `mixed`

不要因为知识点重要就默认设置为 `calculate`。

---

### 2. `completion_criteria`

表示这个 KP 达到什么能力水平，可以认为本轮复习基本完成。

不要保存完整自然语言句子，只保存能力标签。

推荐枚举：

```text
can_recall
can_explain
can_distinguish
can_apply
can_choose_method
can_solve_standard
can_solve_variant
can_prove
```

允许一个 KP 对应多个能力目标。

例如：

```json
"completion_criteria": [
  "can_choose_method",
  "can_solve_standard"
]
```

作用：

> **决定行动清单中的“过关标准”。**

生成规则：

- 定义 / 公式：优先考虑 `can_recall`
- 概念：优先考虑 `can_explain` / `can_distinguish`
- 方法：优先考虑 `can_choose_method` / `can_solve_standard`
- 定理：根据用途考虑 `can_explain` / `can_apply` / `can_prove`
- 综合应用：可考虑 `can_solve_variant`

只选择真正符合该 KP 学习目标的能力标签，不要机械添加所有能力。

---

### 3. `learning_role`

表示这个知识点在整个学习链路中的稳定角色。

推荐枚举：

```text
foundation       基础前置
core_concept     核心概念
core_method      核心方法
application      应用知识
integration      综合连接
```

每个 KP 原则上选择一个主要角色。

作用：

> **配合 `prerequisites` 和 `foundational_level`，帮助生成合理的分阶段复习路径。**

生成规则：

- 大量其他知识依赖该 KP：优先 `foundation`
- 属于课程核心定义 / 核心思想：`core_concept`
- 属于反复使用的核心解题方法：`core_method`
- 主要用于解决具体问题：`application`
- 主要承担多个知识点联合、综合使用：`integration`

注意：

不要在 Catalog 中保存：

```text
第一阶段
第二阶段
第三阶段
补前置
攻核心
快速过
```

这些属于本次 Review Session 动态生成结果，不是知识本身长期属性。

---

### 4. `risk_tags`

表示这个 KP 本身常见的学习或答题风险。

推荐枚举：

```text
condition_check      使用条件易漏
concept_confusion    概念易混
formula_misuse       公式误用
method_selection     方法选择错误
calculation_error    计算易错
proof_format         证明书写问题
boundary_case        边界 / 特殊情况遗漏
```

允许多个标签。

例如：

```json
"risk_tags": [
  "condition_check",
  "method_selection"
]
```

作用：

> **决定行动清单中的“易错扫雷任务”。**

生成规则：

- 有明确适用条件：考虑 `condition_check`
- 与其他概念容易混淆：考虑 `concept_confusion`
- 公式存在常见误用：考虑 `formula_misuse`
- 多种方法容易选错：考虑 `method_selection`
- 计算过程本身容易出错：考虑 `calculation_error`
- 涉及证明规范：考虑 `proof_format`
- 容易遗漏特殊情况 / 边界：考虑 `boundary_case`

注意：

`risk_tags` 表示知识本身的典型风险，不代表学生一定已经犯过这些错误。

---

## 四、推荐 KP 结构

在原有 KP 结构中增加以下字段：

```json
{
  "id": "kp_xxx",
  "name": "知识点名称",

  "knowledge_type": "method",

  "importance": 5,
  "difficulty": 4,
  "teacher_emphasis": 2,
  "exam_signal": "strong",
  "foundational_level": 4,

  "prerequisites": [],
  "related_points": [],

  "note_coverage": "partial",
  "note_missing_items": [],

  "practice_type": [
    "calculate",
    "choose_method"
  ],

  "completion_criteria": [
    "can_choose_method",
    "can_solve_standard"
  ],

  "learning_role": "core_method",

  "risk_tags": [
    "condition_check",
    "method_selection"
  ],

  "evidence": [],
  "confidence": 0.95
}
```

---

## 五、这些字段如何辅助行动清单生成

### 1. 决定先复习什么

使用：

```text
prerequisites
+
foundational_level
+
learning_role
```

用于建立合理知识顺序。

目标：

> 先补真正必要的前置，再进入本次老师强调的核心内容。

---

### 2. 决定哪些是本次重点

使用：

```text
本次老师重点
+
importance
+
exam_signal
+
difficulty
```

动态生成本次 Review Session 的 S / A / B / C 优先级。

本次老师重点属于动态信号，不写入长期学习角色。

---

### 3. 决定具体怎么复习

使用：

```text
practice_type
```

将 KP 转换成具体动作：

```text
recall
→ 复述 / 默写

distinguish
→ 概念对比 / 判断辨析

calculate
→ 计算训练

prove
→ 证明训练

choose_method
→ 方法识别与选择

apply
→ 应用训练

mixed
→ 综合训练
```

---

### 4. 决定什么时候算完成

使用：

```text
completion_criteria
```

生成可勾选的过关标准，例如：

```text
□ 能复述核心内容
□ 能解释适用条件
□ 能区分易混概念
□ 能判断应该使用哪种方法
□ 能独立完成标准题
□ 能完成证明过程
```

行动清单不要只写“复习某知识点”，应尽量生成明确的完成条件。

---

### 5. 决定最后扫什么雷

使用：

```text
risk_tags
+
老师本次易错提醒
+
note_missing_items
```

生成专项扫雷任务，例如：

```text
□ 检查使用条件是否遗漏
□ 区分容易混淆的概念
□ 检查方法选择是否正确
□ 检查公式是否误用
□ 检查证明书写是否完整
```

---

## 六、Session 信息不要写进 Catalog

以下信息属于本次 Review Session：

```text
本次要求做多少题
本次考试时间
本次老师特别强调的题型
本次证明书写要求
本次临时复习安排
本次特殊提醒
```

生成 Review Checklist 时再动态抽取，例如：

```text
session_emphasis
session_focus_items
session_practice_count
session_exam_signal
session_error_signal
session_special_requirement
```

整体关系：

```text
Knowledge Catalog
        +
老师本次重点
        ↓
Review Session
        ↓
行动清单
```

---

## 七、行动清单最终生成目标

行动清单不要生成大段泛化建议。

建议生成：

```text
阶段路线
+
任务卡
+
过关标准
+
扫雷任务
```

内部结构建议：

```text
阶段
├── 阶段目标
├── KP
│   ├── 本次优先级
│   ├── 具体任务
│   ├── 过关标准
│   └── 风险提醒
└── 阶段完成条件
```

字段映射：

```text
learning_role
→ 辅助决定阶段归属

practice_type
→ 决定具体任务形式

completion_criteria
→ 决定过关标准

risk_tags
→ 决定扫雷任务
```

---

## 八、核心约束

1. 只新增 `practice_type`、`completion_criteria`、`learning_role`、`risk_tags` 四个字段。
2. 不新增语义重复的优先级、投入度、训练强度字段。
3. 新字段必须描述长期稳定的知识属性。
4. 不要把本次题量、时间、老师临时要求写入 Catalog。
5. `practice_type` 只回答“怎么练”。
6. `completion_criteria` 只回答“达到什么能力算完成”。
7. `learning_role` 只回答“知识在学习链路中是什么角色”。
8. `risk_tags` 只回答“知识本身有哪些典型风险”。
9. 所有字段都应基于现有资料、老师信息和知识结构判断，无法确认时不要强行填充。
10. 不要因为新增字段而改变原有 Chapter / Topic / KP / Item 层级结构。
11. 增量更新时优先补充已有 KP 的新字段，不随意创建重复 KP。
12. 原有稳定 ID 必须继续保持。

---

## 九、最终原则

新增字段不是为了让 Knowledge Catalog 变复杂，而是建立下面这层转换能力：

```text
Knowledge Point
      ↓
怎么练
      ↓
练到什么程度
      ↓
它在学习链路中扮演什么角色
      ↓
重点防什么问题
      ↓
可执行复习任务
```

最终目标：

> **让 Knowledge Catalog 在保持“知识结构索引”稳定性的同时，为后续 Review Checklist 生成阶段路线、任务卡、过关标准和扫雷任务提供结构化依据。**
