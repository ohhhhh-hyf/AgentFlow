# 待办任务客观化与直连执行清单

> 范围：只针对 `actions`（待办）任务。
>
> 目标：待办只输出客观待办；actions-only 直接走待办 Agent，跳过会议理解、跳过视角建模，不再使用 `actions` 的 UnderstandingProfile。
>
> 不涉及：`minutes`、`risks`、`mindmap`、`minutes_styles`、`notes`。

---

## 〇、当前落地状态

- [x] Step 1 契约冻结：`ACTIONS_OBJECTIVE_OUTPUT_FIELDS` / `ACTIONS_OBJECTIVE_ITEM_FIELD_NAMES`
- [x] 冻结测试：`tests/unit/meeting/test_actions_objective_contract_freeze.py`
- [x] Contract / Prompt / Agent 已切客观：`assigned_actions / unassigned_actions`，8 字段
- [x] actions_render 已按客观两数组读取
- [x] `ActionItems` 模型已只保留 `assigned_actions / unassigned_actions`
- [x] `models.py` 旧 `my_actions / delegated_actions` 兼容逻辑已删除
- [x] `_EMPTY_ACTION_ITEMS` 已改为客观两数组
- [x] actions 上下文只读会议原文，不再注入会议理解 / 用户画像 / 命中 / 雷达 / 视角模型
- [x] actions-only 跳过 perspective_modeling；多线仍为其他线保留视角建模
- [x] actions-only 跳过 meeting_understanding：`actions_entry` 直连 actions_agent
- [x] 删除 `TASK_PROFILES["actions"]` / `TASK_INTRO["actions"]`
- [x] actions 不再参与 understanding profile union（`resolve_profile` 过滤 actions）
- [x] actions Supervisor 上下文只保留原文 + 送审稿，视角模式固定 objective
- [x] actions Render 上下文只保留草稿 + 审核结论
- [x] `supervisor_slice` / template router / memory render / report / node needle 零散引用已清理
- [x] `ActionItems` 生产链路已无 `my_actions / delegated_actions`
- [x] actions 生成 Prompt 合并为单一 `ACTION_ITEMS_GENERATION_SYSTEM_PROMPT`（不再拆 header / common）
- [ ] 真实 LLM E2E / 最终全量验收
- [x] Supervisor / Render 上下文 / 其他零散位置清理

---

## 一、冻结目标

### 1.1 运行链路

actions-only 固定为：

```text
START
→ actions_agent
→ actions_supervisor
→ actions_render
```

明确不构建：

```text
meeting_understanding
perspective_modeling
template_classify
minutes_view
```

不再有：

```text
会议理解 7 字段
actions UnderstandingProfile
action_hints
session_segments
decisions
personal_perspective
perspective_profile
```

### 1.2 输入

待办 Agent 只读：

```text
会议原文
```

不再读：

```text
meeting_brief
meeting_purpose
speakers
session_segments
decisions
action_hints
用户画像
preferences / personality
perspective_profile
user_hits_block
user_radar_block
会议记忆
```

### 1.3 输出

统一客观待办：

```text
assigned_actions
unassigned_actions
```

不再输出：

```text
my_actions
delegated_actions
```

每个待办条目精简为 8 个字段：

```text
category
task
owner
deadline
collaborators
acceptance_criteria
dependency
evidence
```

删除：

```text
timing_anchor
deliverable
status
confidence
```

`category` 是分组键；渲染时按 `category` 聚合。本次先保持扁平契约，不在本次清理中改嵌套结构。

`ActionItemsReport.actions` 继续作为最终结构列表，组装时合并：

```text
assigned_actions + unassigned_actions
```

### 1.4 模式

待办始终是客观模式：

```text
不解析 personal / objective / role_template
不根据 profile=user 做本人裁剪
不调用 PersonalPerspective
不调用 PerspectiveModeling
不写 perspective_profile
不写命中表 / 雷达块
```

### 1.5 跳过规则

```text
actions-only（selected == ["actions"]）
→ 不构建 meeting_understanding
→ 不构建 perspective_modeling
→ 不构建 template_classify / minutes_view

actions + minutes
→ minutes 仍需要 meeting_understanding / personal perspective
→ actions 直接读原文，不消费 meeting_understanding / personal_perspective

actions + risks
→ risks 仍按自身逻辑运行
→ actions 直接读原文，不消费 meeting_understanding
```

### 1.6 会议理解中的 actions profile

删除：

