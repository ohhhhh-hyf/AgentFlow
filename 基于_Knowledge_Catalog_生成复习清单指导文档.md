# 基于 Knowledge Catalog 生成复习清单指导文档

## 一、目标

用户只需要输入：

> **老师本次重点文本**

系统基于已有 **Knowledge Catalog** 生成本次复习清单。

核心原则：

> **Catalog 定知识范围，老师重点激活本次复习内容，目录字段决定轻重与顺序。**

不要重新从原始资料中发现知识点，也不要重新构建目录。

---

## 二、输入

### 1. Knowledge Catalog

提供长期知识底座：

- Chapter / Topic / Knowledge Point / Knowledge Item
- importance
- difficulty
- knowledge_type
- foundational_level
- prerequisites
- related_points
- note_coverage
- note_missing_items
- 历史老师重点等目录属性

### 2. 本次老师重点文本

这是唯一需要用户再次输入的内容。

主要用于识别：

- 本次重点 KP
- 本次重点 Item
- 老师明确提到的难点
- 考试相关信号
- 易错提醒
- 多知识点组合关系

---

## 三、核心处理流程

```text
老师重点文本
      ↓
重点信息抽取
      ↓
与 Knowledge Catalog 匹配
      ↓
生成本次 Review View
      ↓
KP 筛选与排序
      ↓
生成复习清单
```

---

## 四、老师重点映射

老师文本优先匹配已有目录节点。

处理顺序：

```text
老师原话
   ↓
匹配 Knowledge Point
   ↓
进一步匹配 Knowledge Item
```

不要因为老师使用了不同说法就创建新的 KP。

无法准确匹配时，应标记不确定，而不是强行建立新节点。

---

## 五、生成本次 Review View

不要直接修改长期 Knowledge Catalog。

为本次复习临时生成：

```text
session_emphasis
session_focus_items
session_exam_signal
session_difficulty_signal
session_error_signal
session_related_points
session_priority
```

其中：

- `session_emphasis`：老师本次强调程度
- `session_focus_items`：老师具体强调的 Item
- `session_exam_signal`：本次考试相关信号
- `session_error_signal`：老师明确提醒的易错内容
- `session_priority`：本次最终复习优先级

本次老师重点优先于目录中的历史老师重点。

---

## 六、KP 筛选

不是所有 KP 都进入详细复习内容。

建议分为：

```text
S：核心展开
A：重点展开
B：简要展示
C：只保留在全局结构中
```

排序综合考虑：

- session_emphasis
- importance
- exam_signal
- difficulty
- foundational_level
- prerequisites
- note_missing_items

原则：

> **老师重点决定复习目标，知识依赖决定复习顺序。**

---

## 七、复习清单结构

### 一、全局导航

#### 1. 复习重点分布

基于本次入选 KP 的权重聚合生成。

输出：

- 饼图
- 重点 KP 表格

不要称为“考试分值占比”，应称为：

> **复习重点分布**

#### 2. 思维导图

直接基于 Catalog 裁剪生成：

```text
Chapter
→ Topic
→ 本次相关 KP
→ 老师重点 Item
```

只展示本次复习相关知识结构。

#### 3. 考点知识图谱

基于：

- prerequisites
- related_points
- 老师本次提到的组合关系

生成局部知识关系图。

主要关系：

```text
前置
关联
替代
配合
易混
组合
```

---

### 二、核心知识点

每个 S / A 级 KP 生成一张复习卡片：

```text
优先级 ｜ 考法预判

知识点讲解

方法步骤

易错提醒
```

---

## 八、知识点卡片生成原则

### 优先级

主要由：

```text
Catalog 长期属性
+
本次老师重点
```

共同决定。

### 考法预判

优先依据：

1. 老师本次明确提到的考法
2. session_exam_signal
3. Catalog 中已有考试信号

没有依据时不要写：

- 必考
- 具体考试概率

### 知识点讲解

围绕：

```text
knowledge_items
+
session_focus_items
+
note_missing_items
```

组织内容。

内部优先级：

> **必须知道 → 老师重点 → 学生笔记缺项**

### 方法步骤

根据 `knowledge_type` 动态生成。

- method / application：生成解题步骤
- theorem / concept：生成判断或应用流程
- formula：生成使用流程和条件检查

不要强迫所有 KP 使用相同模板。

### 易错提醒

优先级：

1. 老师本次明确提醒
2. Catalog 已有易错信息
3. 学生笔记缺失 Item
4. 知识本身的使用条件和限制

没有依据的提醒不要强行生成。

---

## 九、行动清单

### 1. 分阶段复习路径

依据：

```text
session_priority
+
prerequisites
+
foundational_level
+
note_missing_items
```

生成。

每个阶段包含：

- 复习目标
- 对应 KP / Item
- 完成标准

### 2. 复习策略

根据本次整体状态动态生成，例如：

- 老师重点是否集中
- 高难度 KP 数量
- 基础前置是否较多
- 学生笔记缺项是否明显

不要生成泛化的“多看书、多做题”等建议。

---

## 十、核心约束

1. Knowledge Catalog 是知识范围唯一来源。
2. 不重新发现或创建 KP。
3. 用户本次只输入老师重点文本。
4. 老师重点优先匹配 KP，再定位 Item。
5. 本次信号生成临时 Review View，不随意修改长期 Catalog。
6. 本次老师重点优先于历史老师重点。
7. 先筛选 KP，再生成详细内容。
8. 思维导图来自 Catalog Tree。
9. 知识图谱来自 prerequisites / related_points。
10. 学生笔记只用于个性化补漏，不直接判断掌握程度。
11. 没有证据时不生成“必考”或具体考试概率。
12. 复习路径必须同时考虑重点程度与知识依赖。

---

## 十一、最终原则

整个流程可以概括为：

> **老师重点作为本次 Query，激活 Knowledge Catalog 中相关 KP 和 Item。**

然后：

```text
Catalog 定范围
↓
老师重点定本次侧重
↓
目录字段定优先级与顺序
↓
生成核心知识内容
↓
聚合为全局导航和行动清单
```

最终目标：

> **让学生只需输入老师最后一节课的重点内容，就能基于已有 Knowledge Catalog 快速生成一份有重点、有结构、有个性化的复习清单。**
