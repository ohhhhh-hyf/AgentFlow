# Codegen —— 域/任务线代码生成器

命名与目录约定：见仓库根 `README.md`（「项目结构」「新增任务线」两节）与各生成脚本的 `--help`。
If this README and the root convention document ever disagree, follow the root
document and update this README.

These scripts create domain/task skeletons and sync generated zones.

The scripts write files as UTF-8. CLI output is intentionally mostly ASCII to
avoid mojibake in Windows PowerShell.

## Scripts

### register_domain.py

Creates a new domain skeleton.

```powershell
python tools/codegen/register_domain.py --domain notes --name "Notes"
```

Creates:

```text
domain/notes/
  __init__.py
  domain_config.py
  models.py
  notes_factory.py
  orchestrator.py
  reports.py
  notes_core/
    __init__.py
  samples/
  tasks/
    __init__.py
```

The shared `PerspectiveModelingAgent` is wired by default. A domain-specific
core understanding agent is optional and can be added later.

### register_task.py

Registers a task line and creates meeting-style runnable templates.

```powershell
python tools/codegen/register_task.py --domain notes --task digest --name "Digest"
```

Creates missing files only; existing user code is never overwritten.
Pass ``--kind llm_extract|llm_document|deterministic_pipeline`` (default extract)
to register ``LINE_KINDS`` in domain_config.py.

```text
domain/notes/tasks/digest/
  __init__.py
  contracts.py
  prompts.py
  steps/
    __init__.py
    digest_agent.py
    digest_supervisor.py
    digest_render.py
```

By default, generated files are importable templates:

- `contracts.py` contains `GenerationContract`, `SupervisorContract`, output
  contract constants, and optional fallback rules.
- `prompts.py` contains the four required prompt constants.
- `digest_agent.py` uses `LLMClient.structured(...)`.
- `digest_supervisor.py` exposes `async def review(...)`.
- `digest_render.py` exposes `async def run(...)` and `async def stream(...)`.

To also append a generic report class:

```powershell
python tools/codegen/register_task.py --domain notes --task digest --name "Digest" --with-report
```

This appends `DigestReport` to `domain/notes/reports.py` if it is missing.

### sync_domain.py

Syncs generated zones from contracts, prompts, reports, and step files.

```powershell
# Models only: generation models, supervisor models, ReportValidation imports.
python tools/codegen/sync_domain.py --domain notes --model

# Full runtime wiring (models / TASK_LINES / factory / Report assemblers).
# Does not generate per-line render_context or fallback nodes.
python tools/codegen/sync_domain.py --domain notes

# Check generated zones.
python tools/codegen/sync_domain.py --domain notes --check
```

If a task line is incomplete, full sync first updates `models.py`, then prints
the missing items and stops before writing incomplete runtime wiring.

### check_user_profile.py

一次性的本地自检：验证 `data/{user_id}/user.json`（用户自建真人档案）是否被正确解析与注入。
**不调模型**，秒级；排查"传了档案但纪要没变化"这类问题时先跑它。

```powershell
python tools/devtools/check_user_profile.py              # 默认 user_id=1 / domain=meeting
python tools/devtools/check_user_profile.py 2            # 指定用户
python tools/devtools/check_user_profile.py 1 --show-block   # 顺带打印「本用户称呼」「本用户偏好」两块全文
```

它打印四件事：`profile=user` 指向哪个文件（并对照打印"传空 → 客观全员"）、解析后的画像
（persona_type 是否为空 = 是否真人、role_template 有没有合并进来）、两个注入块的实际内容、
以及本次会跑视角建模还是跳过。字段写法见根 `api.md` 的 `user.json` 小节。

## Naming Rules

约定以代码生成器为准（`sync_domain.py` / `register_task.py`）。要点是：
task constants use the contract model base, not necessarily the task directory
name. For example, `MinutesGenerationContract` uses the `MINUTES` prefix.

### Domain

`--domain` must be a valid Python identifier.

```text
notes      ok
meeting    ok
my_notes   ok
my-notes   invalid
123notes   invalid
```

For `notes`, scripts derive:

```text
Notes
NotesState
NotesAgentFactory
NotesAgentSystem
notes_core/
notes_factory.py
```

### Task

`--task` is the runtime line name and directory name.

```text
digest             -> Digest
actions       -> ActionItems
minutes -> MinutesGeneration
```

Required layout:

```text
domain/<domain>/tasks/<task>/contracts.py
domain/<domain>/tasks/<task>/prompts.py
domain/<domain>/tasks/<task>/steps/<task>_agent.py
domain/<domain>/tasks/<task>/steps/<task>_supervisor.py
domain/<domain>/tasks/<task>/steps/<task>_render.py
```

