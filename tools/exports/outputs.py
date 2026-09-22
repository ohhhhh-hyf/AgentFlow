"""Output persistence: save task reports and export graph artifacts.

合并自 archive.py（报告 JSON/文本落盘）与 exporters.py（导图/图谱导出），
统一负责"最终输出落盘"：

- 报告类任务：``save_all_reports`` 写入 data/{user_id}/output/ 下的文本产物
- 图类任务：``export_mindmap_*`` / ``export_graph`` 导出 HTML/PNG（脑图）或 SVG/HTML（图谱）
"""
from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from tools.exports.html.knowledge_graph import render_graph_bundle
from tools.exports.html.mindmap import (
    markmap_available,
    mindmap_png_available,
    render_mindmap_html,
    render_mindmap_png,
)
from tools.core.domain_hooks import hooks_for
from tools.core.runtime_context import DomainContext

logger = logging.getLogger(__name__)


# ── 报告类任务落盘 ─────────────────────────────────────────────

def task_output_dir(ctx: DomainContext, line_name: str) -> Path:
    """产物目录：API 设置 ``ctx.output_dir``（data/{user}/output/{request_id}/）时直接用；
    CLI 等未设置时兜底为 ``data/{user}/output/cli_{时间戳}/{line_name}/``，不再写根目录 output/。"""
    requested = getattr(ctx, "output_dir", None)
    if requested:
        out_dir = Path(requested)
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir
    if (ctx.user_id or "").strip():
        from tools.core.ids import safe_id

        uid = safe_id(ctx.user_id)
    else:
        uid = "default"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    out_dir = (
        ctx.project_root / "data" / uid / "output" / f"cli_{stamp}" / line_name
    )
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


def _html_document(title: str, body: str) -> str:
    from tools.exports.html.paper_css import latex_paper_css

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>{title}</title>
  <style>
{latex_paper_css()}
  </style>
</head>
<body>
  <main class="page">
    <div class="ck-doc">
      <header class="ck-doc-header">
        <h1>{title}</h1>
      </header>
      <div class="ck-doc-content">
        {body}
      </div>
    </div>
  </main>
