"""把原始纪要 Markdown 与视觉 IR 合成最终 HTML。

保证 100% 原始 Markdown 完整无损渲染；
视觉块精准穿插在所属 Section 的标题下方，实现图文呼应。
"""
from __future__ import annotations

import re
from typing import Dict, Optional

from markdown_it import MarkdownIt

from ..models.ir import SectionVisual, VisualDocumentIR
from ..parsing.parser import ParsedMinutes, SectionNode, parse_minutes
from .renderer import TASTE_CSS, escape, render_master, render_visual

MARKDOWN_BODY_CSS = """
.markdown-body {
  font-family: var(--vm-font-sans);
  font-size: 15px;
  line-height: 1.75;
  color: var(--vm-ink-body);
}

.markdown-body h1 {
  font-size: clamp(1.4rem, 2.2vw, 1.8rem);
  font-weight: 700;
  color: var(--vm-ink-title);
  margin: 36px 0 18px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--vm-border);
  letter-spacing: -0.02em;
}

.markdown-body h2 {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--vm-ink-title);
  margin: 40px 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--vm-border);
  letter-spacing: -0.015em;
}

.markdown-body h3 {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--vm-ink-title);
  margin: 28px 0 14px;
  line-height: 1.4;
}

.markdown-body p {
  margin: 0 0 14px;
}

.markdown-body ul, .markdown-body ol {
  margin: 0 0 18px;
  padding-left: 22px;
}

.markdown-body li {
  margin-bottom: 6px;
  line-height: 1.7;
}

.markdown-body li::marker {
  color: var(--vm-ink-subtle);
}

.markdown-body blockquote {
  margin: 20px 0;
  padding: 12px 18px;
  background: var(--vm-tone-stone);
  border-left: 3px solid var(--vm-accent-blue);
  border-radius: 0 var(--vm-radius) var(--vm-radius) 0;
  color: var(--vm-ink-muted);
}

.markdown-body code {
  font-family: var(--vm-font-mono);
  font-size: 85%;
  background: var(--vm-tone-stone);
  padding: .15em .35em;
  border-radius: 4px;
}

.markdown-body pre {
  overflow-x: auto;
  padding: 16px;
  background: var(--vm-tone-stone);
  border-radius: var(--vm-radius);
}

.markdown-body table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  word-break: break-word;
  margin: 18px 0;
}

.markdown-body th, .markdown-body td {
  border: 1px solid var(--vm-border);
  padding: 10px 12px;
}

.markdown-body th {
  background: var(--vm-tone-stone);
  font-weight: 700;
}

.markdown-body img {
  max-width: 100%;
  height: auto;
}
"""

LAYOUT_CSS = """
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #F8F9FA;
  color: var(--vm-ink-body);
  font-family: var(--vm-font-sans);
  -webkit-font-smoothing: antialiased;
}

.vm-doc {
  max-width: 980px;
  margin: 36px auto;
  padding: 44px 54px;
  background: #FFFFFF;
  border: 1px solid var(--vm-border);
  border-radius: 14px;
  box-shadow: 0 4px 24px -2px rgba(0, 0, 0, 0.03);
}

.vm-doc-header {
  margin-bottom: 28px;
}

.vm-doc-footer {
  margin-top: 56px;
  padding-top: 22px;
  border-top: 1px solid var(--vm-border);
  text-align: center;
  font-size: 12px;
  color: var(--vm-ink-faint);
}

.vm-section {
  margin: 0;
}

@media (max-width: 768px) {
  .vm-doc {
    margin: 0;
    border: 0;
    border-radius: 0;
    padding: 24px 18px;
  }
}
"""


class DocumentCompositor:
    def __init__(self) -> None:
        self.md = MarkdownIt("commonmark").enable("table").enable("strikethrough")

    def _render_section_with_visual(
        self, section: SectionNode, visual_html: str
    ) -> str:
        tokens = self.md.parse(section.markdown)
        for token in tokens:
            if token.type == "heading_open":
                token.attrSet("id", section.section_id)
                break
        rendered = self.md.renderer.render(tokens, self.md.options, {})
        if not visual_html:
            return rendered

        # 优先穿插在第一个标题闭合标签之后，实现图文呼应
        match = re.search(
            r"(<h[1-6][^>]*>.*?</h[1-6]>)",
            rendered,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            end_pos = match.end()
            return rendered[:end_pos] + f"\n{visual_html}\n" + rendered[end_pos:]
        return rendered + f"\n{visual_html}\n"

    def composite(
        self,
        parsed: ParsedMinutes | str,
        ir: VisualDocumentIR,
        *,
        output_path: Optional[str] = None,
    ) -> str:
        if isinstance(parsed, str):
            parsed = parse_minutes(parsed)

        by_section: Dict[str, SectionVisual] = {
            item.section_id: item for item in ir.sections if item.visual is not None
        }

        parts: list[str] = []
        if parsed.preamble_markdown.strip():
            parts.append(self.md.render(parsed.preamble_markdown))

        for section in parsed.sections:
            visual = by_section.get(section.section_id)
            visual_html = (
                render_visual(visual.visual)
                if visual and visual.visual
                else ""
            )
            section_html = self._render_section_with_visual(section, visual_html)
            parts.append(
                f'<section class="vm-section" data-section-id="{section.section_id}">'
                f"{section_html}</section>"
            )

        body = "".join(parts)
        master_html = render_master(ir.master)

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(ir.master.headline)}</title>
<style>
{TASTE_CSS}
{MARKDOWN_BODY_CSS}
{LAYOUT_CSS}
</style>
</head>
<body>
<div class="vm-doc">
  <header class="vm-doc-header">{master_html}</header>
  <main class="markdown-body">{body}</main>
  <footer class="vm-doc-footer">智能图文纪要系统 · 商业级双流推断与渲染引擎</footer>
</div>
</body>
</html>"""
        return html


__all__ = ["DocumentCompositor"]
