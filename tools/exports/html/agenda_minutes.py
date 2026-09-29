"""agenda_minutes.py -- 议程驱动型会议纪要的双模态导出（Markdown 与 LaTeX Paper 风格 HTML）。

包含：
1. format_agenda_minutes_markdown：结构化 draft 确定性渲染为 Markdown (result.md)；
2. render_agenda_minutes_html：渲染为高规格政企/学术 LaTeX Paper 风格 HTML 页面 (agenda_minutes.html)。
"""
from __future__ import annotations

from html import escape
import re
from typing import Any

from tools.exports.html.paper_css import latex_paper_css as _latex_paper_css


def _safe_str(val: Any) -> str:
    if val is None or val is False:
        return ""
    return str(val).strip()


def _md_inline(text: str) -> str:
    """行内简易 Markdown 转 HTML。"""
    if not text:
        return ""
    escaped = escape(text, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped


def format_agenda_minutes_markdown(draft: dict[str, Any], title: str = "") -> str:
    """把结构化草稿排版为标准 Markdown 纪要（result.md）。"""
    meta = draft.get("meeting_meta") or {}
    items = draft.get("agenda_items") or []

    theme = meta.get("theme") or title or "会议审议与技术研讨"
    date_time = meta.get("date_time") or "2026年度会议"
    attendees = meta.get("attendees_summary") or "全体与会人"
    stats = meta.get("agenda_stats") or f"既定议题共 {len(items)} 项"

    lines = [
        f"# {theme} · 议程全景纪要",
        "",
        f"> **会议时间**：{date_time}  ",
        f"> **与会人员**：{attendees}  ",
        f"> **议程进展总览**：{stats}",
        "",
        "---",
        "",
        "## 议题总览",
        "",
        "| 议题名称 | 汇报人 | 结论/定调状态 | 核心结论与后续安排 |",
        "| :--- | :---: | :---: | :--- |",
    ]

    for it in items:
        it_title = it.get("agenda_title") or "议题"
        pres = it.get("presenter") or "未记录"
        state = it.get("discussion_state") or "discussed"
        status = it.get("status_tag") or ("[本次未讨论]" if state == "skipped" else "[审议通过]")
        res = it.get("conclusion_and_status") or it.get("resolution") or ""
        res_summary = res.splitlines()[0] if res else ("—" if state == "skipped" else "（本次未形成明确决议）")
        if len(res_summary) > 60:
            res_summary = res_summary[:57] + "..."
        lines.append(f"| {it_title} | {pres} | `{status}` | {res_summary} |")

    lines.extend([
        "",
        "---",
        "",
        "## 议题分析",
        "",
    ])

    for it in items:
        seq = it.get("agenda_seq") or "01"
        it_title = it.get("agenda_title") or "议题"
        pres = it.get("presenter") or "未记录"
        state = it.get("discussion_state") or "discussed"
        status = it.get("status_tag") or ("[本次未讨论]" if state == "skipped" else "[审议通过]")

        lines.extend([
            f"### 议题 {seq} · {it_title}",
            "",
            f"- **汇报人/责任单位**：{pres}",
            f"- **结论定调**：`{status}`",
            "",
        ])

        if state == "skipped" or "[本次未讨论]" in status:
            lines.extend([
                "> （本次会议录音转写未见本议题汇报或讨论记录）",
                "",
            ])
            continue

        # 1. 目标与对象
        target = it.get("target_and_audience") or it.get("proposal_highlights") or []
        lines.append("#### 1. 目标与对象")
        if target:
            for p in target:
                lines.append(f"- {p}")
        else:
            lines.append("- 按既定方案申报，明确核心诉求与预期目标。")
        lines.append("")

        # 2. 内容与依据
        content_raw = it.get("content_and_evidence")
        if isinstance(content_raw, list):
            content_list = list(content_raw)
        elif isinstance(content_raw, dict):
            content_list = list(content_raw.get("key_metrics") or []) + list(content_raw.get("facts_and_options") or [])
        else:
            delib = it.get("deliberation_details") or {}
            content_list = list(delib.get("key_metrics") or []) if isinstance(delib, dict) else []

        lines.append("#### 2. 内容与依据")
        if content_list:
            for m in content_list:
                lines.append(f"- {m}")
        else:
            lines.append("- 依据现场方案申报材料与基线指标开展审议。")
        lines.append("")

        # 3. 过程与互动
        process_raw = it.get("process_and_interaction")
        if isinstance(process_raw, list):
            process_list = list(process_raw)
        elif isinstance(process_raw, dict):
            process_list = list(process_raw.get("feedback_concerns") or []) + list(process_raw.get("focus_debates") or [])
        else:
            delib = it.get("deliberation_details") or {}
            process_list = list(delib.get("feedback_concerns") or []) if isinstance(delib, dict) else []

        lines.append("#### 3. 过程与互动")
        if process_list:
            for c in process_list:
                lines.append(f"- {c}")
        else:
            lines.append("- 现场就方案细节与落地风险展开了充分质询与沟通。")
        lines.append("")

        # 4. 结论与状态
        conclusion = str(it.get("conclusion_and_status") or it.get("resolution") or "").strip()
        lines.append("#### 4. 结论与状态")
        if conclusion:
            lines.extend([f"> {conclusion}", ""])
        else:
            lines.extend(["> （本次会议未记录到明确决议）", ""])

        # 5. 行动与效果
        actions = it.get("action_items") or it.get("action_commitments") or []
        lines.append("#### 5. 行动与效果")
        if actions:
            lines.extend([
                "| 责任人 | 跟进事项与交付目标 | 时限节点 |",
                "| :--- | :--- | :--- |",
            ])
            for act in actions:
                owner = act.get("owner") or "待定"
                task = act.get("task") or "后续跟进"
                deadline = act.get("deadline") or "近期"
                lines.append(f"| {owner} | {task} | {deadline} |")
        else:
            lines.append("- 暂无额外待办，由主讲团队按常规流程推进。")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _status_class(status: str) -> tuple[str, str]:
    """返回 (badge_class, display_text)。"""
    s = status.strip()
    if "[本次未讨论]" in s or "未讨论" in s:
        return "badge-skipped", s
    if "附条件" in s or "条件通过" in s:
        return "badge-conditional", s
    if "通过" in s:
        return "badge-approved", s
    if "共识" in s or "认可" in s or "建议" in s:
        return "badge-consensus", s
    return "badge-default", s


def render_agenda_minutes_html(
    title: str,
    text: str,
    data: dict[str, Any] | None = None,
) -> str:
    """渲染遵循 LaTeX Paper / 企业标准报告风格的 HTML 纪要页面。"""
    draft = data or {}
    meta = draft.get("meeting_meta") or {}
    items = draft.get("agenda_items") or []

    theme = meta.get("theme") or title or "议程全景纪要"
    date_time = meta.get("date_time") or "2026年度会议"
    attendees = meta.get("attendees_summary") or "全体参会人"
    stats = meta.get("agenda_stats") or f"共 {len(items)} 项议题"

    total_cnt = len(items)
    discussed_cnt = sum(
        1 for it in items
        if it.get("discussion_state") != "skipped" and "[本次未讨论]" not in str(it.get("status_tag") or "")
    )
    skipped_cnt = total_cnt - discussed_cnt

    # 构建议题总览表格行（已移除序号列）
    table_rows = []
    for it in items:
        seq = _safe_str(it.get("agenda_seq") or "01")
        it_title = _safe_str(it.get("agenda_title") or "议题")
        pres = _safe_str(it.get("presenter") or "未记录")
        status = _safe_str(it.get("status_tag") or "[审议通过]")
        res = _safe_str(it.get("conclusion_and_status") or it.get("resolution") or "")
        badge_cls, badge_text = _status_class(status)

        table_rows.append(f"""
        <tr>
            <td class="col-title"><a href="#topic-{seq}">{escape(it_title)}</a></td>
            <td class="col-pres">{escape(pres)}</td>
            <td class="col-status"><span class="badge {badge_cls}">{escape(badge_text)}</span></td>
            <td class="col-res">{_md_inline(res[:80])}</td>
        </tr>
        """)

    # 构建议题卡片
    cards = []
    for it in items:
        seq = _safe_str(it.get("agenda_seq") or "01")
        it_title = _safe_str(it.get("agenda_title") or "议题")
        pres = _safe_str(it.get("presenter") or "未记录")
        status = _safe_str(it.get("status_tag") or "[审议通过]")
        state = _safe_str(it.get("discussion_state") or "discussed")
        badge_cls, badge_text = _status_class(status)

        if state == "skipped" or "[本次未讨论]" in status:
            card_html = f"""
            <div class="agenda-card card-skipped" id="topic-{seq}">
                <div class="card-header">
                    <div class="card-title-group">
                        <span class="topic-index">议题 {seq}</span>
                        <h3 class="topic-name">{escape(it_title)}</h3>
                    </div>
                    <span class="badge {badge_cls}">{escape(badge_text)}</span>
                </div>
                <div class="card-skipped-body">
                    <span class="card-meta">汇报人/责任单位：{escape(pres)}</span>
                    <span class="skipped-banner">（本次会议录音转写未见本议题汇报或讨论记录）</span>
                </div>
            </div>
            """
            cards.append(card_html)
            continue

        # 1. 目标与对象
        target = it.get("target_and_audience") or it.get("proposal_highlights") or []
        target_li = "".join(f"<li>{_md_inline(p)}</li>" for p in target) if target else "<li>按既定方案申报，明确核心诉求与预期目标。</li>"

        # 2. 内容与依据
        content_raw = it.get("content_and_evidence")
        if isinstance(content_raw, list):
            content_list = list(content_raw)
        elif isinstance(content_raw, dict):
            content_list = list(content_raw.get("key_metrics") or []) + list(content_raw.get("facts_and_options") or [])
        else:
            delib = it.get("deliberation_details") or {}
            content_list = list(delib.get("key_metrics") or []) if isinstance(delib, dict) else []

        content_li = "".join(f"<li>{_md_inline(m)}</li>" for m in content_list) if content_list else "<li>依据现场方案申报材料与基线指标开展审议。</li>"

        # 3. 过程与互动
        process_raw = it.get("process_and_interaction")
        if isinstance(process_raw, list):
            process_list = list(process_raw)
        elif isinstance(process_raw, dict):
            process_list = list(process_raw.get("feedback_concerns") or []) + list(process_raw.get("focus_debates") or [])
        else:
            delib = it.get("deliberation_details") or {}
            process_list = list(delib.get("feedback_concerns") or []) if isinstance(delib, dict) else []

        process_li = "".join(f"<li>{_md_inline(c)}</li>" for c in process_list) if process_list else "<li>现场就方案细节与落地风险展开了充分质询与沟通。</li>"

        # 4. 结论与状态
        conclusion = _safe_str(it.get("conclusion_and_status") or it.get("resolution") or "")
        conclusion_content = _md_inline(conclusion) if conclusion else "（本次会议未形成明确决议）"

        # 5. 行动与效果
        actions = it.get("action_items") or it.get("action_commitments") or []
        if actions:
            act_rows = []
            for a in actions:
                owner = _safe_str(a.get("owner") or "待定")
                task = _safe_str(a.get("task") or "后续推进")
                deadline = _safe_str(a.get("deadline") or "近期")
                act_rows.append(f"""
                <tr>
                    <td><strong>{escape(owner)}</strong></td>
                    <td>{_md_inline(task)}</td>
                    <td><span class="deadline-tag">{escape(deadline)}</span></td>
                </tr>
                """)
            action_table = f"""
            <div class="action-table-wrap">
                <table class="action-table">
                    <thead>
                        <tr><th>责任人</th><th>跟进事项与交付目标</th><th>时限节点</th></tr>
                    </thead>
                    <tbody>{''.join(act_rows)}</tbody>
                </table>
            </div>
            """
        else:
            action_table = "<p class='no-action'>暂无额外待办，由主讲团队按常规流程推进。</p>"

        card_html = f"""
        <div class="agenda-card" id="topic-{seq}">
            <div class="card-header">
                <div class="card-title-group">
                    <span class="topic-index">议题 {seq}</span>
                    <h3 class="topic-name">{escape(it_title)}</h3>
                </div>
                <span class="badge {badge_cls}">{escape(badge_text)}</span>
            </div>
            <div class="card-meta">
                <span>汇报人/责任单位：{escape(pres)}</span>
            </div>

            <div class="pillar-section">
                <div class="pillar-label"><span class="pillar-num">1</span> 目标与对象</div>
                <ul class="bullet-list">{target_li}</ul>
            </div>

            <div class="pillar-section">
                <div class="pillar-label"><span class="pillar-num">2</span> 内容与依据</div>
                <ul class="bullet-list">{content_li}</ul>
            </div>

            <div class="pillar-section">
                <div class="pillar-label"><span class="pillar-num">3</span> 过程与互动</div>
                <ul class="bullet-list">{process_li}</ul>
            </div>

            <div class="pillar-section">
                <div class="pillar-label"><span class="pillar-num">4</span> 结论与状态</div>
                <div class="resolution-box">
                    <div class="resolution-text">{conclusion_content}</div>
                </div>
            </div>

            <div class="pillar-section">
                <div class="pillar-label"><span class="pillar-num">5</span> 行动与效果</div>
                {action_table}
            </div>
        </div>
        """
        cards.append(card_html)

    attendees_brief = attendees[:80] + ("..." if len(attendees) > 80 else "")

    custom_css = """
    .ck-doc-meta {
      font-style: normal;
      color: #555555;
      font-size: 0.8rem;
    }
    .ck-doc blockquote, .ck-quote {
      font-style: normal;
    }
    .summary-table {
      margin: 10px 0 24px;
    }
    .summary-table th {
      font-size: 0.82rem;
      white-space: nowrap;
    }
    .summary-table td {
      font-size: 0.82rem;
    }
    .col-title a {
      color: #111111;
      text-decoration: underline;
      text-underline-offset: 3px;
      text-decoration-color: #888888;
      font-weight: 600;
    }
    .col-title a:hover {
      color: #000000;
      text-decoration-color: #111111;
    }
    .col-pres {
      width: 130px;
      white-space: nowrap;
    }
    .col-status {
      width: 120px;
      white-space: nowrap;
    }
    .col-res {
      color: #333333;
    }

    .badge {
      display: inline-block;
      padding: 2px 7px;
      border-radius: 3px;
      font-size: 0.76rem;
      font-weight: 600;
      line-height: 1.35;
      letter-spacing: 0.02em;
      white-space: nowrap;
    }
    .badge-approved {
      background: #edf7ed;
      color: #1e4620;
      border: 1px solid #c8e6c9;
    }
    .badge-conditional {
      background: #fff8e1;
      color: #825300;
      border: 1px solid #ffe082;
    }
    .badge-consensus {
      background: #e8f4fd;
      color: #0d47a1;
      border: 1px solid #bbdefb;
    }
    .badge-skipped {
      background: #f5f5f5;
      color: #616161;
      border: 1px solid #e0e0e0;
    }
    .badge-default {
      background: #f5f5f5;
      color: #333333;
      border: 1px solid #d4d0c7;
    }

    .agenda-cards-wrap {
      margin-top: 12px;
    }
    .agenda-card {
      background: #ffffff;
      border: 1px solid #d4d0c7;
      border-radius: 4px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
      padding: 16px 20px;
      margin-bottom: 20px;
    }
    .card-skipped {
      background: #faf9f6;
      border-style: dashed;
      border-color: #c4bfb6;
      padding: 8px 14px;
      margin-bottom: 10px;
    }
    .card-skipped .card-header {
      margin-bottom: 4px;
      padding-bottom: 4px;
      border-bottom: 1px dashed #ede9e1;
    }
    .card-skipped-body {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
    }
    .card-skipped .card-meta {
      font-size: 0.78rem;
      color: #666666;
      margin-bottom: 0;
      font-style: normal;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 8px;
      padding-bottom: 8px;
      border-bottom: 1px solid #ede9e1;
      gap: 12px;
    }
    .card-title-group {
      display: flex;
      align-items: baseline;
      gap: 8px;
    }
    .topic-index {
      font-size: 0.8rem;
      font-weight: 700;
      color: #222222;
      background: #f0ece1;
      padding: 1px 6px;
      border-radius: 2px;
      white-space: nowrap;
    }
    .topic-name {
      font-size: 0.95rem;
      font-weight: 700;
      margin: 0;
      color: #111111;
    }
    .card-meta {
      font-size: 0.8rem;
      color: #555555;
      margin-bottom: 12px;
      font-style: normal;
    }

    .pillar-section {
      margin-bottom: 14px;
    }
    .pillar-label {
      font-size: var(--ck-fs);
      font-weight: 700;
      color: #111111;
      margin-bottom: 6px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .pillar-num {
      background: #ede9e1;
      color: #333333;
      font-size: 0.72rem;
      width: 17px;
      height: 17px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 50%;
      font-weight: 700;
    }
    .bullet-list {
      margin: 3px 0 6px;
      padding-left: 1.4em;
      font-size: var(--ck-fs);
      color: #222222;
      line-height: 1.6;
    }
    .bullet-list li {
      margin: 2px 0;
    }

    .sub-block {
      background: #fbfaf7;
      border-radius: 3px;
      padding: 8px 12px;
      margin-bottom: 8px;
      border: 1px solid #ece8df;
    }
    .sub-block-title {
      font-size: 0.8rem;
      font-weight: 700;
      color: #333333;
      margin-bottom: 4px;
    }

    .resolution-box {
      background: #f7faf7;
      border: 1px solid #d4e6d4;
      border-left: 3px solid #2e7d32;
      border-radius: 3px;
      padding: 8px 12px;
      font-size: var(--ck-fs);
      color: #1b4d1d;
      line-height: 1.6;
    }

    .skipped-banner {
      background: #f2efe8;
      border-radius: 2px;
      padding: 2px 8px;
      font-size: 0.78rem;
      color: #666666;
      font-style: normal;
      line-height: 1.4;
      display: inline-block;
      margin: 0;
    }

    .action-table-wrap {
      overflow-x: auto;
      margin-top: 4px;
    }
    .action-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
      border-top: 1.5px solid #222222;
      border-bottom: 1.5px solid #222222;
    }
    .action-table th {
      background: #fbfaf7;
      padding: 6px 10px;
      color: #111111;
      font-weight: 700;
      border-bottom: 1px solid #222222;
      text-align: left;
    }
    .action-table td {
      padding: 6px 10px;
      border-bottom: 1px solid #ede9e1;
      vertical-align: middle;
      color: #222222;
    }
    .deadline-tag {
      background: #f0ece1;
      padding: 1px 6px;
      border-radius: 2px;
      font-size: 0.76rem;
      color: #444444;
      white-space: nowrap;
    }
    .no-action {
      font-size: 0.82rem;
      color: #666666;
      font-style: normal;
      margin: 4px 0 0 0;
    }
    """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(theme)} · 议程全景纪要</title>
    <style>
{_latex_paper_css()}
{custom_css}
    </style>
