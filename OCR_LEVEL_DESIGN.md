# 笔记 OCR 识别级别设计：Light / Medium / Heavy

本文档描述笔记识别的三种级别设计，以及 Heavy 模式下 `meta.json` 应该如何辅助生成目录 JSON、复习清单、知识图谱、思维导图、重点统计和行动清单。

## 设计原则

三种级别不是三条互相独立的路线，而是逐级增强：

```text
Heavy 包含 Medium
Medium 包含 Light
```

也就是说：

```text
Light  = OCR + LLM 审校
Medium = Light + VLM 版面增强（双页切分 + 颜色标记 + 大标题提示）
Heavy  = Medium + VLM/LLM 结构化理解 meta.json
```

级别提升只能增加能力，不能阉割已有能力。

最终正式目录 JSON 的保存位置始终不变：

```text
data/{user_id}/knowledge/catalogs/{subject}_{hash}.json
```

例如：

```text
data/1/knowledge/catalogs/math_7e676e9e.json
```

## Light 模式

Light 是当前基础模式，目标是快速、低成本地把图片变成可入库 Markdown。

流程：

```text
图片
-> OCR 接口识别
-> 得到原始 OCR 文本
-> LLM 生成 Markdown 初稿
-> LLM 审校 Markdown
-> 保存 txt + md
-> 使用 llmv2.md 入库/生成目录
```

输出：

```text
data/{user_id}/ocr/{subject}/txt/*_ocr.txt
data/{user_id}/ocr/{subject}/md/*_llmv2.md
```

Light 不主动处理双页，不提示双页风险，不额外调用 VLM。双页乱序属于 Light 的能力边界。

## Medium 模式

Medium 在 Light 基础上增强版面理解，但仍然只输出 txt + md，不保存 `meta.json`。

OCR 接口本身可以识别横向图片，所以 Medium 不负责旋转判断。VLM 的任务是：

```text
判断是否双页
给出合适的切分方式
给出阅读顺序
观察颜色标记的可能含义
给出大标题候选或标题位置提示
```

用户仍然只上传一张图，处理过程对用户无感。

流程：

```text
图片
-> VLM 输出 layout_plan
   -> 是否双页
   -> 双页切分方案
   -> 阅读顺序
   -> 颜色标记含义
   -> 大标题候选
-> 如果不是双页：回到 Light
-> 如果是双页：
   -> 按 VLM 建议裁剪左页/右页
   -> 分别上传 OCR 接口识别
   -> 按阅读顺序合并 OCR 文本
   -> LLM 根据 OCR 文本 + VLM 版面提示生成 Markdown 初稿
   -> LLM 审校 Markdown
-> 保存 txt + md
-> 使用 llmv2.md 入库/生成目录
```

Medium 的 VLM 输出建议：

```json
{
  "is_double_page": true,
  "confidence": 0.86,
  "split_strategy": "vertical_gutter",
  "split_ratio": 0.50,
  "reading_order": ["left", "right"],
  "crop_plan": [
    {
      "id": "left",
      "x1_ratio": 0.00,
      "y1_ratio": 0.00,
      "x2_ratio": 0.515,
      "y2_ratio": 1.00
    },
    {
      "id": "right",
      "x1_ratio": 0.485,
      "y1_ratio": 0.00,
      "x2_ratio": 1.00,
      "y2_ratio": 1.00
    }
  ],
  "visual_hints": {
    "highlight_meanings": [
      {
        "color": "yellow",
        "meaning": "章节标题或重点标题",
        "confidence": 0.78
      },
      {
        "color": "red",
        "meaning": "重点公式或强调内容",
        "confidence": 0.72
      }
    ],
    "title_candidates": [
      {
        "text_hint": "标题短文本或空字符串",
        "location": "left page top",
        "confidence": 0.82
      }
    ]
  },
  "notes": [
    "中间装订线明显，左右两页应分开识别",
    "裁剪区域在中缝处保留少量重叠，避免切掉文字"
  ]
}
```

Medium 的准确率优化点：

