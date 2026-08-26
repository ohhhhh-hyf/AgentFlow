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

from tools.exports.knowledge_graph import graphviz_available, render_knowledge_graph_bundle
from tools.exports.mindmap import (
    markmap_available,
    mindmap_png_available,
    render_mindmap_html,
    render_mindmap_png,
)
from tools.runtime_context import DomainContext

logger = logging.getLogger(__name__)


# ── 报告类任务落盘 ─────────────────────────────────────────────

def task_output_dir(ctx: DomainContext, line_name: str) -> Path:
    """产物目录：有 user 时 ``output/{user_id}/{domain}/{line_name}``，否则旧路径。"""
    if (ctx.user_id or "").strip():
        from tools.memory.store import safe_id

        out_dir = (
            ctx.project_root / "output" / safe_id(ctx.user_id) / ctx.name / line_name
        )
    else:
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


import html
import re


def _format_inline_md(text: str) -> str:
    if not text:
        return ""
    # Code `...` first to protect code blocks and identifiers like `minutes_trace`
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Bold **...**
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic *...* (requires non-whitespace inside and boundary checks, avoids snake_case _ identifiers)
    text = re.sub(r"(?<!\*)\*([^\s\*](?:[^\*]*[^\s\*])?)\*(?!\*)", r"<em>\1</em>", text)
    # Strikethrough ~~...~~
    text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)
    return text


def render_markdown_to_html(md_text: str) -> str:
    """纯 Python Markdown 转结构化 HTML 渲染器。"""
    if not md_text or not md_text.strip():
        return '<p class="empty-doc">暂无内容</p>'

    lines = md_text.strip().splitlines()
    html_out: list[str] = []
    in_code_block = False
    code_lang = ""
    code_lines: list[str] = []
    in_ul = False
    in_ol = False
    in_table = False
    table_rows: list[list[str]] = []

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            html_out.append("</ul>")
            in_ul = False
        if in_ol:
            html_out.append("</ol>")
            in_ol = False

    def close_table():
        nonlocal in_table, table_rows
        if in_table and table_rows:
            html_out.append('<div class="table-wrap"><table class="doc-table">')
            if len(table_rows) >= 1:
                html_out.append("<thead><tr>")
                for cell in table_rows[0]:
                    html_out.append(f"<th>{_format_inline_md(cell.strip())}</th>")
                html_out.append("</tr></thead>")
            if len(table_rows) > 1:
                html_out.append("<tbody>")
                for row in table_rows[1:]:
                    html_out.append("<tr>")
                    for cell in row:
                        html_out.append(f"<td>{_format_inline_md(cell.strip())}</td>")
                    html_out.append("</tr>")
                html_out.append("</tbody>")
            html_out.append("</table></div>")
            in_table = False
            table_rows = []

    for line in lines:
        raw_line = line
        stripped = line.strip()

        # Code block fence
        if stripped.startswith("```"):
            if in_code_block:
                code_content = html.escape("\n".join(code_lines))
                html_out.append(f'<pre class="code-block"><code class="language-{code_lang}">{code_content}</code></pre>')
                in_code_block = False
                code_lines = []
            else:
                close_lists()
                close_table()
                in_code_block = True
                code_lang = stripped.lstrip("`").strip() or "text"
            continue

        if in_code_block:
            code_lines.append(raw_line)
            continue

        if not stripped:
            close_lists()
            close_table()
            continue

        # Horizontal rule
        if stripped in {"---", "***", "___"} or re.match(r"^[-*_]{3,}$", stripped):
            close_lists()
            close_table()
            html_out.append('<hr class="doc-divider"/>')
            continue

        # Table row
        if stripped.startswith("|") and stripped.endswith("|"):
            close_lists()
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                continue
            cells = [c for c in stripped.split("|")[1:-1]]
            if not in_table:
                in_table = True
                table_rows = []
            table_rows.append(cells)
            continue
        else:
            close_table()

        # Heading
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            close_lists()
            level = len(heading_match.group(1))
            heading_content = _format_inline_md(heading_match.group(2))
            html_out.append(f'<h{level} class="doc-h{level}">{heading_content}</h{level}>')
            continue

        # Bullet list item
        ul_match = re.match(r"^[-*+]\s+(.*)$", stripped)
        if ul_match:
            if in_ol:
                html_out.append("</ol>")
                in_ol = False
            if not in_ul:
                html_out.append('<ul class="doc-ul">')
                in_ul = True
            item_content = _format_inline_md(ul_match.group(1))
            html_out.append(f"<li>{item_content}</li>")
            continue

        # Numbered list item
        ol_match = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if ol_match:
            if in_ul:
                html_out.append("</ul>")
                in_ul = False
            if not in_ol:
                html_out.append('<ol class="doc-ol">')
                in_ol = True
            item_content = _format_inline_md(ol_match.group(2))
            html_out.append(f"<li>{item_content}</li>")
            continue

        # Blockquote
        if stripped.startswith(">"):
            close_lists()
            quote_content = _format_inline_md(stripped.lstrip("> ").strip())
            html_out.append(f'<blockquote class="doc-quote"><p>{quote_content}</p></blockquote>')
            continue

        # Normal paragraph
        close_lists()
        p_content = _format_inline_md(stripped)
        html_out.append(f'<p class="doc-p">{p_content}</p>')

    if in_code_block and code_lines:
        code_content = html.escape("\n".join(code_lines))
        html_out.append(f'<pre class="code-block"><code>{code_content}</code></pre>')
    close_lists()
    close_table()

    return "\n".join(html_out)


