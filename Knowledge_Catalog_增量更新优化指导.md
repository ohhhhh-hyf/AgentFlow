# Knowledge Catalog 增量更新优化指导

## 一、目标

当前知识库可能按章节分批上传，例如：

- 第一次只上传第一章
- 后续再上传第二章、第三章……

因此 Knowledge Catalog 不能每次都从零重新生成，而应支持：

> **基于已有目录进行增量更新。**

目标是保证：

- 已有目录结构稳定
- 已有节点 ID 不变
- 新章节可以持续追加
- 新资料优先匹配已有节点
- 只更新受影响的局部内容
- 避免重复节点和结构漂移

---

## 二、目录结构保持不变

统一使用：

```text
Course
└── Chapter
    └── Topic
        └── Knowledge Point
            └── Knowledge Item
```

Knowledge Point 仍然是后续复习清单的核心单位。

---

## 三、目录生成分为两种模式

### 1. 首次生成

当不存在历史目录时：

```text
new_material
    ↓
build_catalog
    ↓
Knowledge Catalog
```

生成完整基础目录。

---

### 2. 增量更新

当已经存在历史目录时：

```text
existing_catalog
      +
new_material
      +
teacher_text
      +
student_notes
      ↓
incremental_update
      ↓
updated_catalog
```

禁止默认重新从零生成整棵目录。

---

## 四、增量更新核心规则

### 1. 已有节点优先复用

新资料中的知识内容首先尝试匹配已有：

- Chapter
- Topic
- Knowledge Point
- Knowledge Item

匹配成功后直接更新已有节点，不创建重复节点。

---

### 2. 稳定 ID

每个节点必须拥有稳定唯一 ID：

```text
chapter_id
topic_id
kp_id
item_id
```

例如：

```text
kp_math_limit_001
```

后续即使名称从：

```text
洛必达定理
```

调整为：

```text
洛必达法则
```

也必须保持原 ID 不变。

旧名称可以保存到：

```text
aliases
```

---

### 3. 新内容按层级判断

新资料出现无法直接匹配的内容时，按以下顺序判断：

```text
已有节点的别名？
      ↓ 否
已有 KP 的 Knowledge Item？
      ↓ 否
新的 Knowledge Point？
      ↓ 否
新的 Topic？
      ↓ 否
新的 Chapter？
      ↓ 否
supplementary / unmatched
```

不要默认创建新的 KP。

---

### 4. 只修改相关局部

例如新增第二章资料时：

```text
高等数学
├── 第一章 极限与连续
│   └── 保持原结构
│
└── 第二章 导数与微分
    └── 新增内容
```

除非新资料提供了明确证据证明第一章存在错误，否则：

> **不得因为新增第二章而重新改写第一章目录。**

---

### 5. 已有节点只允许三类更新

对已有节点原则上只进行：

#### 补充

新增：

- Knowledge Item
- aliases
- evidence
- sources
- teacher_focus_items
- note coverage
- prerequisites
- related_points

#### 修正

只有发现明确结构错误时，才能修改：

- name
- parent
- knowledge_type
- 节点层级

修正后仍保留原 ID。

#### 合并

发现两个节点实际属于同一知识点时：

```text
KP_A
KP_B
  ↓
merge
  ↓
KP_A
```

其中一个作为主节点，另一个名称进入 `aliases`，并保留 merge 记录。

---

## 五、为增量更新新增的字段

建议在原 Knowledge Catalog 基础上增加以下字段。

### 1. `version`

目录版本号。

例如：

```json
"version": 3
```

每次成功增量更新后递增。

---

### 2. `created_at`

节点第一次创建时间。

---

### 3. `updated_at`

节点最后更新时间。

---

### 4. `source_documents`

记录该节点由哪些资料支持。

例如：

```json
"source_documents": [
  "第一章课件.pdf",
  "第二周课堂笔记.md"
]
```

---

### 5. `node_status`

节点状态：

```text
active
merged
deprecated
uncertain
```

正常节点使用：

```text
active
```

---

### 6. `change_type`

本次更新对节点进行了什么操作：

```text
unchanged
added
updated
merged
moved
```

主要用于审计和调试。

---

## 六、原有复习清单预留字段继续保留

每个 KP 继续维护：

```text
importance
difficulty
teacher_emphasis
knowledge_type
foundational_level
exam_signal

teacher_focus_items

note_coverage
note_covered_items
note_missing_items

prerequisites
related_points

evidence
confidence
```

增量更新时：

> 新资料只更新能够被新证据支持的字段。

例如第二章资料不能无缘无故改变第一章某个 KP 的 `importance`。

---

## 七、字段更新原则

### evidence 采用追加模式

不要覆盖旧 evidence。

```text
old evidence
+
new evidence
=
all evidence
```

---

### sources 采用去重合并

例如：

```text
课程资料
老师重点
学生笔记
```

重复来源只保留一次。

---

### teacher_emphasis

如果新老师文本提供更强的强调信号，可以更新。

例如：

```text
1 → 3
```

但不能因为新材料没有提到该知识点，就从：

```text
3 → 0
```

---

### note_coverage

根据新增学生笔记重新计算该 KP 的覆盖状态。

例如：

```text
partial → detailed
```

允许更新。

---

### importance / difficulty

不要因为每次新增资料都重新随机评分。

只有出现新证据时才允许调整，并保留调整理由。

---

## 八、推荐输入结构

```json
{
  "mode": "incremental_update",

  "existing_catalog": {},

  "new_material": [],

  "teacher_text": "",

  "student_notes": []
}
```

如果不存在 `existing_catalog`：

```text
mode = build
```

如果存在：

```text
mode = incremental_update
```

---

## 九、推荐输出结构

除了完整更新后的目录，还应返回变更摘要：

```json
{
  "catalog": {},
  "changes": {
    "added_chapters": [],
    "added_topics": [],
    "added_knowledge_points": [],
    "updated_knowledge_points": [],
    "merged_nodes": [],
    "uncertain_nodes": [],
    "unmatched_content": []
  }
}
```

这样可以清楚知道：

> **这次上传第二章，到底给目录带来了什么变化。**

---

## 十、核心约束

AI 增量更新时必须遵守：

1. 有 existing_catalog 时禁止默认全量重建。
2. 已有节点优先匹配和复用。
3. 已有节点 ID 永久稳定。
4. 新资料优先补充已有节点。
5. 不因新增章节随意修改旧章节。
6. 同义节点必须归一。
7. 只在具备明确证据时调整已有结构。
8. evidence 追加，不覆盖历史证据。
9. teacher_emphasis 等事实字段不能因“本次未提及”而降低。
10. importance、difficulty 等推断字段避免每次重新随机评分。
11. 无法确定的新内容放入 uncertain_nodes。
12. 无法匹配的内容放入 unmatched_content。
13. 每次更新输出 changes，明确记录新增、更新、合并情况。

---

## 十一、最终目标

Knowledge Catalog 应从“一次性生成结果”升级为：

> **可持续生长、可增量维护、节点稳定、证据可追溯的课程知识树。**

理想流程：

```text
第一章资料
   ↓
Build Catalog
   ↓
Catalog v1
   +
第二章资料
   ↓
Incremental Update
   ↓
Catalog v2
   +
第三章资料
   ↓
Incremental Update
   ↓
Catalog v3
```

目录持续扩展，但已有知识节点保持稳定。

这样后续基于 Knowledge Catalog 生成复习清单时，才能稳定引用同一个 Knowledge Point，而不会因为每次上传新章节导致目录结构和知识点 ID 大幅变化。
