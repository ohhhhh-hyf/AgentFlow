# 议题纪要：column_major 与 topic_major 工作方式

> 一句话：
>
> - **column_major（栏目主序）**：先按模板栏目展开，某一栏内部再按议题分段。
> - **topic_major（议题主序）**：先按议题展开，每个议题内部再按模板子栏输出。

---

## 1. column_major（栏目主序）

### 1.1 草稿输出字段

议题模式使用 `MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT`：

| 字段 | 作用域 | 含义 |
|---|---|---|
| `headline` | 全局 | 纪要标题 |
| `executive_summary` | 全局 + 按议题 | `[0]` 全场概况；`[1:]` 每个议题一段，段内用 `### 一. 议题名` |
| `key_decisions` | 全局扁平 | 全场决议 |
| `personally_relevant_points` | 全局扁平 | 全场行动/落实安排 |
| `risks_and_blockers` | 全局扁平 | 全场风险/卡点 |
| `unresolved_questions` | 全局扁平 | 全场未决/待确认 |
| `history_comparison` | 全局 | 历史对比，通常 `[]` |

### 1.2 渲染对应关系

| 模板栏目 | 取哪个草稿字段 |
|---|---|
| 概况 / 摘要 / 全文摘要 | `executive_summary[0]` |
| 议题研讨 / 工作进展 / 要点梳理 | `executive_summary[1:]`（所有议题都在这一栏里） |
| 结论定调 / 最终决议 | `key_decisions` |
| 落实安排 / 后续计划 / 待办 | `personally_relevant_points` |
| 风险预警 / 卡点 | `risks_and_blockers` |
| 遗留问题 / 待确认 | `unresolved_questions` |
| 未决风险 | `risks_and_blockers` + `unresolved_questions` |

### 1.3 例子

草稿：

```json
{
  "headline": "团队例会纪要",
  "executive_summary": [
    "本次例会围绕接口联调与上线准备展开。",
    "### 一. 接口联调\n- 方案已确认\n- 联调排期本周内",
    "### 二. 上线准备\n- 灰度名单已确认"
  ],
  "key_decisions": ["按 B 方案执行", "周三晚开始灰度"],
  "personally_relevant_points": [
    "张三周五前完成联调报告",
    "李四周二前提交回滚方案"
  ],
  "risks_and_blockers": ["依赖外部团队，可能延迟", "监控覆盖不足"],
  "unresolved_questions": ["上线时间是否按原计划", "是否增加值守人员"],
  "history_comparison": []
}
```

示例模板：

```markdown
## [例会概况]
## [工作进展]
## [落实安排]
## [未决风险]
```

渲染结果：

```markdown
## 例会概况
本次例会围绕接口联调与上线准备展开。

## 工作进展
### 一. 接口联调
- 方案已确认
- 联调排期本周内

### 二. 上线准备
- 灰度名单已确认

## 落实安排
- 张三周五前完成联调报告
- 李四周二前提交回滚方案

## 未决风险
- 依赖外部团队，可能延迟
- 监控覆盖不足
- 上线时间是否按原计划
- 是否增加值守人员
```

特点：**所有议题都挤在“工作进展”这一栏里；行动和风险是全场扁平列表，不区分属于哪个议题。**

---

## 2. topic_major（议题主序）

### 2.1 草稿输出字段

议题模式使用 `MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT`：

```json
{
  "headline": "",
  "overview": "",
  "topics": [
    {
      "topic_name": "",
      "topic_summary": [],
      "decisions": [],
      "actions": [],
      "risks": [],
      "open_questions": []
    }
  ],
  "history_comparison": []
}
```

| 字段 | 作用域 | 含义 |
|---|---|---|
| `headline` | 全局 | 纪要标题 |
| `overview` | 全局 | 全场概况，单段 |
| `topics` | 按议题 | 每个有效议题一条记录 |
| `topic_name` | 按议题 | 议题全称，与有效议题清单一致 |
| `topic_summary` | 按议题 | 本议题正文/研讨/进展 |
| `decisions` | 按议题 | 本议题已拍板决议 |
| `actions` | 按议题 | 本议题落实安排/行动 |
| `risks` | 按议题 | 本议题风险/卡点 |
| `open_questions` | 按议题 | 本议题未决/待确认 |
| `history_comparison` | 全局 | 历史对比，通常 `[]` |

