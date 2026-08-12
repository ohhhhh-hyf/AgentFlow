"""Output persistence: save task reports and export graph artifacts.

合并自 archive.py（报告 JSON/文本落盘）与 exporters.py（导图/图谱导出），
统一负责"最终输出落盘"：

- 报告类任务：``save_all_reports`` 写入 output/{domain}/{task}/ 的 JSON 与 Markdown
- 图类任务：``export_mindmap_*`` / ``export_knowledge_graph`` 导出 HTML/PNG/SVG
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from .knowledge_graph import graphviz_available, render_knowledge_graph_bundle
from .mindmap import (
    markmap_available,
    mindmap_png_available,
    render_mindmap_html,
    render_mindmap_png,
)
from .runtime_context import DomainContext

logger = logging.getLogger(__name__)


# ── 报告类任务落盘 ─────────────────────────────────────────────

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
    *,
    gate_ok: bool | None = None,
) -> dict[str, Path]:
    """落盘 JSON；门禁通过才写 result_*.md，失败写 result_*_rejected.md 备查。

    Args:
        gate_ok: True 通过 / False 失败 / None 未做门禁（无模板）→ 仍写正式 md。
    """
    from .hard_execution import should_write_result_md

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
    if not text:
        return paths

    # has_template：仅当显式走过门禁（True/False）时视为有模板约束
    has_template = gate_ok is not None
    if should_write_result_md(gate_ok, has_template=has_template):
        md_path = out_dir / f"result_{timestamp}.md"
        md_path.write_text(text, encoding="utf-8")
        paths["text"] = md_path
    elif gate_ok is False:
        rej = out_dir / f"result_{timestamp}_rejected.md"
        header = (
            "<!-- 强执行门禁未通过：本文件不作为正式 result，仅供排查 -->\n"
        )
        warn = data.get("quality_warning") or ""
        if warn:
            header += f"<!-- {warn} -->\n\n"
        rej.write_text(header + text, encoding="utf-8")
        paths["rejected"] = rej
        logger.warning(
            "门禁失败，已写入 rejected 文本而非 result.md：%s", rej
        )
    return paths


def save_all_reports(
    ctx: DomainContext,
    reports: dict,
    timestamp: str,
    *,
    gate_by_line: dict[str, bool | None] | None = None,
) -> dict[str, dict[str, Path]]:
    """保存各线报告。

    gate_by_line: 线名 → gate_ok（True/False/None）；False 时不写正式 result.md。
    """
    saved: dict[str, dict[str, Path]] = {}
    gate_by_line = gate_by_line or {}
    for line_name, report in reports.items():
        if line_name not in ctx.task_lines:
            continue
        if line_name in {"mindmap", "knowledge_graph"}:
            continue
        saved[line_name] = save_report_artifacts(
            ctx,
            line_name,
            report,
            timestamp,
            gate_ok=gate_by_line.get(line_name),
        )
    return saved


# ── 图类任务导出 ───────────────────────────────────────────────

def _stamp() -> str:
    """毫秒级时间戳（同秒多次运行不互相覆盖产物）。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def export_mindmap_html(reports: dict, out_dir: Path) -> Path | None:
    mindmap_report = reports.get("mindmap")
    outline = getattr(mindmap_report, "outline", None) if mindmap_report else None
    if not outline or not outline.strip():
        return None
    if not markmap_available():
        logger.warning("未检测到 npx/node，跳过思维导图 HTML 生成")
        return None
    filename = f"mindmap_{_stamp()}.html"
    return render_mindmap_html(outline, out_dir, filename)


async def export_mindmap_png(
    reports: dict, out_dir: Path, html_path: Path | None = None
) -> Path | None:
    mindmap_report = reports.get("mindmap")
    outline = getattr(mindmap_report, "outline", None) if mindmap_report else None
    if not outline or not outline.strip():
        return None
    if not mindmap_png_available():
        logger.warning(
            "未安装 playwright，跳过思维导图 PNG 生成"
            "（安装：pip install playwright && playwright install chromium）"
        )
        return None
    filename = f"mindmap_{_stamp()}.png"
    return await render_mindmap_png(outline, out_dir, filename, html_path=html_path)


def export_knowledge_graph(reports: dict, out_dir: Path) -> dict[str, Path]:
    kg = reports.get("knowledge_graph")
    nodes = getattr(kg, "nodes", None) if kg else None
    if not nodes:
        return {}
    if not graphviz_available():
        logger.warning("未检测到 graphviz（dot），跳过知识图谱 PNG/SVG 生成")
    edges = getattr(kg, "edges", None) or []
    outline = getattr(kg, "outline", "") or ""
    title = str(getattr(kg, "title", "") or "").strip()
    for line in outline.splitlines():
        stripped = line.strip()
        if not title and stripped.startswith("# "):
            title = stripped[2:].strip()
            break
    stem = f"knowledge_graph_{_stamp()}"
    return render_knowledge_graph_bundle(nodes, edges, out_dir, stem, title=title)


__all__ = [
    "export_knowledge_graph",
    "export_mindmap_html",
    "export_mindmap_png",
    "report_text",
    "report_to_dict",
    "save_all_reports",
    "save_report_artifacts",
    "task_output_dir",
]
