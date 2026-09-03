"""minutes_trace 溯源纪要的 LaTeX Paper 风格 HTML 审阅栏渲染。

左侧：纪要正文排版（紧凑宽行），命中溯源材料的语句高亮并在句末附加蓝色 [1], [2] 序号标签。
右侧：命中的 keypoints 和 notes 证据卡片，与左侧首次出现的行水平对齐（Sidenote 布局）。
      - 随文批注（notes）：含用户批注，徽标为「随文批注」（赭石徽章）
      - 要点归纳（keypoints）：提炼核心重点，徽标为「要点归纳」（蓝色徽章）
      - 重复命中的材料复用相同序号，右侧对应同一张卡片。
交互：点击左侧语句或蓝色序号点亮右侧卡片并带光晕脉冲动画；点击右侧卡片点亮左侧对应语句。
"""
from __future__ import annotations

import re
from html import escape
from typing import Any

from tools.meeting_memory.render import _latex_paper_css

_PIN_RE = re.compile(r"###\[【([^】]+)】\](?:\([^)]*\))?")
_NOTE_SEP = " **用户批注** "

_TRACE_SCRIPT = """<script>
(function () {
  function alignTraceCards() {
    const isDesktop = window.innerWidth > 860;
    document.querySelectorAll('.ck-review').forEach((review) => {
      const leftEl = review.querySelector('.ck-review-left');
      const rightEl = review.querySelector('.ck-review-right');
      const listEl = review.querySelector('.ck-ev-list');
      if (!leftEl || !rightEl || !listEl) return;

      const cards = Array.from(listEl.querySelectorAll('.ck-ev'));
      if (!cards.length) return;

      if (!isDesktop) {
        cards.forEach((c) => {
          c.style.position = '';
          c.style.top = '';
          c.style.width = '';
        });
        rightEl.style.minHeight = '';
        listEl.style.minHeight = '';
        return;
      }

      // 桌面端：右侧卡片精确对齐左侧首次出现的位置，同时防重叠向下推
      cards.forEach((c) => {
        c.style.position = 'absolute';
        c.style.width = '100%';
        c.style.boxSizing = 'border-box';
      });

      const leftRect = leftEl.getBoundingClientRect();
      let lastBottom = 0;
      const gap = 10;

      cards.forEach((card) => {
        const traceId = card.getAttribute('data-trace');
        const targetEntity = leftEl.querySelector(`.ck-cite-ref[data-target-trace="${traceId}"]`)
                          || leftEl.querySelector(`.ck-cite-entity[data-trace~="${traceId}"]`);

        let targetTop = 0;
        if (targetEntity) {
          const entRect = targetEntity.getBoundingClientRect();
          targetTop = entRect.top - leftRect.top;
        } else {
          targetTop = lastBottom > 0 ? lastBottom + gap : 0;
        }

        // 避免与上一张卡片重叠
        const placedTop = Math.max(targetTop, lastBottom > 0 ? lastBottom + gap : 0);
        card.style.top = `${placedTop}px`;

        const cardHeight = card.offsetHeight || 75;
        lastBottom = placedTop + cardHeight;
      });

      const minHeight = Math.max(leftEl.offsetHeight, lastBottom + 16);
      rightEl.style.minHeight = `${minHeight}px`;
      listEl.style.minHeight = `${minHeight}px`;
    });
  }

  window.__alignTraceCards = alignTraceCards;

  document.querySelectorAll('.ck-review').forEach((row) => {
    const cites = row.querySelectorAll('.ck-cite-ref');
    const entities = row.querySelectorAll('.ck-cite-entity');
    const cards = row.querySelectorAll('.ck-ev');

    const clearHighlights = () => {
      entities.forEach((el) => el.classList.remove('is-on'));
      cards.forEach((el) => el.classList.remove('is-on', 'is-highlighted'));
      cites.forEach((c) => c.classList.remove('is-active'));
    };

    const highlightTrace = (targetTraceId) => {
      clearHighlights();
      let targetCard = null;
      row.querySelectorAll('.ck-ev').forEach((card) => {
        if (card.getAttribute('data-trace') === targetTraceId) {
          targetCard = card;
          card.classList.add('is-on', 'is-highlighted');
          card.style.animation = 'none';
          void card.offsetHeight;
          card.style.animation = 'citePulse 1.2s ease';
        }
      });
      entities.forEach((ent) => {
        const traces = (ent.getAttribute('data-trace') || '').split(' ');
        if (traces.includes(targetTraceId)) {
          ent.classList.add('is-on');
        }
      });
      cites.forEach((c) => {
        if (c.getAttribute('data-target-trace') === targetTraceId) {
          c.classList.add('is-active');
        }
      });
      if (targetCard) {
        targetCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    };

    cites.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const targetId = btn.getAttribute('data-target-trace');
        if (targetId) highlightTrace(targetId);
      });
    });

    entities.forEach((ent) => {
      ent.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const traces = (ent.getAttribute('data-trace') || '').split(' ');
        if (traces.length > 0 && traces[0]) highlightTrace(traces[0]);
      });
    });

    row.addEventListener('click', (e) => {
      const card = e.target.closest('.ck-ev');
      if (card) {
        const traceId = card.getAttribute('data-trace');
        if (traceId) highlightTrace(traceId);
      }
    });
  });

  alignTraceCards();
  window.addEventListener('load', alignTraceCards);
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(alignTraceCards, 80);
  });
})();
</script>"""


