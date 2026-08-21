# Domain Scaffolding Scripts

Canonical naming conventions live in `../../SCAFFOLDING_CONVENTIONS.md`.
If this README and the root convention document ever disagree, follow the root
document and update this README.

These scripts create domain/task skeletons and sync generated zones.

The scripts write files as UTF-8. CLI output is intentionally mostly ASCII to
avoid mojibake in Windows PowerShell.

## Scripts

### register_domain.py

Creates a new domain skeleton.

```powershell
python tools/scripts/register_domain.py --domain notes --name "Notes"
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
python tools/scripts/register_task.py --domain notes --task digest --name "Digest"
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
python tools/scripts/register_task.py --domain notes --task digest --name "Digest" --with-report
```

This appends `DigestReport` to `domain/notes/reports.py` if it is missing.

### sync_domain.py

Syncs generated zones from contracts, prompts, reports, and step files.

```powershell
# Models only: generation models, supervisor models, ReportValidation imports.
python tools/scripts/sync_domain.py --domain notes --model

# Full runtime wiring (models / TASK_LINES / factory / Report assemblers).
# Does not generate per-line render_context or fallback nodes.
python tools/scripts/sync_domain.py --domain notes

# Check generated zones.
python tools/scripts/sync_domain.py --domain notes --check
```

If a task line is incomplete, full sync first updates `models.py`, then prints
the missing items and stops before writing incomplete runtime wiring.

## Naming Rules

See `SCAFFOLDING_CONVENTIONS.md` for the complete rules. The key point is that
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
action_items       -> ActionItems
minutes_generation -> MinutesGeneration
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
action_items -> ACTION_ITEMS
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
python tools/scripts/sync_domain.py --domain notes --model
python tools/scripts/sync_domain.py --domain notes
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
python tools/scripts/register_domain.py --domain notes --name "Notes"

# Optional: add notes_core contracts/prompts/notes_understanding_agent.py
python tools/scripts/sync_domain.py --domain notes --model
python tools/scripts/sync_domain.py --domain notes

python tools/scripts/register_task.py --domain notes --task digest --name "Digest" --with-report

# Customize generated TODOs in contracts.py, prompts.py, steps/*.py, reports.py.
python tools/scripts/sync_domain.py --domain notes --model
python tools/scripts/sync_domain.py --domain notes
python tools/scripts/sync_domain.py --domain notes --check
```
