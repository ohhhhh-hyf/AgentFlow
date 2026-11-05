"""把原始纪要 Markdown 与视觉 IR 合成最终 HTML。

支持飞书同款左侧目录导航栏（TOC Outline）、第一张全景大图归入“## 总览”、
保证 100% 原始 Markdown 完整无损渲染，平滑跳转与滚动联动。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from markdown_it import MarkdownIt

from ..models.ir import SectionVisual, VisualDocumentIR
from ..parsing.parser import ParsedMinutes, SectionNode, parse_minutes
from .renderer import TASTE_CSS, escape, render_master, render_visual

# 提取并保留已内嵌的高清小艺图标
from .xiaoyi_icon_uri import XIAOYI_ICON_DATA_URI

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
  color: #FFFFFF;
  margin: 36px 0 18px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--vm-border);
  letter-spacing: -0.02em;
  scroll-margin-top: 24px;
}

.markdown-body h2 {
  font-size: 1.25rem;
  font-weight: 700;
  color: #FFFFFF;
  margin: 40px 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--vm-border);
  letter-spacing: -0.015em;
  scroll-margin-top: 24px;
}

.markdown-body h3 {
  font-size: 1.05rem;
  font-weight: 700;
  color: #FFFFFF;
  margin: 28px 0 14px;
  line-height: 1.4;
  scroll-margin-top: 24px;
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
  margin: 12px 0 24px;
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.03);
  border-left: 3px solid var(--vm-accent-gold);
  border-radius: 0 8px 8px 0;
  color: var(--vm-ink-body);
  backdrop-filter: blur(10px);
}

.markdown-body blockquote p {
  margin: 0;
  color: var(--vm-ink-body);
  line-height: 1.7;
}

.markdown-body code {
  font-family: var(--vm-font-mono);
  font-size: 85%;
  background: rgba(6, 10, 19, 0.55);
  color: var(--vm-accent-gold-light);
  border: 1px solid rgba(255, 255, 255, 0.12);
  padding: .15em .4em;
  border-radius: 4px;
}

.markdown-body pre {
  overflow-x: auto;
  padding: 16px;
  background: rgba(6, 10, 19, 0.65);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: var(--vm-radius);
  box-shadow: inset 0 2px 6px rgba(0, 0, 0, 0.4);
}

.markdown-body pre code {
  background: transparent;
  border: none;
  padding: 0;
  color: var(--vm-ink-body);
}

.markdown-body table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  word-break: break-word;
  margin: 20px 0;
  background: rgba(255, 255, 255, 0.03);
  border-radius: var(--vm-radius);
  overflow: hidden;
  border: 1px solid var(--vm-border);
}

.markdown-body th, .markdown-body td {
  border: 1px solid var(--vm-border);
  padding: 10px 12px;
}

.markdown-body th {
  background: rgba(255, 255, 255, 0.06);
  color: #FFFFFF;
  font-weight: 700;
}

.markdown-body tr:hover td {
  background: rgba(255, 255, 255, 0.02);
}

.markdown-body img {
  max-width: 100%;
  height: auto;
  border-radius: var(--vm-radius);
}
"""