def _parse_source_key(raw: str) -> tuple[str, str, str, str]:
    """解析溯源钉内容：返回 (kind, kind_cn, left_text, right_text)。
    
    - 随文批注（notes）：含用户批注（" **用户批注** " 或 " -> "）。
    - 要点归纳（keypoints）：提炼核心要点。
    """
    raw_s = raw.strip()
    if _NOTE_SEP in raw_s:
        left, right = raw_s.split(_NOTE_SEP, 1)
        return "note", "随文批注", left.strip(), right.strip()
    if " -> " in raw_s:
        left, right = raw_s.split(" -> ", 1)
        return "note", "随文批注", left.strip(), right.strip()
    return "keypoint", "要点归纳", raw_s, ""


def _format_trace_minutes_html(
    markdown: str,
    source_map: dict[tuple[str, str, str], dict[str, Any]],
) -> tuple[str, str]:
    """格式化左侧纪要正文：紧凑学术排版，命中溯源材料的句子高亮并在句末附加 [1], [2] 标签。"""
    lines = markdown.splitlines()
    meeting_title = "会议纪要"
    if lines and lines[0].startswith("# "):
        meeting_title = lines[0][2:].strip()
        lines = lines[1:]

    out: list[str] = []
    list_buf: list[str] = []
    ol_buf: list[str] = []

    def flush_list() -> None:
        if list_buf:
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in list_buf) + "</ul>")
            list_buf.clear()
        if ol_buf:
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in ol_buf) + "</ol>")
            ol_buf.clear()

    def process_line_pins(line_str: str) -> str:
        """处理行内的溯源钉，转换为高亮实体与蓝色引用标签。"""
        if "###[【" not in line_str:
            return inline_markdown(line_str)

        parts: list[str] = []
        pos = 0

        matches = list(_PIN_RE.finditer(line_str))
        if not matches:
            return inline_markdown(line_str)

        i_m = 0
        while i_m < len(matches):
            group_matches = [matches[i_m]]
            while (
                i_m + 1 < len(matches)
                and matches[i_m + 1].start() == group_matches[-1].end()
            ):
                i_m += 1
                group_matches.append(matches[i_m])

            first_m = group_matches[0]
            last_m = group_matches[-1]

            prev_text = line_str[pos : first_m.start()]

            sids: list[str] = []
            badges: list[str] = []
            first_num = 1
            for gm in group_matches:
                raw_source = gm.group(1).strip()
                kind, kind_cn, left_t, right_t = _parse_source_key(raw_source)
                key = (kind, left_t, right_t)
                info = source_map.get(key)
                if info:
                    sid = info["sid"]
                    num = info["num"]
                    if not sids:
                        first_num = num
                    if sid not in sids:
                        sids.append(sid)
                    badges.append(
                        f'<a href="javascript:void(0)" class="ck-cite-ref" data-target-trace="{escape(sid, quote=True)}" title="点击查看{escape(info["kind_cn"], quote=True)} [{num}]">[{num}]</a>'
                    )

            if sids and prev_text:
                prefix_match = re.match(r"^(\s*[-*•\d\.\s]+)(.*)$", prev_text)
                if prefix_match:
                    p_prefix = prefix_match.group(1)
                    p_content = prefix_match.group(2)
                    parts.append(inline_markdown(p_prefix))
                    parts.append(
                        f'<span class="ck-cite-entity" data-trace="{" ".join(sids)}" data-cite="{first_num}">{inline_markdown(p_content)}</span>'
                    )
                else:
                    parts.append(
                        f'<span class="ck-cite-entity" data-trace="{" ".join(sids)}" data-cite="{first_num}">{inline_markdown(prev_text)}</span>'
                    )
                parts.append("".join(badges))
            else:
                parts.append(inline_markdown(prev_text))
                parts.append("".join(badges))

            pos = last_m.end()
            i_m += 1

        parts.append(inline_markdown(line_str[pos:]))
        return "".join(parts)

    def inline_markdown(s: str) -> str:
        esc = escape(s, quote=False)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        esc = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", esc)
        esc = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)
        return esc

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        stripped = raw_line.strip()
        if not stripped:
            flush_list()
            i += 1
            continue

        if stripped.startswith("### "):
            flush_list()
            out.append(f'<h3 class="ck-doc-h3">{process_line_pins(stripped[4:])}</h3>')
            i += 1
            continue
        if stripped.startswith("## "):
            flush_list()
            out.append(f'<h2 class="ck-doc-h2">{process_line_pins(stripped[3:])}</h2>')
            i += 1
            continue
        if stripped.startswith("# "):
            flush_list()
            out.append(f'<h2>{process_line_pins(stripped[2:])}</h2>')
            i += 1
            continue

        if re.match(r"^\s*[-*]\s+", raw_line):
            if ol_buf:
                flush_list()
            list_buf.append(process_line_pins(re.sub(r"^\s*[-*]\s+", "", raw_line)))
            i += 1
            continue

        if re.match(r"^\s*\d+[.)、]\s+", raw_line):
            if list_buf:
                flush_list()
            ol_buf.append(process_line_pins(re.sub(r"^\s*\d+[.)、]\s+", "", raw_line)))
            i += 1
            continue

        if stripped.startswith(">"):
            flush_list()
            out.append(f'<div class="ck-quote">{process_line_pins(stripped.lstrip("> "))}</div>')
            i += 1
            continue

        flush_list()
        out.append(f'<p>{process_line_pins(stripped)}</p>')
        i += 1

    flush_list()
    return meeting_title, "".join(out)