```python
TASK_PROFILES["actions"] = UnderstandingProfile(
    segments="light",
    fields=("decisions", "action_hints"),
    intro="本次任务服务于待办执行与分工提炼。",
)
```

同时删除：

```text
TASK_INTRO["actions"]
actions 专用的 action_hints / decisions 理解要求
actions 专用 light session_segments 要求
```

其他任务线仍可保留：

```text
minutes
risks
mindmap
FULL_PROFILE
```

`action_hints` 字段本身可以继续存在于其他 profile / FULL_PROFILE，但 actions 不再请求它。

---

## 二、当前状态盘点

### 2.1 Meeting Understanding

当前 `actions` 仍会进入会议理解，并使用：

```text
segments = light
fields = decisions, action_hints
```

实际输出还包含基础字段：

```text
meeting_brief
meeting_purpose
speakers
session_segments(light)
decisions
action_hints
```

### 2.2 编排层

当前 `_build_core()`：

- 总是构建 `meeting_understanding`；
- `actions` 不在 `skip_perspective` 中，因此会构建 `perspective_modeling`；
- 任务线边从 core 汇合点进入 `actions_agent`。

### 2.3 待办上下文

当前 `_line_shared_context()` 在 personal 下会向 actions 注入：

```text
用户画像
preferences
user_hits_block
user_radar_block
perspective_profile
会议理解
会议原文
```

### 2.4 待办 Agent / 契约

当前存在：

```text
PersonalActionItemsGenerationContract
ACTION_ITEMS_PERSONAL_GENERATION_OUTPUT_CONTRACT
ACTION_ITEMS_PERSONAL_GENERATION_PROMPT
my_actions / delegated_actions
```

`ActionItemsAgent.run()` 仍会：

```text
parse_perspective_mode(shared_context)
personal / role_template → 个人 Prompt + 个人契约
objective → 客观 Prompt + 客观契约
```

---

## 三、文件级改动

### 3.1 `domains/meeting/meeting_core/understanding_profiles.py`

- [ ] 删除 `TASK_PROFILES["actions"]`
- [ ] 删除 `actions` 的 `intro`
- [ ] 保留 `minutes` / `risks` / `mindmap` profile
- [ ] `FULL_PROFILE` 中是否保留 `action_hints` 单独决策；actions-only 不走 FULL_PROFILE
- [ ] 如 `is_actions_risks_only_tasks()` 仅服务旧 actions/risks 逻辑，评估删除或改为 risks-only

### 3.2 `domains/meeting/meeting_core/prompts.py`

- [ ] 删除 `TASK_INTRO["actions"]`
- [ ] actions-only 不再调用 `build_understanding_prompt`
- [ ] 不删除其他任务线的 `action_hints` guidance

### 3.3 `domains/meeting/orchestrator.py::_build_core`

- [ ] 识别 actions-only：
  ```text
  selected == ["actions"]
  ```
- [ ] actions-only 不添加 `meeting_understanding` 节点
- [ ] actions-only 不添加 `perspective_modeling` 节点
- [ ] actions-only 不添加 `template_classify`
- [ ] actions-only 不添加 `minutes_view`
- [ ] 解决空 core 汇合：
  - 方案 A：增加一个零成本 `actions_entry` 节点
  - 方案 B：`_build_graph` 在 core 为空时直接连 `START → actions_agent`
- [ ] 确保 `actions_agent` 仍能拿到原文
- [ ] 确保 actions-only 不写 `meeting_understanding`
- [ ] 确保 actions-only 不写 `perspective_profile` / 命中 / 雷达

### 3.4 `domains/meeting/orchestrator.py::_line_shared_context`

- [ ] 增加 actions 专用分支
- [ ] actions 上下文只给：
  ```text
  视角模式：objective
  会议原文
  ```
- [ ] 不再调用 `_meeting_pack()`
- [ ] 不再注入：
  ```text
  会议理解
  用户画像
  preferences
  user_hits_block
  user_radar_block
  perspective_profile
  ```
- [ ] actions + minutes 时，actions 也不读取 `personal_perspective`

### 3.5 `domains/meeting/orchestrator.py::_supervisor_context`

- [ ] actions 不再依赖 `meeting_understanding`
- [ ] actions 审核上下文只给：
  ```text
  送审稿
  会议原文
  ```
- [ ] 不注入用户画像 / 命中 / 雷达 / perspective_profile
- [ ] 保留 actions supervisor 的客观事实审核规则

### 3.6 `domains/meeting/orchestrator.py::_render_context`

