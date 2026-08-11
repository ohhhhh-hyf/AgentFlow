"""Runtime domain discovery for the CLI entrypoint."""
from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path


SHORT_ALIASES: dict[str, dict[str, str]] = {
    "meeting": {
        "minutes": "minutes_generation",
        "actions": "action_items",
    },
}


@dataclass
class DomainContext:
    """Runtime metadata that keeps the bootstrap entrypoint domain-agnostic."""

    name: str
    module: object
    config: object
    models: object
    orchestrator: object
    system_cls: type
    samples_dir: Path
    line_cn_names: dict[str, str]
    task_lines: dict[str, dict]
    task_aliases: dict[str, str]
    env_prefix: str
    project_root: Path

    @property
    def cli_samples_dir(self) -> Path:
        return self.project_root / "samples" / self.name

    @property
    def default_file_dir(self) -> Path:
        return self.cli_samples_dir / "file"

    @property
    def default_profile_dir(self) -> Path:
        return self.cli_samples_dir / "profile"

    def default_template_dir(self, line_name: str) -> Path:
        return self.cli_samples_dir / f"{line_name}_template"


def load_domain(name: str, project_root: Path) -> DomainContext:
    """Load domain.<name> modules and build aliases for task names."""
    module = importlib.import_module(f"domain.{name}")
    config = importlib.import_module(f"domain.{name}.domain_config")
    models = importlib.import_module(f"domain.{name}.models")
    orchestrator = importlib.import_module(f"domain.{name}.orchestrator")
    pascal = name[0].upper() + name[1:]
    system_cls = getattr(orchestrator, f"{pascal}AgentSystem")
    line_cn_names = getattr(config, "LINE_CN_NAMES", {})
    task_lines = getattr(orchestrator, "TASK_LINES", {})
    aliases = dict(SHORT_ALIASES.get(name, {}))
    aliases.update({line: line for line in task_lines})
    aliases.update({cn: line for line, cn in line_cn_names.items()})
    return DomainContext(
        name=name,
        module=module,
        config=config,
        models=models,
        orchestrator=orchestrator,
        system_cls=system_cls,
        samples_dir=getattr(module, "SAMPLES_DIR"),
        line_cn_names=line_cn_names,
        task_lines=task_lines,
        task_aliases=aliases,
        env_prefix=name.upper(),
        project_root=project_root,
    )


def env_path(ctx: DomainContext, key: str, default: Path | None) -> Path | None:
    """Read a path from a domain-prefixed environment variable."""
    value = os.getenv(f"{ctx.env_prefix}_{key}", "").strip()
    return Path(value) if value else default


def normalize_tasks(
    ctx: DomainContext, tasks: list[str], known_lines: set[str] | None = None
) -> list[str]:
    """Resolve CLI task names to canonical task line names."""
    known = known_lines or set(ctx.task_lines)
    result: list[str] = []
    for raw in tasks:
        name = raw.strip()
        line = ctx.task_aliases.get(name, name)
        if line not in known:
            raise ValueError(f"未知任务线：{name}（可用：{sorted(known)}）")
        result.append(line)
    return result


__all__ = ["DomainContext", "env_path", "load_domain", "normalize_tasks"]
