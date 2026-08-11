"""Persist final task reports under output/{domain}/{task}/."""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

from .runtime_context import DomainContext


def task_output_dir(ctx: DomainContext, line_name: str) -> Path:
    out_dir = ctx.project_root / "output" / ctx.name / line_name
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def report_to_dict(report: object) -> dict:
    if hasattr(report, "model_dump"):
        return report.model_dump()
    if is_dataclass(report):
        return asdict(report)
    if isinstance(report, dict):
        return report
    return {"value": str(report)}


def report_text(data: dict) -> str:
    for key in (
        "personalized_minutes",
        "personalized_text",
        "outline",
        "rendered",
        "text",
    ):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def save_report_artifacts(
    ctx: DomainContext,
    line_name: str,
    report: object,
    timestamp: str,
) -> dict[str, Path]:
    out_dir = task_output_dir(ctx, line_name)
    data = report_to_dict(report)
    paths: dict[str, Path] = {}
    json_path = out_dir / f"report_{timestamp}.json"
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["json"] = json_path
    text = report_text(data)
    if text:
        md_path = out_dir / f"result_{timestamp}.md"
        md_path.write_text(text, encoding="utf-8")
        paths["text"] = md_path
    return paths


def save_all_reports(
    ctx: DomainContext,
    reports: dict,
    timestamp: str,
) -> dict[str, dict[str, Path]]:
    saved: dict[str, dict[str, Path]] = {}
    for line_name, report in reports.items():
        if line_name not in ctx.task_lines:
            continue
        if line_name in {"mindmap", "knowledge_graph"}:
            continue
        saved[line_name] = save_report_artifacts(ctx, line_name, report, timestamp)
    return saved


__all__ = [
    "report_text",
    "report_to_dict",
    "save_all_reports",
    "save_report_artifacts",
    "task_output_dir",
]