</head>
<body>
    <main class="page">
        <div class="ck-doc">
            <header class="ck-doc-header">
                <h1>{escape(theme)} · 议程全景纪要</h1>
                <div class="ck-doc-meta">
                    <span>会议时间：{escape(date_time)}</span> &nbsp;|&nbsp;
                    <span>议程进展：共 {total_cnt} 项（有效审议 {discussed_cnt} 项，本次未讨论 {skipped_cnt} 项）</span> &nbsp;|&nbsp;
                    <span>与会人员：{escape(attendees_brief)}</span>
                </div>
            </header>

            <div class="ck-doc-content">
                <h2 class="ck-doc-h2" style="margin-top: 20px;">议题总览</h2>
                <table class="ck-table summary-table">
                    <thead>
                        <tr>
                            <th class="col-title">议题名称</th>
                            <th class="col-pres">汇报人/单位</th>
                            <th class="col-status">结论定调</th>
                            <th class="col-res">核心结论与后续安排</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(table_rows)}
                    </tbody>
                </table>

                <h2 class="ck-doc-h2" style="margin-top: 28px;">议题分析</h2>
                <div class="agenda-cards-wrap">
                    {''.join(cards)}
                </div>
            </div>
        </div>
    </main>
</body>
</html>
"""
    return html