- [ ] actions 渲染上下文只给已审核待办草稿 + 必要审核结论
- [ ] 不注入用户画像 / 会议理解 / 命中 / 雷达 / perspective_profile
- [ ] 不改变 `ActionItemsReport.actions` 的最终结构

### 3.7 `domains/meeting/tasks/actions/contracts.py`

- [ ] 删除 `PersonalActionItemsGenerationContract`
- [ ] 删除 `ACTION_ITEMS_PERSONAL_GENERATION_OUTPUT_CONTRACT`
- [ ] `ActionItemsGenerationContract` 改为纯客观契约
- [ ] 输出字段收敛为：
  ```text
  assigned_actions
  unassigned_actions
  ```
- [ ] `ACTION_ITEM_FIELDS` 精简为 8 字段：
  ```text
  category
  task
  owner
  deadline
  collaborators
  acceptance_criteria
  dependency
  evidence
  ```
- [ ] 删除：
  ```text
  timing_anchor
  deliverable
  status
  confidence
  ```
- [ ] `ActionItemsFallbackRules` 只合并客观两数组
- [ ] 保留 `ACTION_ITEMS_SUPERVISOR_OUTPUT_CONTRACT`

### 3.8 `domains/meeting/tasks/actions/prompts.py`

- [ ] 删除 `_ACTION_PERSONAL_HEADER`
- [ ] 删除 `ACTION_ITEMS_PERSONAL_GENERATION_PROMPT`
- [ ] `ACTION_ITEMS_GENERATION_SYSTEM_PROMPT` 固定为客观 Prompt
- [ ] 删除所有 `action_hints / decisions / session_segments` 输入说明
- [ ] Prompt 改为直接读会议原文：
  ```text
  先按业务议题分组
  → 组内逐条提取待办
  → 输出 category / task / owner / deadline / ...
  ```
- [ ] 明确要求：
  - 同一组复用完全相同的 `category`
  - 从原文识别拍板、指派、承诺、时限、协同、验收、依赖
  - 无依据字段为 null
- [ ] 删除 Supervisor Prompt 的：
  - “读取视角模式 objective / personal”
  - “个人视角条目精简”
  - `my_actions / delegated_actions`

### 3.9 `domains/meeting/tasks/actions/steps/actions_agent.py`

- [ ] 删除 `parse_perspective_mode`
- [ ] 删除 personal / role_template 分支
- [ ] 固定使用客观 Prompt / 客观 Contract
- [ ] 删除个人 `allow_missing`
- [ ] label 不再带 personal / role_template 后缀

### 3.10 `domains/meeting/tasks/actions/steps/actions_render.py`

- [ ] `extract_actions()` 不再判断 `objective_perspective`
- [ ] 统一合并：
  ```python
  assigned_actions + unassigned_actions
  ```
- [ ] 删除 `my_actions / delegated_actions` 回退
- [ ] `render_draft()` 同步只读客观两数组
- [ ] 更新注释，删除“个人视角仅本人待办”
- [ ] 保留按 `category` 聚合的渲染结构

### 3.11 模型与生成区

- [ ] `ActionItems` 只保留：
  ```text
  assigned_actions
  unassigned_actions
  ```
- [ ] 删除 `my_actions / delegated_actions`
- [ ] 更新 `models.py` 兼容校验
- [ ] 更新 `_EMPTY_ACTION_ITEMS`
- [ ] 更新 `sync_domain.py` 契约源
- [ ] 如历史数据仍需兼容，只保留只读兼容，不进入新输出

### 3.12 其他位置

- [ ] `core/runtime/supervisor_slice.py`
  - actions 字段白名单移除个人字段
- [ ] `core/templates/router/__init__.py`
  - `LINE_SCHEMA_HINTS["actions"]` 改为：
    ```text
    assigned_actions / unassigned_actions
    ```
- [ ] `domains/meeting/memory/render.py`
  - 待办渲染兜底只合并客观两数组
  - 历史个人字段只读兼容（可选）
- [ ] `domains/meeting/reports.py`
  - 更新 `ActionItemsReport` 注释
- [ ] `app/tasks.py`
  - 确认 actions 不再依赖个人 profile
- [ ] `domains/meeting/domain_config.py`
  - 如 actions 有个人分支配置，一并清理

---

## 四、测试清单

### 4.1 删除 / 改写

- [ ] 删除个人 actions Prompt / Contract 测试
- [ ] 删除 `my_actions / delegated_actions` 断言
- [ ] 删除 actions 的 UnderstandingProfile 测试
- [ ] 删除 actions 视角建模测试
- [ ] 改写 actions 上下文 / supervisor 测试