## contracts.py Rules

Required generation contract:

```python
class DigestGenerationContract(GenerationContract):
    ...
```

The class name must end with `GenerationContract`. The generated model class is
the prefix without that suffix:

```text
DigestGenerationContract -> Digest
ActionItemsGenerationContract -> ActionItems
MinutesGenerationContract -> Minutes
```

Required supervisor contract:

```python
class DigestSupervisorContract(SupervisorContract):
    ...
```

This generates:

```text
DigestSupervisorContract -> DigestSupervisorReview
```

Required constants:

```python
DIGEST_GENERATION_OUTPUT_CONTRACT = DigestGenerationContract.to_json_template()
DIGEST_SUPERVISOR_OUTPUT_CONTRACT = DigestSupervisorContract.to_json_template()
```

Constant names use:

```text
<TASK_UPPER>_GENERATION_OUTPUT_CONTRACT
<TASK_UPPER>_SUPERVISOR_OUTPUT_CONTRACT
```

Examples:

```text
digest       -> DIGEST
actions -> ACTION_ITEMS
```

Optional fallback:

```python
class DigestFallbackRules(FallbackRules):
    ...

DIGEST_FALLBACK_RULES = DigestFallbackRules()
```

## prompts.py Rules

Required constants:

```python
DIGEST_GENERATION_SYSTEM_PROMPT
DIGEST_SUPERVISOR_DOMAIN_PROMPT
DIGEST_RENDER_PROMPT
DIGEST_RENDER_TEMPLATE_PROMPT
```

Do not shorten `DIGEST_GENERATION_SYSTEM_PROMPT` to `DIGEST_SYSTEM_PROMPT`;
`sync_domain.py` checks the full name.

## steps Rules

For task `digest`, these classes and methods must exist:

```python
class DigestAgent:
    async def run(self, shared_context: str) -> Digest:
        ...

class DigestSupervisor:
    async def review(self, context: str) -> DigestSupervisorReview:
        ...

class DigestRender:
    async def run(self, approved_context: str, template: str = "") -> str:
        ...

    async def stream(self, approved_context: str, template: str = ""):
        ...
```

Supervisor uses `review`, not `run`.

Use the project `LLMClient` interface:

```python
await self.client.structured(
    SYSTEM_PROMPT,
    user_prompt,
    OutputModel,
    OUTPUT_CONTRACT,
)
```

Do not use `with_structured_output()`.

## reports.py Rules

Final reports live in:

```text
domain/<domain>/reports.py
```

Example:

```python
@dataclass
class DigestReport(ModelMixin, DigestReportValidation):
    items: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={"source": "structure"},
    )
    quality_warning: str | None = None
    personalized_text: str | None = field(
        default=None,
        metadata={"source": "rendered"},
    )
```

`sync_domain.py --model` generates `DigestReportValidation` in `models.py` and
refreshes the generated import block in `reports.py`.

## Core Understanding Rule

A domain-specific understanding agent is detected by path:

```text
domain/<domain>/<domain>_core/<domain>_understanding_agent.py
```

For `notes`:

```text
domain/notes/notes_core/notes_understanding_agent.py
```

Class name:

```python
class NotesUnderstandingAgent:
    ...
```

Then run:

```powershell
python tools/codegen/sync_domain.py --domain notes --model
python tools/codegen/sync_domain.py --domain notes
```

The script wires:

```text
notes_core/__init__.py
notes_factory.py
orchestrator.py
NotesState.notes_understanding
```

## Recommended Flow

```powershell
python tools/codegen/register_domain.py --domain notes --name "Notes"

# Optional: add notes_core contracts/prompts/notes_understanding_agent.py
python tools/codegen/sync_domain.py --domain notes --model
python tools/codegen/sync_domain.py --domain notes

python tools/codegen/register_task.py --domain notes --task digest --name "Digest" --with-report

# Customize generated TODOs in contracts.py, prompts.py, steps/*.py, reports.py.
python tools/codegen/sync_domain.py --domain notes --model
python tools/codegen/sync_domain.py --domain notes
python tools/codegen/sync_domain.py --domain notes --check
```


## 手工运维脚本（不在本目录）

非生成类的手工脚本在 `tools/devtools/`：

- `tools/devtools/check_user_profile.py`：自检 `data/{user_id}/user.json` 是否被正确解析与注入
- `tools/devtools/purge_kb_source.py`：按来源列出/清除知识库旧知识块