1. 中缝重叠裁剪  
   左右裁剪区域在中线附近保留少量重叠，避免中缝附近内容被切断。

2. 分页 OCR 后合并  
   双页不要直接整图 OCR，而是左页 OCR、右页 OCR，再按顺序合并。

3. 失败回退 Light  
   VLM 失败、JSON 解析失败、置信度过低时，直接走 Light，避免 Medium 比 Light 更脆。

4. OCR 结果轻量校验  
   如果裁剪后某一页 OCR 文本极少，或左右页大量重复，可以记录 warning，后续再考虑二次切分。

5. 颜色标记和大标题提示  
   VLM 观察颜色标记和大标题候选，但这些提示只用于 Markdown 标题层级和重点标注，不作为事实来源，不单独落盘。为了避免视觉模型返回中文字段时出现编码问题，`visual_hints` 中的 `meaning`、`location`、`text_hint` 建议使用 ASCII English 短语；不确定的中文标题不要强行转写。

6. VLM JSON 稳定性  
   Medium 使用四层保险：Prompt 约束、JSON 提取、轻量 JSON 修复、最终回退 Light。JSON 修复只处理常见格式问题，例如解释文字、Markdown 围栏、中文双引号、尾随逗号、Python 风格 `True/False/None`；不猜测字段语义。

Medium 输出仍然只有：

```text
*_ocr.txt
*_llmv2.md
```

Medium 不生成 `meta.json`。它通过更准确的 `llmv2.md` 间接提升后续目录生成质量。

## Heavy 模式

Heavy 在 Medium 基础上增加结构化理解，目标不是多识别几个字，而是让笔记变成更适合目录生成和复习清单生成的知识资产。

流程：

```text
图片
-> Medium 流程
   -> 必要时 VLM 双页切分
   -> 分区 OCR
   -> LLM 初稿
   -> LLM 审校
   -> 得到 llmv2.md
-> VLM/LLM 基于图片、OCR 文本、llmv2.md 生成 meta.json
-> 保存 txt + md + meta.json
-> 使用 llmv2.md + meta.json 生成正式目录 JSON
-> 复习清单、知识图谱、思维导图、重点统计、行动清单参考正式目录 JSON 和 meta.json
```

Heavy 输出：

```text
data/{user_id}/ocr/{subject}/txt/*_ocr.txt
data/{user_id}/ocr/{subject}/md/*_llmv2.md
data/{user_id}/knowledge/catalogs/{subject}_meta.json
```

如果同一学科多批 OCR 都使用 Heavy，可以选择把多个批次合并进一个学科级 meta 文件：

```text
data/{user_id}/knowledge/catalogs/{subject}_meta.json
```

也可以短期先按批次保存：

```text
data/{user_id}/knowledge/catalogs/{subject}_{timestamp}_meta.json
```

正式目录 JSON 仍然保存为：

```text
data/{user_id}/knowledge/catalogs/{subject}_{hash}.json
```

`meta.json` 不是最终目录，它是目录和复习清单的增强输入。

## meta.json 的定位

`meta.json` 应该简练有效，不追求字段多。它的任务是告诉后续系统：

```text
哪些内容应该进目录？
哪些内容适合做复习问题？
哪些知识点之间有关联？
哪些内容是重点？
哪些内容需要行动或人工检查？
```

它不应该完整复刻 Markdown，也不应该保存大量视觉细节。视觉信息只保留对学习有用的部分。

## 推荐 meta.json 字段

建议字段如下：

```json
{
  "schema_version": "1.0",
  "recognition_level": "heavy",
  "subject": "math",
  "source": {
    "source_type": "handwritten_notes",
    "files": ["xxx.jpg"],
    "md_files": ["xxx_llmv2.md"]
  },
  "layout": {
    "page_type": "single_page | double_page",
    "reading_order": ["left", "right"],
    "confidence": 0.86
  },
  "catalog_hints": [],
  "knowledge_points": [],
  "review_items": [],
  "relations": [],
  "priority_stats": {},
  "action_items": [],
  "warnings": []
}
```

### catalog_hints

用于辅助生成正式目录 JSON。

它回答：

