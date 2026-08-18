# Knowledge Catalog 优化指导清单

## 一、目标

优化现有知识目录，使其成为后续生成复习清单的统一知识底座。

当前阶段： - 只生成和优化目录。 -
不生成完整知识讲解、考法预判、解题步骤、易错提醒、复习路径或复习策略。 -
但必须提前保存后续生成这些内容所需要的结构化字段。

核心原则：

> 目录既是一棵稳定的知识树，也是一份后续复习清单生成所需的结构化索引。

------------------------------------------------------------------------

## 二、目录结构

统一使用：

``` text
Course
└── Chapter
    └── Topic
        └── Knowledge Point
            └── Knowledge Item
```

-   **Chapter**：章节
-   **Topic**：知识主题
-   **Knowledge Point（KP）**：核心知识点，后续复习清单的基本单位
-   **Knowledge Item**：KP 内部的公式、条件、性质、分类、细节

### 粒度原则

1.  同层 KP 粒度尽量一致。
2.  条件、公式细节、分类、性质通常作为 Knowledge Item。
3.  同一个 KP 只保留一个主节点，其他位置通过关联引用，不重复创建。
4.  同义知识点合并，其他名称保存到 `aliases`。

例如：

``` text
KP：等价无穷小
├── Item：常用等价关系
├── Item：使用条件
└── Item：替换规则
```

不要把"替换规则"再次创建成独立 KP。

------------------------------------------------------------------------

## 三、每个 KP 建议保留的字段

### 1. 基础结构

-   `id`：稳定唯一 ID
-   `name`：标准名称
-   `aliases`：其他名称/同义名称
-   `chapter`
-   `topic`
-   `knowledge_items`

### 2. `importance`：重要程度

``` text
1 普通
2 次重点
3 重要
4 很重要
5 核心
```

用于后续重点分布、优先级和核心知识点筛选。

### 3. `difficulty`：难度

``` text
1 简单
2 较简单
3 中等
4 较难
5 很难
```

重要程度和难度必须分开。

### 4. `teacher_emphasis`：老师强调程度

必须依据老师重点文本判断。

``` text
0 未提及
1 提及
2 明确强调
3 反复/强烈强调
```

### 5. `knowledge_type`：知识类型

``` text
concept       概念型
formula       公式型
theorem       定理型
method        方法型
application   应用型
mixed         综合型
```

用于后续决定知识点的讲解方式。

### 6. `foundational_level`：基础性

表示该 KP 对其他知识的前置作用。

``` text
1 很少作为前置
2 较弱
3 一般
4 重要前置
5 核心基础
```

### 7. `exam_signal`：考试信号

表示现有材料中是否存在明显考试相关信号。

``` text
none
weak
medium
strong
```

只能根据老师重点或课程资料中的明确信息判断，不生成具体考试概率，不无依据判断"必考"。

### 8. `teacher_focus_items`：老师重点强调的 Item

例如：

``` json
["使用条件", "替换规则"]
```

用于后续决定知识讲解中哪些细节需要重点展开。

### 9. 学生笔记覆盖字段

-   `note_coverage`
-   `note_covered_items`
-   `note_missing_items`

`note_coverage`：

``` text
none
mentioned
partial
detailed
```

只判断笔记覆盖情况，不根据笔记直接推断学生是否掌握。

### 10. `prerequisites`：前置知识

记录学习该 KP 前最好掌握的其他 KP。

用于后续生成合理复习顺序。

### 11. `related_points`：关联知识

关系尽量使用固定类型：

``` text
alternative       替代方法
used_with         配合使用
easily_confused   容易混淆
derived_from      推导关系
```

用于后续知识图谱、方法选择和易混知识提示。

### 12. `evidence`：来源证据

重要标签尽量保留依据，来源包括：

-   课程资料
-   老师重点文本
-   学生笔记

特别是
`teacher_emphasis`、`exam_signal`、`teacher_focus_items`、`note_coverage`
等字段，不应无依据生成。

### 13. `confidence`：置信度

对 AI 不确定的节点、映射或属性保存置信度。低置信度内容不要强行确定。

------------------------------------------------------------------------

## 四、字段与后续复习清单的关系

  字段                    后续主要用途
  ----------------------- --------------------
  `importance`            优先级、重点分布
  `difficulty`            复习投入、讲解深度
  `teacher_emphasis`      优先级、老师重点
  `knowledge_type`        决定知识点讲解方式
  `foundational_level`    复习顺序
  `exam_signal`           考法预判
  `teacher_focus_items`   知识讲解重点
  `note_coverage`         个性化程度
  `note_missing_items`    个性化提醒
  `prerequisites`         分阶段复习路径
  `related_points`        知识图谱、方法选择
  `evidence`              防止无依据生成
  `confidence`            质量控制

------------------------------------------------------------------------

## 五、目录阶段暂时不要生成

不要提前生成：

-   完整知识点讲解
-   完整考法预判
-   完整解题步骤
-   完整易错提醒
-   复习优先级正文
-   复习路径
-   复习策略

目录只负责保存未来生成这些内容所需的结构化依据。

------------------------------------------------------------------------

## 六、推荐 KP 数据结构

``` json
{
  "id": "kp_001",
  "name": "等价无穷小",
  "aliases": [],
  "chapter": "极限与连续",
  "topic": "极限计算",
  "knowledge_type": "method",

  "knowledge_items": [
    "常用等价关系",
    "使用条件",
    "替换规则"
  ],

  "importance": 5,
  "difficulty": 3,
  "teacher_emphasis": 3,
  "foundational_level": 3,
  "exam_signal": "strong",

  "teacher_focus_items": [
    "替换规则"
  ],

  "note_coverage": "partial",
  "note_covered_items": [
    "常用等价关系"
  ],
  "note_missing_items": [
    "使用条件"
  ],

  "prerequisites": [
    "无穷小"
  ],

  "related_points": [
    {
      "name": "洛必达法则",
      "relation": "alternative"
    }
  ],

  "evidence": [],
  "confidence": 0.95
}
```

------------------------------------------------------------------------

## 七、核心优化规则

1.  固定 `Course → Chapter → Topic → KP → Item` 层级。
2.  KP 是核心单位，同层 KP 粒度保持一致。
3.  条件、公式细节、分类、性质通常放入 Item，不要过度拆 KP。
4.  同一个 KP 只保留一个主节点，禁止重复。
5.  同义名称归一，其他名称保存到 `aliases`。
6.  重点、难度、老师强调程度分别判断。
7.  老师重点不仅匹配 KP，还要尽量定位到具体 Item。
8.  学生笔记只判断覆盖情况，不直接推断掌握程度。
9.  保存 `prerequisites`，为后续复习顺序做准备。
10. 保存 `related_points`，为后续知识图谱和方法选择做准备。
11. 重要判断尽量保留 `evidence`。
12. 不确定的信息降低 `confidence`，不要强行生成。

最终目标：

> **将 Knowledge Catalog
> 建设成后续复习清单生成的稳定、结构化知识底座。**