### 4.2 新增

- [ ] actions-only 不构建 `meeting_understanding`
- [ ] actions-only 不构建 `perspective_modeling`
- [ ] actions-only 不调用 `PerspectiveModelingAgent`
- [ ] actions-only 不写 `meeting_understanding`
- [ ] actions-only 不写 `perspective_profile`
- [ ] actions 上下文只有原文
- [ ] actions 上下文不含用户画像 / 命中 / 雷达 / 会议理解
- [ ] actions Agent 固定使用客观 Prompt / Contract
- [ ] actions 输出只有 `assigned_actions / unassigned_actions`
- [ ] actions 不输出 `my_actions / delegated_actions`
- [ ] actions 条目只有 8 字段
- [ ] actions render 按 `category` 聚合客观两数组
- [ ] actions supervisor 只对照原文 + 送审稿
- [ ] actions + minutes 时：
  - minutes 仍能走自己的理解 / 个人视角
  - actions 不消费 `meeting_understanding` / `personal_perspective`
- [ ] 客观 / 多线 / 其他任务线回归无新增失败

---

## 五、执行顺序

1. 冻结 actions-only 直连链路
2. 删除 `TASK_PROFILES["actions"]` / `TASK_INTRO["actions"]`
3. 改 `_build_core()`：actions-only 跳过会议理解 + 视角建模
4. 解决空 core 汇合（entry 节点或 START 直连）
5. 改 actions 专用上下文 / supervisor / render context
6. 改 actions contract / prompt / agent / render
7. 改模型与 codegen
8. 清理 supervisor_slice / template router / memory render / report 注释
9. 更新测试
10. actions-only FakeLLM E2E + 全量回归

---

## 六、验收标准

```text
rg "TASK_PROFILES\\[.actions.\\]|action_hints|session_segments|decisions" \
  domains/meeting/meeting_core domains/meeting/tasks/actions
# actions 专用路径不应再依赖这些字段

rg "perspective_modeling|PerspectiveModeling|personal_perspective|perspective_profile" \
  domains/meeting/tasks/actions
# actions 生产代码零命中

rg "my_actions|delegated_actions" domains/meeting/tasks/actions
# 生产代码零命中
```

行为验收：

- [ ] actions-only 图中没有 `meeting_understanding`
- [ ] actions-only 图中没有 `perspective_modeling`
- [ ] actions Agent 直接从会议原文生成待办
- [ ] actions 输出 assigned_actions / unassigned_actions
- [ ] 每条待办 8 字段
- [ ] actions 上下文不含会议理解 / 用户画像 / 命中 / 雷达 / 旧视角
- [ ] actions supervisor 只对照原文 + 送审稿
- [ ] actions + minutes 多线不影响 minutes 链路
- [ ] `ActionItemsReport.actions` 正常产出
- [ ] 全量测试失败集合不扩大
- [ ] 有 API Key 时补 actions-only 真实 E2E

---

## 七、风险与待确认

1. **跳过会议理解后，待办 Agent 责任变重**
   - 必须自己识别分组、拍板、指派、承诺、时限、验收、依赖。
   - Prompt 必须明确这些规则，不能只写“提取待办”。

2. **没有 decisions / action_hints 兜底**
   - 只能从原文找；可能漏掉隐含推进项。
   - 需要 FakeLLM 与真实样例验证召回率。

3. **category 一致性**
   - 同一组必须复用相同字符串。
   - 输出后可做归一化；无法归一则「综合事项」。

4. **actions + 其他线**
   - 其他线可能仍需要 meeting_understanding。
   - 只对 actions-only 跳过会议理解；多线请求不能误删其他线的 core。

5. **历史数据**
   - `my_actions / delegated_actions` 可能存在于旧 memory / report。
   - 新契约不写；历史只读兼容是否保留，需明确。

6. **codegen**
   - `ActionItems` 是生成区，必须先改契约源，再运行 `sync_domain.py`。

---

## 八、最终形态

```text
会议原文
→ actions_agent
   - 先分组
   - 组内分点
   - 输出客观待办
→ actions_supervisor
→ actions_render
→ ActionItemsReport.actions
```

待办链路不再出现：

```text
meeting_understanding
actions UnderstandingProfile
session_segments
action_hints
decisions
PersonalPerspective
PerspectiveModeling
perspective_profile
user_hits_block
user_radar_block
my_actions / delegated_actions
记忆注入
```
