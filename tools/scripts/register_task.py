"""register_task.py -- register a task line and create standard templates.

Usage:
    python tools/scripts/register_task.py --domain notes --task points --name "Points"

This script intentionally generates only generic scaffolding. It:
1. adds ``"<task>": "<name>"`` to domain/<domain>/domain_config.py LINE_CN_NAMES;
2. creates task files if they are missing;
3. writes runnable meeting-style templates with TODO business text;
4. optionally appends a Report class with --with-report.
"""
from __future__ import annotations

import argparse
import ast
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_domain as _sync_domain  # noqa: E402
from sync_domain import set_domain  # noqa: E402


def _read_py(path: Path) -> str:
    """Read Python source, accepting UTF-8 files with or without BOM."""
    return path.read_text(encoding="utf-8-sig")


def _pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _write_if_missing(path: Path, text: str) -> bool:
    """Create a file only when it is missing. Return whether it was created."""
    if path.exists():
        return False
    path.write_text(text, encoding="utf-8")
    return True


def _ensure_task_skeleton(task: str, name: str) -> list[Path]:
    """Create standard task templates without overwriting user code."""
    task_dir = _sync_domain.CURRENT.tasks_dir / task
    steps_dir = task_dir / "steps"
    task_dir.mkdir(parents=True, exist_ok=True)
    steps_dir.mkdir(parents=True, exist_ok=True)

    pascal = _pascal(task)
    upper = task.upper()
    state_cls = _sync_domain.CURRENT.state_class()
    created: list[Path] = []

    files = {
        task_dir / "__init__.py": f'''"""{task} -- {name} task line.

Required implementation classes:
- steps/{task}_agent.py: class {pascal}Agent with async def run(...)
- steps/{task}_supervisor.py: class {pascal}Supervisor with async def review(...)
- steps/{task}_render.py: class {pascal}Render with async def run(...) and async def stream(...)
"""
''',
        task_dir / "contracts.py": f'''"""{task} contract definitions.

Required by tools/scripts/sync_domain.py:
- class {pascal}GenerationContract(GenerationContract)
- class {pascal}SupervisorContract(SupervisorContract)
- {upper}_GENERATION_OUTPUT_CONTRACT = {pascal}GenerationContract.to_json_template()
- {upper}_SUPERVISOR_OUTPUT_CONTRACT = {pascal}SupervisorContract.to_json_template()

Optional fallback:
- class {pascal}FallbackRules(FallbackRules)
- {upper}_FALLBACK_RULES = {pascal}FallbackRules()
"""
from __future__ import annotations

from tools.contracts import (
    Check, Decision, Feedback, GenerationContract, ObjListField, StrField,
    SupervisorContract,
)
from tools.fallback_rules import FallbackRules, Lines


class {pascal}GenerationContract(GenerationContract):
    """TODO: replace generic items with {name}-specific fields."""

    fields = [
        ObjListField("items", [
            StrField("title", "TODO: item title"),
            StrField("summary", "TODO: item summary"),
            StrField("evidence", "TODO: source evidence"),
        ]),
    ]


class {pascal}SupervisorContract(SupervisorContract):
    """TODO: define strict review checks for {name}."""

    decision = Decision()
    feedback = Feedback("Only fill when decision=revise; be specific and evidence-based")
    checks = [
        Check("{task}_check", "TODO: describe severe issues only"),
    ]


{upper}_GENERATION_OUTPUT_CONTRACT = {pascal}GenerationContract.to_json_template()
{upper}_SUPERVISOR_OUTPUT_CONTRACT = {pascal}SupervisorContract.to_json_template()


class {pascal}FallbackRules(FallbackRules):
    """Fallback assembly for {name}: keep structured items."""

    sections = [
        Lines("items"),
    ]
    empty_text = "No explicit items"
    structured = {{"field": "items"}}


{upper}_FALLBACK_RULES = {pascal}FallbackRules()

__all__ = [
    "{upper}_GENERATION_OUTPUT_CONTRACT",
    "{upper}_SUPERVISOR_OUTPUT_CONTRACT",
    "{upper}_FALLBACK_RULES",
]
''',
        task_dir / "prompts.py": f'''"""{task} prompt definitions.

Required by tools/scripts/sync_domain.py:
- {upper}_GENERATION_SYSTEM_PROMPT
- {upper}_SUPERVISOR_DOMAIN_PROMPT
- {upper}_RENDER_PROMPT
- {upper}_RENDER_TEMPLATE_PROMPT

Do not shorten {upper}_GENERATION_SYSTEM_PROMPT to {upper}_SYSTEM_PROMPT;
sync_domain.py checks the full name.
"""
from __future__ import annotations

from tools.template_prompt import build_template_render_prompt


{upper}_GENERATION_SYSTEM_PROMPT = """You are the {name} generation agent.

TODO:
- Describe exactly what to extract or generate.
- State that the output must stay faithful to the source text.
- State what should be left empty when evidence is missing.
- Keep the structured output aligned with {upper}_GENERATION_OUTPUT_CONTRACT.
"""


{upper}_SUPERVISOR_DOMAIN_PROMPT = """## Domain review rules for {name}

TODO:
- Define severe issues that should trigger revise.
- Define what should not block approval.
- Keep feedback specific, actionable, and evidence-based.
"""


{upper}_RENDER_PROMPT = """You are the {name} renderer.

Render the approved structured result into clear Markdown.
Do not add facts that are not present in the approved result.
"""


{upper}_RENDER_TEMPLATE_PROMPT = build_template_render_prompt(
    renderer="{name} renderer",
    source="approved structured result",
    empty_rule="When the result is empty, follow the template's empty-content rule.",
)
''',
        steps_dir / "__init__.py": f'"""{task} pipeline steps: agent / supervisor / render."""\n',
        steps_dir / f"{task}_agent.py": f'''from __future__ import annotations

from llm_client import LLMClient

from ....models import {pascal}
from ..contracts import {upper}_GENERATION_OUTPUT_CONTRACT
from ..prompts import {upper}_GENERATION_SYSTEM_PROMPT


class {pascal}Agent:
    """Generate the structured {name} draft."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> {pascal}:
        return await self.client.structured(
            {upper}_GENERATION_SYSTEM_PROMPT,
            shared_context,
            {pascal},
            {upper}_GENERATION_OUTPUT_CONTRACT,
        )
''',
        steps_dir / f"{task}_supervisor.py": f'''from __future__ import annotations

from supervisor import GlobalSupervisor

from llm_client import LLMClient
from ....models import {pascal}SupervisorReview
from ..contracts import {upper}_SUPERVISOR_OUTPUT_CONTRACT
from ..prompts import {upper}_SUPERVISOR_DOMAIN_PROMPT


class {pascal}Supervisor:
    """Review the {name} draft."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(
            {upper}_SUPERVISOR_DOMAIN_PROMPT
        )

    async def review(self, context: str) -> {pascal}SupervisorReview:
        return await self.client.structured(
            self._system_prompt,
            context,
            {pascal}SupervisorReview,
            {upper}_SUPERVISOR_OUTPUT_CONTRACT,
        )
''',
        steps_dir / f"{task}_render.py": f'''from __future__ import annotations

from collections.abc import AsyncIterator

from llm_client import LLMClient
from tools.prompt_utils import build_render_prompt

from ....models import {state_cls}
from ..prompts import {upper}_RENDER_PROMPT, {upper}_RENDER_TEMPLATE_PROMPT


class {pascal}Render:
    """Render the approved {name} result."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        return build_render_prompt(
            context,
            template,
            {upper}_RENDER_PROMPT,
            {upper}_RENDER_TEMPLATE_PROMPT,
        )

    async def run(self, approved_context: str, template: str = "") -> str:
        prompt, user = self._prompt_and_user(approved_context, template)
        return await self.client.text(prompt, user)

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        prompt, user = self._prompt_and_user(approved_context, template)
        async for chunk in self.client.stream_text(prompt, user):
            yield chunk

    @staticmethod
    def extract_items(state: {state_cls}) -> list[dict]:
        draft = (
            (state.get("lines") or {{}})
            .get("{task}", {{}})
            .get("draft")
            or {{}}
        )
        return list(draft.get("items") or [])
''',
    }

    for path, text in files.items():
        if _write_if_missing(path, text):
            created.append(path)

    return created