LAYOUT_CSS = """
html {
  scroll-behavior: smooth;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background-color: var(--vm-bg-night);
  background-image:
    radial-gradient(circle 600px at 85% 15%, rgba(124, 156, 196, 0.25) 0%, transparent 65%),
    radial-gradient(circle 750px at 10% 45%, rgba(51, 81, 122, 0.32) 0%, transparent 65%),
    radial-gradient(circle 500px at 70% 85%, rgba(228, 184, 99, 0.10) 0%, transparent 60%);
  background-attachment: fixed;
  color: var(--vm-ink-body);
  font-family: var(--vm-font-sans);
  -webkit-font-smoothing: antialiased;
  min-height: 100vh;
  position: relative;
}

/* 全屏微质感噪点叠加 (2.5% SVG feTurbulence 噪点颗粒层) */
body::before {
  content: "";
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  opacity: 0.025;
  pointer-events: none;
  z-index: 9999;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
}

/* 飞书同款：全屏通透无界画板，视口动态流式比例弹性自适应 (Fluid Responsive Layout) */
.vm-layout-wrapper {
  display: flex;
  justify-content: flex-start;
  align-items: flex-start;
  gap: clamp(24px, 2.6vw, 56px);
  width: 100%;
  min-height: 100vh;
  margin: 0;
  padding: 24px clamp(20px, 2.5vw, 48px) 60px clamp(20px, 2.5vw, 48px);
  box-sizing: border-box;
  position: relative;
  z-index: 1;
}

/* 左侧目录导航栏 (TOC Sidebar - 玻璃拟态风格) */
.vm-toc-sidebar {
  width: clamp(200px, 15vw, 280px);
  flex-shrink: 0;
  position: sticky;
  top: 24px;
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  padding: 12px 6px;
  background: rgba(255, 255, 255, 0.03);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid var(--vm-border);
  border-radius: var(--vm-radius-lg);
  box-shadow: 0 16px 40px rgba(3, 7, 18, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.18), inset 0 -1px 0 rgba(2, 6, 16, 0.3);
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}

.vm-toc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
  color: #FFFFFF;
  padding: 4px 8px 10px 8px;
  margin-bottom: 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  letter-spacing: 0.02em;
}

.vm-toc-icon {
  color: var(--vm-accent-gold);
  flex-shrink: 0;
}

.vm-toc-nav {
  width: 100%;
}

.vm-toc-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.vm-toc-item {
  margin: 0;
  padding: 0;
}

.vm-toc-level-3 {
  padding-left: 14px;
}

.vm-toc-link {
  display: block;
  padding: 6px 10px;
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--vm-ink-muted);
  text-decoration: none;
  border-radius: 8px;
  border: 1px solid transparent;
  transition: all 0.3s var(--vm-spring-easing);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.vm-toc-level-3 .vm-toc-link {
  font-size: 12px;
  color: var(--vm-ink-subtle);
}

.vm-toc-link:hover {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.15);
  color: #FFFFFF;
  transform: translateX(2px);
}

.vm-toc-link.active {
  background: var(--vm-accent-gold-bg);
  border-color: var(--vm-accent-gold-border);
  color: var(--vm-accent-gold-light);
  font-weight: 600;
  box-shadow: 0 4px 16px rgba(228, 184, 99, 0.15), inset 0 1px 0 rgba(243, 220, 168, 0.3);
}

/* 右侧主文档画布：无边框自然融入夜航背景 */
.vm-doc {
  flex: 0 1 clamp(780px, 56vw, 1080px);
  width: 100%;
  max-width: clamp(780px, 56vw, 1080px);
  min-width: 0;
  margin: 0;
  padding: 0 12px 48px 12px;
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
  box-sizing: border-box;
}

.vm-overview-heading {
  font-size: 1.25rem;
  font-weight: 700;
  color: #FFFFFF;
  margin: 0 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--vm-border);
  letter-spacing: -0.015em;
  scroll-margin-top: 24px;
}

.vm-overview-content {
  margin-bottom: 36px;
}

.vm-doc-footer {
  margin-top: 56px;
  padding-top: 22px;
  border-top: 1px solid var(--vm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 12px;
  color: var(--vm-ink-subtle);
  user-select: none;
}

.vm-footer-icon {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
  vertical-align: middle;
}

.vm-footer-text {
  line-height: 1.4;
}

.vm-section {
  margin: 0;
}

@media (max-width: 1024px) {
  .vm-layout-wrapper {
    flex-direction: column;
    align-items: stretch;
    padding: 12px 16px;
    margin: 0;
    gap: 16px;
  }
  .vm-toc-sidebar {
    position: static;
    width: 100%;
    max-height: none;
    border-radius: var(--vm-radius-lg);
  }
  .vm-doc {
    max-width: 100%;
    padding: 12px 0 24px 0;
  }
}
"""


