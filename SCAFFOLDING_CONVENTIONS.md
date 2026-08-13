# AgentFlow 脚手架约定

本文档是新增 domain / task 的唯一命名约定。脚本、现有 domain、后续任务线都应按这里执行，不保留历史兼容别名。

## 1. Domain 命名

`--domain` 必须是合法 Python 标识符。

示例：

```text
meeting -> Meeting
notes -> Notes
my_notes -> MyNotes
```

脚本按 domain 推导：

```text
domain/<domain>/
domain/<domain>/<domain>_factory.py
domain/<domain>/<domain>_core/
domain/<domain>/models.py              # 手写：State / 画像再导出
domain/<domain>/models_base.py         # 手写：ModelMixin / UserIdentity
domain/<domain>/models_generated.py    # 生成：业务模型 / 审核模型 / Report 校验
<Pascal>State
<Pascal>AgentFactory
<Pascal>AgentSystem
```

例如 `notes`：

```text
domain/notes/notes_factory.py
domain/notes/notes_core/
NotesState
NotesAgentFactory
NotesAgentSystem
```

## 2. Core Understanding 命名

领域专属理解 agent 使用固定路径：

```text
domain/<domain>/<domain>_core/<domain>_understanding_agent.py
```

类名：

```text
<DomainPascal>UnderstandingAgent
```

契约类：

```text
<DomainPascal>UnderstandingGenerationContract
```

模型类由脚本生成：

```text
<DomainPascal>Understanding
```

常量名使用契约基名：

```text
<DOMAIN_UNDERSTANDING>_GENERATION_OUTPUT_CONTRACT
<DOMAIN_UNDERSTANDING>_SYSTEM_PROMPT
```

例如 `notes`：

```text
NotesUnderstandingGenerationContract
NotesUnderstanding
NotesUnderstandingAgent
NOTES_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT
NOTES_UNDERSTANDING_SYSTEM_PROMPT
```

core agent 必须使用项目统一 LLM 接口：

```python
await self.client.structured(
    SYSTEM_PROMPT,
    user_prompt,
    OutputModel,
    OUTPUT_CONTRACT,
)
```

不要使用 `with_structured_output()`。

## 3. Task 命名

`--task` 是任务线目录名，也是运行时 line name。

示例：

```text
action_items -> ActionItems
minutes_generation -> MinutesGeneration
risk -> Risk
points -> Points
```

文件结构固定：

```text
domain/<domain>/tasks/<task>/
  __init__.py
  contracts.py
  prompts.py
  steps/
    __init__.py
    <task>_agent.py
    <task>_supervisor.py
    <task>_render.py
```

## 4. 契约基名

所有 task 常量前缀都以 `GenerationContract` 的类名前缀为准，不以目录名为准。

规则：

```text
<ModelBase>GenerationContract -> <MODEL_BASE_UPPER>
```

示例：

```text
ActionItemsGenerationContract -> ACTION_ITEMS
MinutesGenerationContract -> MINUTES
RiskGenerationContract -> RISK
PointsGenerationContract -> POINTS
```

特别注意：

```text
minutes_generation 目录的常量前缀是 MINUTES，不是 MINUTES_GENERATION。
```

## 5. contracts.py 约定

每个 task 必须定义：

```python
class <ModelBase>GenerationContract(GenerationContract):
    ...

class <ModelBase>SupervisorContract(SupervisorContract):
    ...
```

脚本生成模型：

```text
<ModelBase>
<ModelBase>SupervisorReview
<ModelBase>ReportValidation
```

必须导出：

```text
<MODEL_BASE_UPPER>_GENERATION_OUTPUT_CONTRACT
<MODEL_BASE_UPPER>_SUPERVISOR_OUTPUT_CONTRACT
```

可选 fallback：

```text
<ModelBase>FallbackRules
<MODEL_BASE_UPPER>_FALLBACK_RULES
```

## 6. prompts.py 约定

每个 task 必须定义：

```text
<MODEL_BASE_UPPER>_GENERATION_SYSTEM_PROMPT
<MODEL_BASE_UPPER>_SUPERVISOR_DOMAIN_PROMPT
<MODEL_BASE_UPPER>_RENDER_PROMPT
<MODEL_BASE_UPPER>_RENDER_TEMPLATE_PROMPT
```

禁止保留旧兼容名，例如：

```text
ACTION_ITEMS_SYSTEM_PROMPT
ITEM_RENDER_PROMPT
ITEM_RENDER_TEMPLATE_PROMPT
POINTS_SYSTEM_PROMPT
```

## 7. steps 约定

Agent：

```python
class <ModelBase>Agent:
    async def run(self, shared_context: str) -> <ModelBase>:
        ...
```

Supervisor：

```python
class <ModelBase>Supervisor:
    async def review(self, context: str) -> <ModelBase>SupervisorReview:
        ...
```

Render：

```python
class <ModelBase>Render:
    async def run(self, approved_context: str, template: str = "") -> str:
        ...

    async def stream(self, approved_context: str, template: str = ""):
        ...
```

Supervisor 方法名必须是 `review`，不是 `run`。

## 8. reports.py 约定

最终 Report 写在：

```text
domain/<domain>/reports.py
```

类名：

```text
<ModelBase>Report
```

继承：

```python
@dataclass
class <ModelBase>Report(ModelMixin, <ModelBase>ReportValidation):
    ...
```

字段必须使用 `metadata["source"]` 声明来源：

```text
title -> 通用标题
rendered -> 渲染文本
structure -> 结构化列表
draft.<field> -> draft 中的指定字段
```

Report 字段名应与业务契约一致。例如 `RiskGenerationContract` 输出 `risks`，则 `RiskReport` 使用 `risks`，不要使用通用 `items`。

## 9. 同步流程

推荐流程：

```powershell
python tools/scripts/register_task.py --domain meeting --task risk --name "风险分析" --with-report
python tools/scripts/sync_domain.py --domain meeting --model
python tools/scripts/sync_domain.py --domain meeting
python tools/scripts/sync_domain.py --domain meeting --check
```

`--check` 必须通过后再运行 `bootstrap.py`。