```text
哪些标题应该进入目录？
它们大概是什么层级？
应该挂在哪个父节点下？
为什么？
```

示例：

```json
{
  "catalog_hints": [
    {
      "title": "一阶微分方程",
      "parent": null,
      "level": 1,
      "reason": "页面主标题，包含多个方法和公式",
      "evidence": "llmv2.md 中的一阶微分方程章节",
      "confidence": 0.88
    },
    {
      "title": "变量分离法",
      "parent": "一阶微分方程",
      "level": 2,
      "reason": "作为解题方法出现，下面包含步骤和例题",
      "evidence": "变量分离法相关段落",
      "confidence": 0.84
    }
  ]
}
```

目录生成时应优先参考：

```text
title
parent
level
reason
confidence
```

### knowledge_points

用于知识点总结、重点统计、目录节点内容补充。

字段不宜太多，建议只保留：

```json
{
  "knowledge_points": [
    {
      "id": "kp_001",
      "title": "变量分离法",
      "type": "method",
      "summary": "将方程整理为两边分别只含 x 或 y 的形式，再分别积分求解。",
      "topic": "一阶微分方程",
      "importance": "high",
      "confidence": 0.83
    }
  ]
}
```

`type` 建议限制在少数几种：

```text
concept
definition
formula
method
example
mistake
```

不要让类型无限扩展，否则后续统计和清单生成会变乱。

### review_items

这是复习清单最直接可用的字段。

它回答：

```text
学生应该怎么复习这个知识点？
应该问自己什么问题？
答案是什么？
优先级如何？
```

示例：

```json
{
  "review_items": [
    {
      "id": "ri_001",
      "topic": "变量分离法",
      "question": "变量分离法适用于什么形式的一阶微分方程？",
      "answer": "适用于可以整理为 g(y)dy = f(x)dx 的方程。",
      "priority": "high",
      "source_knowledge_id": "kp_001"
    }
  ]
}
```

复习清单可以直接使用 `review_items` 生成：

```text
知识点总结
自测问题
行动清单
重点复习项
```

### relations

用于知识图谱和思维导图。

不要做复杂图数据库格式，先用简单三元关系：

```json
{
  "relations": [
    {
      "source": "一阶微分方程",
      "target": "变量分离法",
      "type": "contains",
      "reason": "变量分离法是一阶微分方程的一种解法"
    },
    {
      "source": "变量分离法",
      "target": "通解公式",
      "type": "uses",
      "reason": "变量分离法通过积分得到通解"
    }
  ]
}
```

`type` 建议限制在：

```text
contains
depends_on
uses
similar_to
contrasts_with
example_of
common_mistake
```

知识图谱可以用 `relations` 生成边，思维导图可以用 `contains` 和 `depends_on` 生成层级。

### priority_stats

用于重点统计。

它应该是汇总信息，不要太细：

```json
{
  "priority_stats": {
    "high": 3,
    "medium": 5,
    "low": 2,
    "has_formulas": true,
    "has_examples": true,
    "has_common_mistakes": false
  }
}
```

复习清单可以据此生成：

```text
本次笔记高优先级知识点 3 个
包含公式
包含例题
暂无明显错题/易错点
```

### action_items

用于行动清单。

它不是普通知识点，而是“学生接下来要做什么”。

示例：

```json
{
  "action_items": [
    {
      "task": "整理变量分离法的标准步骤，并补做 2 道例题",
      "reason": "该方法为高优先级，且笔记中包含公式推导",
      "priority": "high",
      "related_topic": "变量分离法"
    },
    {
      "task": "人工检查通解公式中的上下标是否识别准确",
      "reason": "公式区域置信度较低",
      "priority": "medium",
      "related_topic": "通解公式"
    }
  ]
}
```

### warnings

用于保守处理不确定内容。

数学笔记里，VLM/LLM 不应该强行修正不确定公式。遇到不确定内容，应该进入 `warnings`：

```json
{
  "warnings": [
    {
      "type": "low_confidence_formula",
      "message": "部分公式上下标可能识别不准确，建议人工检查。",
      "related_topic": "通解公式"
    }
  ]
}
```