def _append_report_if_missing(task: str) -> bool:
    """Append a generic Report class to reports.py when it is missing."""
    path = _sync_domain.CURRENT.reports_path
    pascal = _pascal(task)
    report_cls = f"{pascal}Report"
    raw = _read_py(path)
    if f"class {report_cls}" in raw:
        return False

    suffix = "" if raw.endswith(("\n", "\r\n")) else "\n"
    block = f'''

@dataclass
class {report_cls}(ModelMixin, {report_cls}Validation):
    """Final report for {task}."""

    items: list[dict[str, Any]] = field(
        default_factory=list,
        metadata={{"source": "structure"}},
    )
    quality_warning: str | None = None
    personalized_text: str | None = field(
        default=None,
        metadata={{"source": "rendered"}},
    )
'''
    path.write_text(raw + suffix + block, encoding="utf-8")
    return True


def _register_line(task: str, name: str) -> bool:
    """Register the task line in domain_config.py LINE_CN_NAMES."""
    path = _sync_domain.CURRENT.dir / "domain_config.py"
    if not path.exists():
        raise SystemExit(
            f"{path} does not exist. Run register_domain.py first."
        )

    raw = _read_py(path)
    tree = ast.parse(raw)
    dict_node = None
    target_name = None

    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "LINE_CN_NAMES"
        ):
            dict_node, target_name = node.value, node.target.id
            break
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "LINE_CN_NAMES"
            for t in node.targets
        ):
            dict_node, target_name = node.value, node.targets[0].id
            break

    if not isinstance(dict_node, ast.Dict):
        raise SystemExit(f"{path} does not define LINE_CN_NAMES as a dict.")

    keys = [k.value for k in dict_node.keys if k is not None]
    if task in keys:
        return False

    lines = raw.split("\n")
    if dict_node.end_lineno == dict_node.lineno:
        lines[dict_node.end_lineno - 1] = (
            f'{target_name}: dict[str, str] = {{\n    "{task}": "{name}",\n}}'
        )
    else:
        lines.insert(dict_node.end_lineno - 1, f'    "{task}": "{name}",')
    path.write_text("\n".join(lines), encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Register a task line and create standard templates."
    )
    parser.add_argument(
        "--domain",
        required=True,
        help="Target domain directory name, for example notes.",
    )
    parser.add_argument(
        "--task",
        required=True,
        metavar="TASK",
        help="Task directory name, for example points or action_items.",
    )
    parser.add_argument(
        "--name",
        required=True,
        metavar="NAME",
        help="Display name, for example Points.",
    )
    parser.add_argument(
        "--with-report",
        action="store_true",
        help="Append a generic Report class to domain/<domain>/reports.py if missing.",
    )
    args = parser.parse_args()

    try:
        set_domain(args.domain)
        registered = _register_line(args.task, args.name)
        created = _ensure_task_skeleton(args.task, args.name)
        report_added = _append_report_if_missing(args.task) if args.with_report else False
        task_dir = _sync_domain.CURRENT.tasks_dir / args.task
        rel_task_dir = task_dir.relative_to(_sync_domain.ROOT)

        print(f"SUCCESS! Task line is ready: {rel_task_dir}")
        if registered:
            print(f"- Registered LINE_CN_NAMES entry: {args.task} -> {args.name}")
        else:
            print(f"- LINE_CN_NAMES already contains: {args.task}")
        if created:
            print("- Created files:")
            for path in created:
                print(f"  - {path.relative_to(_sync_domain.ROOT)}")
        else:
            print("- No files created; skeleton already existed.")
        if args.with_report:
            if report_added:
                print(f"- Appended Report class to: {_sync_domain.CURRENT.reports_path.relative_to(_sync_domain.ROOT)}")
            else:
                print("- Report class already exists or was not changed.")

        upper = args.task.upper()
        pascal = _pascal(args.task)
        print("")
        print("Required names for sync_domain.py:")
        print(f"- contracts.py: class {pascal}GenerationContract")
        print(f"- contracts.py: class {pascal}SupervisorContract")
        print(f"- contracts.py: {upper}_GENERATION_OUTPUT_CONTRACT")
        print(f"- contracts.py: {upper}_SUPERVISOR_OUTPUT_CONTRACT")
        print(f"- prompts.py: {upper}_GENERATION_SYSTEM_PROMPT")
        print(f"- prompts.py: {upper}_SUPERVISOR_DOMAIN_PROMPT")
        print(f"- prompts.py: {upper}_RENDER_PROMPT")
        print(f"- prompts.py: {upper}_RENDER_TEMPLATE_PROMPT")
        print(f"- steps/{args.task}_agent.py: class {pascal}Agent + async def run")
        print(
            f"- steps/{args.task}_supervisor.py: "
            f"class {pascal}Supervisor + async def review"
        )
        print(
            f"- steps/{args.task}_render.py: "
            f"class {pascal}Render + async def run + async def stream"
        )
        print(
            f"- reports.py: class {pascal}Report(ModelMixin, "
            f"{pascal}ReportValidation)"
        )
        print("")
        print("Next:")
        print(f"  1. Review and customize domain/{args.domain}/tasks/{args.task}/contracts.py")
        print(f"  2. Review and customize domain/{args.domain}/tasks/{args.task}/prompts.py")
        print(f"  3. Run: python tools/scripts/sync_domain.py --domain {args.domain} --model")
        if args.with_report:
            print(f"  4. Review generated steps and domain/{args.domain}/reports.py")
        else:
            print(f"  4. Review generated steps and add {pascal}Report to domain/{args.domain}/reports.py")
        print(f"  5. Run: python tools/scripts/sync_domain.py --domain {args.domain}")
        print(f"  6. Run: python tools/scripts/sync_domain.py --domain {args.domain} --check")
    except SystemExit as e:
        if isinstance(e.code, int):
            rc = e.code
        else:
            print(e.code, file=sys.stderr)
            rc = 1
        print("FAIL!!!")
        sys.exit(rc)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        print("FAIL!!!")
        sys.exit(1)


if __name__ == "__main__":
    main()