</body>
</html>
"""


def save_report_artifacts(
    ctx: DomainContext,
    line_name: str,
    report: object,
    *,
    gate_ok: bool | None = None,
    memory_on: bool = False,
) -> dict[str, Path]:
    """落盘文本产物；门禁通过才写正式 result，失败写 rejected 备查。

    md 文件名：只落文本的任务线（actions/risks/minutes_styles）按线命名
    （{line_name}.md，与 {line_name}.html 模式对齐），其余固定 result.md；
    目录按请求隔离，不重复叠加时间戳。

    Args:
        gate_ok: True 通过 / False 失败 / None 未做门禁（无模板）。
            **三种情况都写正式 md**：质量信号由 API 的
            ``quality_warning`` 与同目录的 ``result_rejected.md`` 承担，不靠"不落盘"表达。
    """
    # md 与 html 同模式按线命名的任务线（无 HTML 产物，file_name 直接指向 md）
    line_named_md = line_name in {"actions", "risks", "minutes_styles", "minutes_trace", "consensus_decision"}

    out_dir = task_output_dir(ctx, line_name)
    data = report_to_dict(report)
    paths: dict[str, Path] = {}
    text = report_text(data)
    if not text:
        return paths

    # has_template：仅当显式走过门禁（True/False）时视为有模板约束
    has_template = gate_ok is not None
    # 视角标题（如有）作为 H1 前缀；正文已自带 # 标题时不再重复叠加
    title = str(data.get("title") or "").strip()
    if title and not text.lstrip().startswith("# "):
        text = f"# {title}\n\n{text}"
    compact = hooks_for(ctx.name).compact_plain
    if compact is not None and not has_template:
        text = compact(line_name, text)
    html_title = title or ctx.line_cn_names.get(line_name, line_name)
    # 门禁失败也照写正式 result.md（2026-09 决定）：实测出现过「正文合格但门禁误判」
    # （表格写法变体被判「固定文字丢失」），此时不落盘会让用户拿不到可用内容。
    # 质量信号由两条承担：API 的 quality_warning（带门禁原因）与同目录的
    # result_rejected.md（备查副本）。
    # library / graph 只输出 text（API 响应携带），不落盘 md/html；
    # graph 的交互 HTML 由 export_graph 单独落盘（见 runner）
    if line_name not in ("library", "graph"):
        md_path = out_dir / (
            f"{line_name}.md" if line_named_md else "result.md"
        )
        md_path.write_text(text, encoding="utf-8")
        paths["text"] = md_path
        review_html = (
            data.get("review_html")
            or data.get("quiz_html")
            or data.get("library_html")
            or data.get("catalog_html")
            or data.get("checklist_html")
        )
        # 域专属 HTML（没这项钩子就回退通用/工具侧渲染器）
        domain_html: str | None = None
        domain_hooks = hooks_for(ctx.name)
        if domain_hooks.html_for is not None:
            domain_html = domain_hooks.html_for(line_name, html_title, text, data)
        if isinstance(review_html, str) and (
            "memory-review" in review_html
            or "quiz-sheet" in review_html
            or "cat-doc" in review_html
            or "ck-doc" in review_html
            or "library-hero" in review_html
        ):
            body = review_html
            html_path = out_dir / f"{line_name}.html"
            if line_name == "checklist" and body.lstrip()[:15].lower().startswith(
                "<!doctype"
            ):
                html_path.write_text(body, encoding="utf-8")
            else:
                html_path.write_text(
                    _html_document(html_title, body),
                    encoding="utf-8",
                )
            paths["html"] = html_path
        elif domain_html:
            # 域专属渲染器（纪要 / 风险 / 待办 / 溯源）：见 domain/<name>/hooks.py
            html_path = out_dir / f"{line_name}.html"
            html_path.write_text(domain_html, encoding="utf-8")
            paths["html"] = html_path
        elif line_name == "consensus_decision":
            from tools.exports.html.consensus_decision import render_consensus_decision_html

            html_doc = render_consensus_decision_html(html_title, text, data)
            html_path = out_dir / f"{line_name}.html"
            html_path.write_text(html_doc, encoding="utf-8")
            paths["html"] = html_path
    if line_name == "review":
        import json

        corrected = str(data.get("corrected_notes") or "").strip()
        if corrected:
            corr_path = out_dir / "result_corrected.md"
            corr_path.write_text(corrected, encoding="utf-8")
            paths["corrected"] = corr_path
        payload = {
            "original_notes": data.get("original_notes") or "",
            "knowledge_points": data.get("knowledge_points") or [],
            "issues": data.get("issues") or [],
            "corrected_notes": corrected,
            "accepted": False,
        }
        payload_path = out_dir / "result.review.json"
        payload_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths["review"] = payload_path
    if gate_ok is False:
        # 门禁失败也留一份备查副本（便于复盘"门禁到底看到了什么"）；
        # 正式 result.md 照写（门禁失败也写），质量信号由 API 的 quality_warning 承担。
        rej = out_dir / "result_rejected.md"
        rej.write_text(text, encoding="utf-8")
        paths["rejected"] = rej
        logger.warning("gate failed, kept a rejected copy for review: %s", rej)
    return paths


def save_all_reports(
    ctx: DomainContext,
    reports: dict,
    *,
    gate_by_line: dict[str, bool | None] | None = None,
    memory_on: bool = False,
) -> dict[str, dict[str, Path]]:
    """保存各线报告。

    gate_by_line: 线名 → gate_ok（True/False/None），透传给 Report 落盘；三种情况都写 md。
    memory_on: 本次开启会议记忆（meeting+minutes 无命中时也输出左右审阅栏）。
    """
    saved: dict[str, dict[str, Path]] = {}
    gate_by_line = gate_by_line or {}
    for line_name, report in reports.items():
        if line_name not in ctx.task_lines:
            continue
        if line_name in {"mindmap", "graph"}:
            continue
        saved[line_name] = save_report_artifacts(
            ctx,
            line_name,
            report,
            gate_ok=gate_by_line.get(line_name),
            memory_on=memory_on,
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
        logger.warning("npx/node not found, skip mindmap html")
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
        logger.warning("playwright missing, skip mindmap png")
        return None
    filename = f"mindmap_{_stamp()}.png"
    return await render_mindmap_png(outline, out_dir, filename, html_path=html_path)


def export_graph(reports: dict, out_dir: Path) -> dict[str, Path]:
    kg = reports.get("graph")
    nodes = getattr(kg, "nodes", None) if kg else None
    if not nodes:
        return {}
    edges = getattr(kg, "edges", None) or []
    outline = getattr(kg, "outline", "") or ""
    title = str(getattr(kg, "title", "") or "").strip()
    for line in outline.splitlines():
        stripped = line.strip()
        if not title and stripped.startswith("# "):
            title = stripped[2:].strip()
            break
    stem = "graph"
    return render_graph_bundle(nodes, edges, out_dir, stem, title=title)


__all__ = [
    "export_graph",
    "export_mindmap_html",
    "export_mindmap_png",
    "report_text",
    "report_to_dict",
    "save_all_reports",
    "save_report_artifacts",
    "task_output_dir",
]