## VLM 在 Heavy 中应该生成什么

VLM 不应该单独承担最终事实判断。它更适合生成视觉观察和结构判断：

```text
标题区域
颜色重点
双页结构
公式区域
例题区域
箭头/图示关系
哪些内容看起来是补充说明
哪些区域置信度低
```

VLM 可输出给 LLM 的中间结果：

```json
{
  "visual_observations": [
    {
      "type": "highlight",
      "meaning": "黄色标记可能是章节标题或重点",
      "related_text": "一阶微分方程",
      "confidence": 0.78
    },
    {
      "type": "formula_region",
      "meaning": "页面中部存在公式推导区域",
      "related_text": "变量分离法",
      "confidence": 0.72
    },
    {
      "type": "example_region",
      "meaning": "右页下方像是例题或练习",
      "related_text": "例题",
      "confidence": 0.70
    }
  ]
}
```

然后 LLM 基于：

```text
llmv2.md
OCR 原始文本
VLM visual_observations
```

生成最终 `meta.json`。

## 目录 JSON 如何使用 meta.json

正式目录生成时，输入应包括：

```text
知识库检索内容
llmv2.md
Heavy meta.json
历史 catalog JSON
```

生成逻辑：

```text
1. 以 llmv2.md 和知识库内容为事实来源
2. 以 meta.json 的 catalog_hints 辅助确定目录层级
3. 以 knowledge_points 辅助补充目录节点摘要
4. 以 review_items 辅助生成复习清单
5. 以 relations 辅助生成知识图谱/思维导图
6. 以 priority_stats 辅助重点统计
7. 以 action_items 生成行动清单
8. 以 warnings 保留人工检查提示
```

注意：

```text
meta.json 只提供辅助信号
正式 catalog JSON 仍然是最终结果
```

不要把整份 `meta.json` 原样塞进正式目录 JSON。正式目录 JSON 应该吸收其中最有价值的摘要，例如：

```text
review_hints
node_summary
importance
relations
warnings
```

## 三种级别的最终对比

| 级别 | 核心能力 | VLM | 输出 | 目录生成 |
| --- | --- | --- | --- | --- |
| Light | OCR + LLM 审校 | 不使用 | txt + md | 通过 llmv2.md 生成目录 |
| Medium | Light + 版面增强 | 双页切分、颜色标记、大标题提示 | txt + md | 通过更准确的 llmv2.md 生成目录 |
| Heavy | Medium + 结构化理解 | 做视觉结构观察 | txt + md + meta.json | 通过 llmv2.md + meta.json 生成更有效目录 |

## 建议的命令行参数

建议使用：

```text
--ocr-level light
--ocr-level medium
--ocr-level heavy
```

不要使用 `version`，因为这不是版本号，而是识别强度。

Gradio 上可以显示为：

```text
轻量 Light
标准 Medium
深度 Heavy
```

内部值仍然使用：

```text
light
medium
heavy
```

## 推荐落地顺序

第一阶段：

```text
新增 --ocr-level 参数
Light 保持当前逻辑
```

第二阶段：

```text
实现 Medium
VLM 做双页切分、颜色标记、大标题提示
分区 OCR 后合并，并把 VLM 版面提示用于 Markdown 整理
```

第三阶段：

```text
实现 Heavy
生成 {subject}_meta.json
目录生成读取 meta.json
```

第四阶段：

```text
复习清单读取正式目录 JSON + meta.json
生成知识点总结、知识图谱、思维导图、重点统计、行动清单
```

## 关键约束

1. Light 不处理双页，不提示双页。
2. Medium 不处理旋转，只处理双页切分、颜色标记和大标题提示。
3. Medium 对用户无感，用户仍然只上传原图。
4. Heavy 必须包含 Medium，Medium 必须包含 Light。
5. `meta.json` 不替代正式目录 JSON。
6. 正式目录 JSON 保存位置不变。
7. 数学公式不确定时进入 warnings，不让 LLM 自由猜。
8. 字段设计宁可少而稳定，不要多而松散。