### 2.2 渲染对应关系

| 模板栏目 | 取哪个草稿字段 |
|---|---|
| 概况 / 摘要 | `overview` |
| 议题容器（如 `议题梳理`） | `topics`，按数组顺序逐个议题输出 |
| 议题标题 | `### 序号. topic_name` |
| 子栏：工作进展 / 内容 / 方案 | `topics[].topic_summary` |
| 子栏：结论定调 / 最终决议 | `topics[].decisions` |
| 子栏：落实安排 / 后续计划 / 待办 | `topics[].actions` |
| 子栏：风险 / 卡点 | `topics[].risks` |
| 子栏：遗留问题 / 待确认 | `topics[].open_questions` |
| 子栏：未决风险 | `topics[].risks` + `topics[].open_questions` |

### 2.3 例子

草稿：

```json
{
  "headline": "团队例会纪要",
  "overview": "本次例会围绕接口联调与上线准备展开。",
  "topics": [
    {
      "topic_name": "接口联调",
      "topic_summary": ["方案已确认", "联调排期本周内"],
      "decisions": ["按 B 方案执行"],
      "actions": ["张三周五前完成联调报告"],
      "risks": ["依赖外部团队，可能延迟"],
      "open_questions": ["上线时间是否按原计划"]
    },
    {
      "topic_name": "上线准备",
      "topic_summary": ["灰度名单已确认"],
      "decisions": ["周三晚开始灰度"],
      "actions": ["李四周二前提交回滚方案"],
      "risks": ["监控覆盖不足"],
      "open_questions": ["是否增加值守人员"]
    }
  ],
  "history_comparison": []
}
```

模板（team_meeting）：

```markdown
## [例会概况]
## [议题梳理]
  每个议题内部按：**工作进展** / **落实安排** / **未决风险** 输出
```

渲染结果：

```markdown
## 例会概况
本次例会围绕接口联调与上线准备展开。

## 议题梳理

### 一. 接口联调
**工作进展**
- 方案已确认
- 联调排期本周内

**落实安排**
- 张三周五前完成联调报告

**未决风险**
- 依赖外部团队，可能延迟
- 上线时间是否按原计划

### 二. 上线准备
**工作进展**
- 灰度名单已确认

**落实安排**
- 李四周二前提交回滚方案

**未决风险**
- 监控覆盖不足
- 是否增加值守人员
```

特点：**每个议题自己的进展、行动、风险都在该议题下面；不同议题不会混在一起。**

说明：`decisions` 仍然被抽取，但 team_meeting 模板没有“结论定调”子栏，所以最终正文不展示；换成带 `**结论定调**` 的模板就会渲染。

---

## 3. 两种 layout 对比

| 维度 | column_major | topic_major |
|---|---|---|
| 第一层组织 | 模板栏目 | 议题 |
| 第二层组织 | 议题（在某栏内部） | 模板子栏 |
| 行动/风险 | 全场扁平 | 按议题归属 |
| 草稿核心字段 | 7 字段 | `headline/overview/topics/history_comparison` |
| 议题内字段 | 只有 `executive_summary[1:]` | `topic_summary/decisions/actions/risks/open_questions` |
| 适合模板 | 全局汇总、叙事型 | 每个议题都有进展/行动/风险 |
| 典型模板 | 通用纪要、政府报告、媒体发布 | 团队例会、项目进度、决策评审 |
| 模板声明 | 无 layout 或 `column_major` | `layout: topic_major` |

---

## 4. 怎么选择走哪种 layout

模板自己声明：

```markdown
<!-- layout
mode: topic_major
container: 议题梳理
-->
```

- 没有 `layout` 或写 `column_major` → 走栏目主序；
- 写 `topic_major` → 走议题主序；
- 两者共用同一个 `minutes` 任务，不是两条任务线；
- 用户仍然只选模板，不需要新增 layout 参数。

---

## 5. 汇报用一句话总结

> **column_major 是“栏目里有议题”，topic_major 是“议题里有栏目”。**
>
> 前者适合全局汇总型纪要，后者适合每个议题都要独立讲进展、行动和风险的会议纪要。