def _html_document(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>{title}</title>
  <style>
    body {{ margin: 0; padding: 24px; background: #f0eee9; color: #1c1b19; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
    .page {{ max-width: 1100px; margin: 0 auto; }}

    /* 两栏记忆溯源 review 视图 */
    .memory-review {{ display: flex; flex-direction: column; border: 1px solid #d4d0c6; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.03); }}
    .review-heading {{ padding: 14px 18px 10px; font-weight: 700; background: #faf9f6; border-bottom: 1px solid #ebe8e1; color: #1c1b19; }}
    .review-heading.h1 {{ font-size: 1.35rem; border-left: 4px solid #0d47a1; }}
    .review-heading.h2 {{ font-size: 1.12rem; border-left: 3px solid #1976d2; margin-top: 6px; }}
    .review-heading.h3 {{ font-size: 0.98rem; border-left: 2px solid #64b5f6; }}
    .review-row {{ display: grid; grid-template-columns: minmax(0, 1fr) 1px minmax(240px, 32%); border-bottom: 1px solid #ebe8e1; }}
    .review-row:last-child {{ border-bottom: none; }}
    .review-left {{ padding: 10px 16px; line-height: 1.7; word-break: break-word; font-size: 0.88rem; color: #2c2a26; }}
    .review-left.list-item {{ display: flex; gap: 8px; }}
    .review-left .bullet {{ color: #0d47a1; font-weight: 700; flex-shrink: 0; }}
    .review-left.num-item {{ display: flex; gap: 8px; }}
    .review-left .num-badge {{ display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #e3f2fd; color: #0d47a1; font-size: 0.72rem; font-weight: 700; flex-shrink: 0; margin-top: 2px; }}
    .review-rule {{ background: #e0dcd3; }}
    .review-right {{ padding: 10px 12px; background: #faf9f6; display: flex; flex-direction: column; justify-content: center; }}
    .mem-mark {{ text-decoration: underline; text-decoration-thickness: 1.8px; text-underline-offset: 3px; background: #fff8d6; padding: 1px 3px; border-radius: 2px; }}
    .mem-card {{ display: block; padding: 10px 12px; border-left: 3px solid #0d47a1; background: #fff; color: #1c1b19; text-decoration: none; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); transition: transform 0.15s ease, box-shadow 0.15s ease; }}
    .mem-card:hover {{ transform: translateY(-1px); box-shadow: 0 3px 8px rgba(0,0,0,0.08); }}
    .mem-card + .mem-card {{ margin-top: 8px; }}
    .mem-card-title {{ font-size: 0.84rem; font-weight: 650; line-height: 1.45; margin-bottom: 5px; color: #0f172a; }}
    .mem-card-meta {{ font-size: 0.76rem; color: #64748b; line-height: 1.4; margin-bottom: 3px; }}
    .mem-card-source {{ font-size: 0.72rem; color: #0284c7; line-height: 1.35; font-weight: 500; }}
    .mem-empty {{ min-height: 20px; }}

    /* 单栏文档排版渲染视图 (.markdown-body) */
    .markdown-body {{ padding: 32px 36px; background: #ffffff; border: 1px solid #d4d0c6; border-radius: 8px; line-height: 1.75; font-size: 0.92rem; color: #2c2a26; box-shadow: 0 2px 10px rgba(0,0,0,0.03); }}
    .markdown-body h1, .doc-h1 {{ font-size: 1.55rem; font-weight: 750; margin: 0 0 16px; padding-bottom: 8px; border-bottom: 2px solid #0d47a1; color: #0f172a; }}
    .markdown-body h2, .doc-h2 {{ font-size: 1.25rem; font-weight: 700; margin: 24px 0 12px; color: #1e293b; border-left: 3px solid #1976d2; padding-left: 10px; }}
    .markdown-body h3, .doc-h3 {{ font-size: 1.05rem; font-weight: 650; margin: 18px 0 8px; color: #334155; }}
    .markdown-body p, .doc-p {{ margin: 0 0 12px; }}
    .markdown-body ul, .doc-ul {{ margin: 0 0 14px; padding-left: 20px; }}
    .markdown-body ol, .doc-ol {{ margin: 0 0 14px; padding-left: 20px; }}
    .markdown-body li {{ margin-bottom: 6px; }}
    .markdown-body strong {{ color: #0f172a; font-weight: 650; }}
    .markdown-body blockquote, .doc-quote {{ margin: 14px 0; padding: 10px 16px; border-left: 4px solid #cbd5e1; background: #f8fafc; color: #475569; border-radius: 0 4px 4px 0; }}
    .doc-divider {{ border: none; border-top: 1px solid #e2e8f0; margin: 20px 0; }}
    .table-wrap {{ overflow-x: auto; margin: 16px 0; }}
    .doc-table {{ width: 100%; border-collapse: collapse; font-size: 0.86rem; }}
    .doc-table th, .doc-table td {{ border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; }}
    .doc-table th {{ background: #f1f5f9; font-weight: 650; color: #1e293b; }}
    .doc-table tr:nth-child(even) {{ background: #f8fafc; }}
    .code-block {{ background: #1e293b; color: #f8fafc; padding: 12px 16px; border-radius: 6px; overflow-x: auto; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 0.82rem; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; background: #f1f5f9; color: #0f172a; padding: 2px 5px; border-radius: 3px; font-size: 0.84rem; }}

    .plain {{ padding: 18px 20px; background: #fff; border: 1px solid #d4d0c6; border-radius: 8px; line-height: 1.65; white-space: pre-wrap; }}
    @media (max-width: 820px) {{ .review-row {{ grid-template-columns: 1fr; }} .review-rule {{ height: 1px; }} .markdown-body {{ padding: 20px; }} }}
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
    from tools.hard_execution import should_write_result_md

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
                body = f'<div class="markdown-body">{render_markdown_to_html(text)}</div>'
            html_path = out_dir / f"result_{timestamp}.html"
            html_path.write_text(
                _html_document(html_title, body),
                encoding="utf-8",
            )
            paths["html"] = html_path
        else:
            body = f'<div class="markdown-body">{render_markdown_to_html(text)}</div>'
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
