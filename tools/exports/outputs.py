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

from tools.exports.knowledge_graph import render_graph_bundle
from tools.exports.mindmap import (
    markmap_available,
    mindmap_png_available,
    render_mindmap_html,
    render_mindmap_png,
)
from tools.runtime_context import DomainContext

logger = logging.getLogger(__name__)


# ── 轻量 Markdown → HTML（产物页面用，无外部依赖）──────────────

def md_to_html(text: str) -> str:
    """把 Markdown 文本渲染成 HTML（标题/表格/列表/粗体/斜体/链接/行内代码/引用）。

    先转义再结构化，防注入；仅覆盖产物页面常用语法。
    """
    import html as _html
    import re as _re

    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    list_buf: list[str] = []
    ol_buf: list[str] = []

    def flush_ul() -> None:
        if list_buf:
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in list_buf) + "</ul>")
            list_buf.clear()

    def flush_ol() -> None:
        if ol_buf:
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in ol_buf) + "</ol>")
            ol_buf.clear()

    def flush_list() -> None:
        flush_ul()
        flush_ol()

    def inline(s: str) -> str:
        esc = _html.escape(s)
        esc = _re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', esc)
        esc = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        esc = _re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", esc)
        esc = _re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)
        return esc

    i = 0
    while i < len(lines):
        line = lines[i]
        m = _re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_list()
            level = min(len(m.group(1)), 6)
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue
        if _re.match(r"^\s*\|.*\|\s*$", line):
            flush_list()
            rows = []
            while i < len(lines) and _re.match(r"^\s*\|.*\|\s*$", lines[i]):
                rows.append([c.strip() for c in lines[i].split("|")[1:-1]])
                i += 1
            if rows:
                head = rows[0]
                body_rows = [
                    r for r in rows[1:]
                    if not all(_re.fullmatch(r":?-+:?", c) for c in r)
                ]
                out.append(
                    "<table><thead><tr>"
                    + "".join(f"<th>{inline(c)}</th>" for c in head)
                    + "</tr></thead><tbody>"
                    + "".join(
                        "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
                        for r in body_rows
                    )
                    + "</tbody></table>"
                )
            continue
        if _re.match(r"^\s*[-*]\s+", line):
            flush_ol()
            list_buf.append(inline(_re.sub(r"^\s*[-*]\s+", "", line)))
            i += 1
            continue
        if _re.match(r"^\s*\d+[.)、]\s+", line):
            flush_ul()
            ol_buf.append(inline(_re.sub(r"^\s*\d+[.)、]\s+", "", line)))
            i += 1
            continue
        if _re.match(r"^\s*>\s?", line):
            flush_list()
            quote = _re.sub(r"^\s*>\s?", "", line)
            out.append(f"<blockquote>{inline(quote)}</blockquote>")
            i += 1
            continue
        if not line.strip():
            flush_list()
            out.append("<br>")
            i += 1
            continue
        flush_list()
        out.append(f"<p>{inline(line)}</p>")
        i += 1
    flush_list()
    return "".join(out)


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
        from tools.memory.store import safe_id

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
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>{title}</title>
  <style>
    body {{ margin: 0; padding: 24px; background: #f0eee9; color: #1c1b19; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .page {{ max-width: 1180px; margin: 0 auto; }}
    .plain {{ padding: 18px 20px; background: #fff; border: 1px solid #d4d0c6; border-radius: 8px; line-height: 1.7; word-break: break-word; }}
    .plain h1, .plain h2, .plain h3, .plain h4 {{ margin: 18px 0 8px; line-height: 1.35; }}
    .plain h1 {{ font-size: 1.5rem; }} .plain h2 {{ font-size: 1.25rem; }}
    .plain h3 {{ font-size: 1.08rem; }} .plain h4 {{ font-size: 1rem; }}
    .plain table {{ border-collapse: collapse; margin: 10px 0; width: 100%; background: #fff; }}
    .plain th, .plain td {{ border: 1px solid #d8d4ca; padding: 7px 10px; font-size: 0.92rem; }}
    .plain th {{ background: #f4f1ea; font-weight: 650; }}
    .plain code {{ background: #efece4; border-radius: 4px; padding: 1px 5px; font-size: 0.88em; }}
    .plain blockquote {{ margin: 8px 0; padding: 6px 12px; border-left: 3px solid #c8c4b8; color: #4a4842; background: #faf9f6; }}
    .plain ul {{ margin: 6px 0; padding-left: 1.4em; }}
    .memory-shell {{ }}
    .memory-legend {{ margin: 0 0 10px; font-size: 0.82rem; color: #6b6860; }}
    .memory-review {{ display: flex; flex-direction: column; border: 1px solid #d4d0c6; background: #fff; border-radius: 8px; overflow: hidden; }}
    .review-heading {{ padding: 14px 16px; font-weight: 700; font-size: 1.15rem; background: #faf9f6; border-bottom: 1px solid #ebe8e1; }}
    .review-head-row, .review-row {{ display: grid; grid-template-columns: minmax(0, 1.4fr) 1px minmax(260px, 34%); }}
    .review-head-row {{ background: #f3f0e8; border-bottom: 1px solid #e2ddd3; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.04em; color: #6b6860; text-transform: none; }}
    .review-head-row .review-left, .review-head-row .review-right {{ padding: 8px 14px; }}
    .review-row {{ border-bottom: 1px solid #ebe8e1; align-items: stretch; }}
    .review-row:last-child {{ border-bottom: none; }}
    .review-row.has-mem {{ background: #fffdf5; }}
    .review-left {{ padding: 12px 16px; line-height: 1.75; word-break: break-word; }}
    .review-rule {{ background: #ddd8cc; }}
    .review-right {{ padding: 10px 12px; background: #f7f5f0; }}
    .mem-mark {{ background: #fff189; border-bottom: 2px solid #e0b400; padding: 0 2px; cursor: pointer; font-style: normal; }}
    .mem-mark.is-on {{ background: #ffd54a; box-shadow: 0 0 0 2px rgba(224,180,0,0.25); }}
    .mem-card {{ display: block; padding: 10px 11px; border-left: 3px solid #c9a227; background: #fffef8; color: #1c1b19; border-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }}
    .mem-card + .mem-card {{ margin-top: 8px; }}
    .mem-card.is-on {{ border-left-color: #9a6b00; box-shadow: 0 0 0 2px rgba(201,162,39,0.35); }}
    .mem-card-title {{ font-size: 0.88rem; font-weight: 650; line-height: 1.45; margin-bottom: 6px; }}
    .mem-card-quote {{ font-size: 0.8rem; color: #4a4842; line-height: 1.5; margin-bottom: 4px; padding: 5px 7px; background: #f7f5f0; border-left: 3px solid #c8c4b8; border-radius: 4px; }}
    .mem-card-time {{ font-size: 0.74rem; color: #9a968c; line-height: 1.35; margin-top: 4px; }}
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
    *,
    gate_ok: bool | None = None,
    memory_on: bool = False,
) -> dict[str, Path]:
    """落盘文本产物；门禁通过才写正式 result，失败写 rejected 备查。

    md 文件名：只落文本的任务线（actions/risks/minutes_styles）按线命名
    （{line_name}.md，与 {line_name}.html 模式对齐），其余固定 result.md；
    目录按请求隔离，不重复叠加时间戳。

    Args:
        gate_ok: True 通过 / False 失败 / None 未做门禁（无模板）→ 仍写正式 md。
    """
    from tools.hard_execution import should_write_result_md

    # md 与 html 同模式按线命名的任务线（无 HTML 产物，file_name 直接指向 md）
    line_named_md = line_name in {"actions", "risks", "minutes_styles", "minutes_trace"}

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
    if line_name in {"minutes", "minutes_trace"} and not has_template:
        from domain.meeting.tasks.minutes.steps.minutes_render import (
            compact_untemplated_minutes,
        )

        text = compact_untemplated_minutes(text)
    html_title = title or ctx.line_cn_names.get(line_name, line_name)
    if should_write_result_md(gate_ok, has_template=has_template):
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
            elif ctx.name == "meeting" and line_name == "minutes":
                from tools.meeting_memory.render import memory_review_html

                review = memory_review_html(text)
                body = review if review else f'<div class="plain">{md_to_html(text)}</div>'
                html_path = out_dir / f"{line_name}.html"
                html_path.write_text(
                    _html_document(html_title, body),
                    encoding="utf-8",
                )
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
    elif gate_ok is False:
        rej = out_dir / "result_rejected.md"
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
    *,
    gate_by_line: dict[str, bool | None] | None = None,
    memory_on: bool = False,
) -> dict[str, dict[str, Path]]:
    """保存各线报告。

    gate_by_line: 线名 → gate_ok（True/False/None）；False 时不写正式 result.md。
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