def trace_review_html(markdown: str, title: str = "") -> str:
    """把带溯源钉的 minutes_trace 渲染为与 checklist / minutes 一致的 LaTeX Paper 风格 HTML。

    左侧：纪要正文排版（宽行紧凑），命中溯源材料的句子高亮并在后面附加蓝色 [1], [2] 序号标签。
    右侧：命中的 keypoints 和 notes 证据卡片，与左侧首次出现的句子水平对齐。
          重复命中的材料复用相同的编号与卡片。
          - 随文批注（notes）：含用户批注，徽标为「随文批注」（赭石徽章）
          - 要点归纳（keypoints）：提炼核心重点，徽标为「要点归纳」（蓝色徽章）
    交互：点击左侧实体或蓝色序号点亮对应右侧卡片并带光晕脉冲动画；点击右侧卡片点亮左侧对应语句。
    """
    text = markdown or ""
    if "###[【" not in text:
        return ""

    # 第一遍扫描：收集按首次出现顺序排序的唯一材料条目，去重并分配全局连续序号 [1], [2], [3]...
    source_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    ordered_sources: list[dict[str, Any]] = []

    for m in _PIN_RE.finditer(text):
        raw = m.group(1).strip()
        kind, kind_cn, left_t, right_t = _parse_source_key(raw)
        key = (kind, left_t, right_t)
        if key not in source_map:
            num = len(ordered_sources) + 1
            sid = f"trace-{num}"
            info = {
                "sid": sid,
                "num": num,
                "kind": kind,
                "kind_cn": kind_cn,
                "left": left_t,
                "right": right_t,
            }
            source_map[key] = info
            ordered_sources.append(info)

    doc_header_title, left_html = _format_trace_minutes_html(text, source_map)
    display_title = title or doc_header_title or "会议纪要"

    # 渲染右侧证据卡片
    cards_html: list[str] = []
    for info in ordered_sources:
        num = info["num"]
        sid = info["sid"]
        kind = info["kind"]
        kind_cn = info["kind_cn"]
        left_t = info["left"]
        right_t = info["right"]

        badge_class = "ck-badge-keypoint" if kind == "keypoint" else "ck-badge-note"

        card = [
            f'<aside class="ck-ev ck-trace-card" id="card-{escape(sid, quote=True)}" data-trace="{escape(sid, quote=True)}" data-cite="{num}">',
            f'<div class="ck-ev-k"><a class="ck-ev-cite-tag" href="javascript:void(0);">[{num}]</a> <span class="ck-ev-kind-badge {badge_class}">{escape(kind_cn, quote=False)}</span></div>',
            f'<div class="ck-mem-title"><strong>{escape(left_t, quote=False)}</strong></div>',
        ]
        if right_t:
            card.append(f'<div class="ck-ev-quote"><strong>用户批注：</strong>{escape(right_t, quote=False)}</div>')
        card.append("</aside>")
        cards_html.append("".join(card))

    page_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(display_title, quote=False)}</title>
  <style>
{_latex_paper_css()}

    /* 优化画布宽度与双栏比例：每行承载更多文字，降低纵向高度 */
    .page {{
      max-width: 1260px;
      margin: 0 auto;
      padding: 24px 18px;
    }}
    .ck-doc {{
      padding: 26px 30px;
    }}
    .ck-review {{
      grid-template-columns: minmax(0, 1.48fr) 1px minmax(290px, 0.92fr);
      overflow: visible;
    }}
    .ck-review-left {{
      padding: 18px 26px;
      font-size: 0.92rem;
      line-height: 1.62;
    }}
    .ck-review-left h2, .ck-review-left .ck-doc-h2 {{
      font-size: 1.12rem;
      margin: 14px 0 6px;
      padding-bottom: 3px;
      border-bottom: 1px solid #e0dcd4;
      font-weight: 700;
    }}
    .ck-review-left h3, .ck-review-left .ck-doc-h3 {{
      font-size: 0.95rem;
      font-weight: 700;
      margin: 10px 0 4px;
      color: #222222;
    }}
    .ck-review-left p {{
      margin: 4px 0;
      line-height: 1.62;
    }}
    .ck-review-left ul, .ck-review-left ol {{
      margin: 4px 0 8px;
      padding-left: 1.25em;
    }}
    .ck-review-left li {{
      margin: 2px 0;
      line-height: 1.6;
    }}
    .ck-review-right {{
      padding: 18px 18px;
      position: relative;
    }}
    .ck-ev-list {{
      position: relative;
      width: 100%;
    }}
    .ck-ev {{
      padding: 9px 12px;
      font-size: 0.82rem;
      line-height: 1.5;
    }}
  </style>
</head>
<body>
  <main class="page">
    <div class="ck-doc">
      <header class="ck-doc-header">
        <h1>{escape(display_title, quote=False)}</h1>
      </header>
      <div class="ck-review">
        <div class="ck-review-left">
          {left_html}
        </div>
        <div class="ck-review-rule"></div>
        <div class="ck-review-right">
          <div class="ck-ev-list">
            {"".join(cards_html)}
          </div>
        </div>
      </div>
    </div>
  </main>
{_TRACE_SCRIPT}
</body>
</html>
"""
    return page_html


__all__ = ["trace_review_html"]