class DocumentCompositor:
    def __init__(self) -> None:
        self.md = MarkdownIt("commonmark").enable("table").enable("strikethrough")

    def _render_section_with_visual(
        self,
        section: SectionNode,
        visual_html: str,
        heading_counter: list[int],
        toc_items: list[dict],
    ) -> str:
        tokens = self.md.parse(section.markdown)
        first_heading_seen = False

        for i, token in enumerate(tokens):
            if token.type == "heading_open":
                lvl = int(token.tag[1])
                # 为所有二级和三级标题赋予唯一锚点 ID，并搜集到 TOC 树中
                if 2 <= lvl <= 3:
                    heading_counter[0] += 1
                    hid = f"heading-{heading_counter[0]}"
                    token.attrSet("id", hid)
                    title = ""
                    if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                        title = tokens[i + 1].content.strip()
                    if title:
                        toc_items.append({"id": hid, "level": lvl, "title": title})
                elif not first_heading_seen:
                    token.attrSet("id", section.section_id)
                first_heading_seen = True

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
        section_summary_markdown: Optional[str] = None,
    ) -> str:
        if isinstance(parsed, str):
            parsed = parse_minutes(parsed)

        by_section: Dict[str, SectionVisual] = {
            item.section_id: item for item in ir.sections if item.visual is not None
        }

        # 目录项列表，第一项固定为“## 总览”
        toc_items: list[dict] = [{"id": "sec-overview", "level": 2, "title": "总览"}]
        heading_counter = [0]

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
            section_html = self._render_section_with_visual(
                section, visual_html, heading_counter, toc_items
            )
            parts.append(
                f'<section class="vm-section" data-section-id="{section.section_id}">'
                f"{section_html}</section>"
            )

        # 智能章节（段落速览）：严格在所有业务章节与图表之后、HTML渲染最末尾挂载，并动态生成TOC目录项
        sec_summary = (section_summary_markdown or "").strip()
        already_has_summary = any("智能章节" in s.heading for s in parsed.sections)
        if sec_summary and not already_has_summary:
            heading_counter[0] += 1
            hid = f"heading-{heading_counter[0]}"
            sec_id = "sec-section-summary"
            toc_items.append({"id": hid, "level": 2, "title": "智能章节"})

            rendered_summary = self.md.render(sec_summary)
            sec_html = f'<h2 id="{hid}">智能章节</h2>\n{rendered_summary}'
            parts.append(
                f'<section class="vm-section" data-section-id="{sec_id}">'
                f"{sec_html}</section>"
            )

        body = "".join(parts)
        master_html = render_master(ir.master)

        # 构建飞书同款左侧导航目录列表 HTML
        toc_li_list = []
        for item in toc_items:
            lvl_cls = f"vm-toc-level-{item['level']}"
            t_title = escape(item["title"])
            t_id = item["id"]
            toc_li_list.append(
                f'<li class="vm-toc-item {lvl_cls}">'
                f'  <a href="#{t_id}" class="vm-toc-link" data-target="{t_id}" title="{t_title}">'
                f'    <span class="vm-toc-text">{t_title}</span>'
                f'  </a>'
                f'</li>'
            )
        toc_list_html = "".join(toc_li_list)

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(parsed.document_title or "图文纪要")}</title>
<style>
{TASTE_CSS}
{MARKDOWN_BODY_CSS}
{LAYOUT_CSS}
</style>
</head>
<body>
<div class="vm-layout-wrapper">
  <!-- 飞书同款左侧目录导航栏 -->
  <aside class="vm-toc-sidebar" id="vm-toc-sidebar">
    <div class="vm-toc-header">
      <svg class="vm-toc-icon" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="8" y1="6" x2="21" y2="6"></line>
        <line x1="8" y1="12" x2="21" y2="12"></line>
        <line x1="8" y1="18" x2="21" y2="18"></line>
        <line x1="3" y1="6" x2="3.01" y2="6"></line>
        <line x1="3" y1="12" x2="3.01" y2="12"></line>
        <line x1="3" y1="18" x2="3.01" y2="18"></line>
      </svg>
      <span>目录导航</span>
    </div>
    <nav class="vm-toc-nav">
      <ul class="vm-toc-list">
        {toc_list_html}
      </ul>
    </nav>
  </aside>

  <!-- 右侧主文档画布 -->
  <div class="vm-doc">
    <main class="markdown-body">
      <!-- 第一张大图外层套上 ## 总览 -->
      <section class="vm-section vm-section-overview" data-section-id="sec-overview">
        <h2 id="sec-overview" class="vm-overview-heading">总览</h2>
        <div class="vm-overview-content">
          {master_html}
        </div>
      </section>
      {body}
    </main>
    <footer class="vm-doc-footer">
      <img class="vm-footer-icon" src="{XIAOYI_ICON_DATA_URI}" alt="小艺慧记" />
      <span class="vm-footer-text">小艺慧记：内容由AI生成，仅供参考。</span>
    </footer>
  </div>
</div>

<script>
document.addEventListener("DOMContentLoaded", function () {{
  const links = document.querySelectorAll(".vm-toc-link");
  const targets = [];
  links.forEach(link => {{
    const id = link.getAttribute("data-target");
    const el = document.getElementById(id);
    if (el) targets.push({{ id, el, link }});
  }});

  function onScroll() {{
    let current = targets[0];
    const scrollY = window.scrollY + 100;
    for (let i = 0; i < targets.length; i++) {{
      if (targets[i].el.getBoundingClientRect().top + window.scrollY <= scrollY) {{
        current = targets[i];
      }}
    }}
    links.forEach(l => l.classList.remove("active"));
    if (current && current.link) {{
      current.link.classList.add("active");
    }}
  }}

  window.addEventListener("scroll", onScroll, {{ passive: true }});
  onScroll();
}});
</script>
</body>
</html>"""
        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(html, encoding="utf-8")
        return html


__all__ = ["DocumentCompositor"]
