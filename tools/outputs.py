"""Output persistence: save task reports and export graph artifacts.

合并自 archive.py（报告 JSON/文本落盘）与 exporters.py（导图/图谱导出），
统一负责"最终输出落盘"：

- 报告类任务：``save_all_reports`` 写入 output/{domain}/{task}/ 的文本产物
- 图类任务：``export_mindmap_*`` / ``export_knowledge_graph`` 导出 HTML/PNG（脑图）或 SVG/HTML（图谱）
"""
from __future__ import annotations

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


def _html_document(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>{title}</title>
  <style>
    body {{ margin: 0; padding: 24px; background: #f0eee9; color: #1c1b19; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .page {{ max-width: 1100px; margin: 0 auto; }}
    .memory-review {{ display: flex; flex-direction: column; border: 1px solid #d4d0c6; background: #fff; border-radius: 8px; overflow: hidden; }}
    .review-heading {{ padding: 12px 16px 8px; font-weight: 650; background: #faf9f6; border-bottom: 1px solid #ebe8e1; }}
    .review-row {{ display: grid; grid-template-columns: minmax(0, 1fr) 1px minmax(230px, 32%); border-bottom: 1px solid #ebe8e1; }}
    .review-row:last-child {{ border-bottom: none; }}
    .review-left {{ padding: 11px 14px; line-height: 1.65; word-break: break-word; }}
    .review-rule {{ background: #c8c4b8; }}
    .review-right {{ padding: 9px 10px; background: #faf9f6; }}
    .mem-mark {{ text-decoration: underline; text-decoration-thickness: 1.5px; text-underline-offset: 3px; background: #fff6c7; }}
    .mem-card {{ display: block; padding: 9px 10px; border-left: 3px solid #6b6860; background: #fff; color: #1c1b19; text-decoration: none; border-radius: 4px; }}
    .mem-card + .mem-card {{ margin-top: 8px; }}
    .mem-card-title {{ font-size: 0.9rem; font-weight: 650; line-height: 1.4; margin-bottom: 6px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
    .mem-card-meta {{ font-size: 0.78rem; color: #6b6860; line-height: 1.35; margin-bottom: 4px; }}
    .mem-card-source {{ font-size: 0.74rem; color: #9a968c; line-height: 1.35; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .review-analysis {{ font-size: 0.8rem; color: #3a3832; line-height: 1.5; margin-top: 4px; white-space: pre-wrap; }}
    .review-fix {{ font-size: 0.78rem; color: #6b6860; line-height: 1.45; margin-top: 4px; }}
    .review-cite {{ font-size: 0.78rem; color: #3a3832; margin-top: 6px; font-weight: 650; }}
    .review-excerpt {{ font-size: 0.76rem; color: #6b6860; margin-top: 4px; line-height: 1.45; }}
    .review-quote {{ font-size: 0.82rem; color: #4a4842; line-height: 1.55; margin-top: 8px; padding: 6px 8px; background: #f7f5f0; border-left: 3px solid #c8c4b8; border-radius: 4px; }}
    .review-note {{ font-size: 0.8rem; color: #6b6860; line-height: 1.5; margin-top: 6px; }}
    .review-tags {{ margin-top: 6px; }}
    .chip {{ display: inline-block; padding: 1px 8px; margin: 2px 4px 0 0; font-size: 0.74rem; color: #3a3832; background: #efece4; border: 1px solid #d4d0c6; border-radius: 10px; }}
    .degree-badge {{ display: inline-block; padding: 1px 9px; margin-right: 6px; font-size: 0.74rem; font-weight: 700; color: #fff; border-radius: 9px; vertical-align: 1px; }}
    .degree-must {{ background: #b3402e; }}
    .degree-key {{ background: #c98a2d; }}
    .degree-know {{ background: #8a867c; }}
    .review-blurb {{ font-size: 0.82rem; color: #3a3832; line-height: 1.6; margin-top: 8px; background: #fbfaf7; border: 1px solid #ebe8e1; border-radius: 6px; padding: 7px 9px; }}
    .mem-empty {{ padding: 10px 12px; color: #9a968c; font-size: 0.78rem; }}
    .quiz-hint {{ font-size: 0.78rem; font-weight: 400; color: #6b6860; margin-top: 4px; }}
    .quiz-item {{ padding: 12px 16px; border-bottom: 1px solid #ebe8e1; }}
    .quiz-item:last-child {{ border-bottom: none; }}
    .quiz-q {{ font-weight: 650; line-height: 1.55; margin-bottom: 6px; }}
    .quiz-dim {{ font-size: 0.76rem; color: #6b6860; margin-bottom: 8px; }}
    .quiz-answer {{ margin: 0; }}
    .quiz-answer summary {{ cursor: pointer; color: #3a3832; font-size: 0.86rem; user-select: none; }}
    .quiz-answer ol {{ margin: 8px 0 0 1.2em; padding: 0; line-height: 1.55; }}
    .quiz-empty {{ padding: 14px 16px; color: #6b6860; }}
    .quiz-section {{ padding: 12px 16px 4px; font-weight: 700; font-size: 0.92rem; background: #f7f5f0; border-bottom: 1px solid #ebe8e1; }}
    .quiz-bank-query {{ padding: 6px 16px 10px; font-size: 0.78rem; color: #6b6860; }}
    .quiz-stem {{ line-height: 1.85; margin: 6px 0 8px; word-break: keep-all; }}
    .quiz-stem p {{ margin: 0 0 .45em; text-indent: 0 !important; }}
    .quiz-formula {{ display: inline !important; vertical-align: middle !important; height: 1.45em; width: auto !important; max-width: none !important; max-height: 2.6em; }}
    .quiz-figure {{ display: block; max-width: 100%; height: auto; margin: 8px 0; }}
    .quiz-blank {{ display: inline-block; min-width: 4em; border-bottom: 1px solid #1c1b19; margin: 0 .15em; }}
    .quiz-opts {{ list-style: none; margin: 0 0 8px; padding: 0; }}
    .quiz-opts li {{ margin: 4px 0; line-height: 1.8; }}
    .quiz-key {{ margin: 8px 0 6px; font-weight: 650; }}
    .quiz-analysis {{ line-height: 1.55; }}
    .library-hero {{ padding: 28px 20px 22px; text-align: center; background: #faf9f6; border-bottom: 1px solid #ebe8e1; }}
    .library-caption {{ margin: 0; font-size: 0.86rem; color: #6b6860; }}
    .library-count {{ margin: 6px 0 0; font-size: 0.95rem; color: #1c1b19; }}
    .library-count strong {{ display: block; font-size: 2.6rem; font-weight: 650; letter-spacing: -0.04em; line-height: 1.05; }}
    .library-files, .library-items, .library-conflicts, .library-peace {{ padding: 12px 16px 16px; }}
    .library-files ul, .library-items ul {{ margin: 0; padding-left: 1.2em; line-height: 1.6; }}
    .library-items span {{ color: #9a968c; font-size: 0.78rem; margin-left: 8px; }}
    .library-verdict {{ margin: 12px 0 0; padding: 12px 14px; border: 1px solid #ebe8e1; border-radius: 8px; background: #fff; }}
    .library-verdict blockquote {{ margin: 8px 0; padding-left: 10px; border-left: 3px solid #c8c4b8; color: #4a4842; font-size: 0.86rem; }}
    .library-ask {{ margin: 10px 0 8px; font-weight: 650; }}
    .library-verdict button {{ margin: 0 8px 0 0; padding: 6px 12px; border: 1px solid #d4d0c6; border-radius: 6px; background: #faf9f6; cursor: pointer; }}
    .library-verdict button.is-on {{ background: #2c2a26; color: #faf9f6; border-color: #2c2a26; }}
    .library-picked {{ min-height: 1.2em; font-size: 0.8rem; color: #6b6860; margin: 8px 0 0; }}
    .library-peace {{ color: #6b6860; }}
    .plain {{ padding: 18px 20px; background: #fff; border: 1px solid #d4d0c6; border-radius: 8px; line-height: 1.65; white-space: pre-wrap; }}
    @media (max-width: 820px) {{ .review-row {{ grid-template-columns: 1fr; }} .review-rule {{ height: 1px; }} }}
  </style>
</head>
<body>
  <main class="page">
{body}
  </main>
</body>
</html>
"""


def save_report_artifacts(
    ctx: DomainContext,
    line_name: str,
    report: object,
    timestamp: str,
    *,
    gate_ok: bool | None = None,
) -> dict[str, Path]:
    """落盘文本产物；门禁通过才写正式 result，失败写 rejected 备查。

    Args:
        gate_ok: True 通过 / False 失败 / None 未做门禁（无模板）→ 仍写正式 md。
    """
    from .hard_execution import should_write_result_md

    out_dir = task_output_dir(ctx, line_name)
    data = report_to_dict(report)
    paths: dict[str, Path] = {}
    text = report_text(data)
    if not text:
        return paths

    # 视角标题（如有）作为 H1 前缀；正文已自带 # 标题时不再重复叠加
    title = str(data.get("title") or "").strip()
    if title and not text.lstrip().startswith("# "):
        text = f"# {title}\n\n{text}"
    html_title = title or ctx.line_cn_names.get(line_name, line_name)

    # has_template：仅当显式走过门禁（True/False）时视为有模板约束
    has_template = gate_ok is not None
    if should_write_result_md(gate_ok, has_template=has_template):
        md_path = out_dir / f"result_{timestamp}.md"
        md_path.write_text(text, encoding="utf-8")
        paths["text"] = md_path
        review_html = (
            data.get("review_html")
            or data.get("quiz_html")
            or data.get("library_html")
            or data.get("catalog_html")
            or data.get("checklist_html")
        )
        if isinstance(review_html, str) and (
            "memory-review" in review_html
            or "quiz-sheet" in review_html
            or "cat-doc" in review_html
            or "ck-doc" in review_html
            or "library-hero" in review_html
        ):
            body = review_html
            html_path = out_dir / f"result_{timestamp}.html"
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
        elif ctx.name == "meeting" and line_name == "minutes_generation":
            from tools.memory.citations import memory_review_html

            review = memory_review_html(text)
            if review:
                body = review
            else:
                import html

                body = f'<div class="plain">{html.escape(text)}</div>'
            html_path = out_dir / f"result_{timestamp}.html"
            html_path.write_text(
                _html_document(html_title, body),
                encoding="utf-8",
            )
            paths["html"] = html_path
        if line_name == "review":
            import json

            corrected = str(data.get("corrected_notes") or "").strip()
            if corrected:
                corr_path = out_dir / f"result_{timestamp}_corrected.md"
                corr_path.write_text(corrected, encoding="utf-8")
                paths["corrected"] = corr_path
            payload = {
                "original_notes": data.get("original_notes") or "",
                "knowledge_points": data.get("knowledge_points") or [],
                "issues": data.get("issues") or [],
                "corrected_notes": corrected,
                "accepted": False,
            }
            payload_path = out_dir / f"result_{timestamp}.review.json"
            payload_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            paths["review"] = payload_path
    elif gate_ok is False:
        rej = out_dir / f"result_{timestamp}_rejected.md"
        # 门禁失败：不写正式 result.md；落盘内容保持干净（无内部注释标记，
        # 避免下载后展示给用户时出现「强执行门禁未通过」等排查信息）
        rej.write_text(text, encoding="utf-8")
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
        logger.warning("未检测到 graphviz（dot），跳过知识图谱 SVG 生成")
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
