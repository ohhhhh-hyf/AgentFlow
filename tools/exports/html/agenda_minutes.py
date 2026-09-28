"""agenda_minutes.py -- 议程驱动型会议纪要的双模态导出（Markdown 与现代化卡片 HTML）。

包含：
1. format_agenda_minutes_markdown：结构化 draft 确定性渲染为 Markdown (result.md)；
2. render_agenda_minutes_html：渲染为高规格政企卡片式 HTML 页面 (agenda_minutes.html)。
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
    adhoc = draft.get("adhoc_items") or []

    theme = meta.get("theme") or title or "会议审议与技术研讨"
    date_time = meta.get("date_time") or "2026年度会议"
    attendees = meta.get("attendees_summary") or "全体与会人"
    stats = meta.get("agenda_stats") or f"既定议题共 {len(items)} 项"
    overview = meta.get("overview_headline") or "全场议程推进平稳，核心技术与版本审议达成阶段共识。"

    lines = [
        f"# {theme} · 议程全景纪要",
        "",
        f"> **会议时间**：{date_time}  ",
        f"> **与会人员**：{attendees}  ",
        f"> **议程进展总览**：{stats}  ",
        f"> **总体评价**：{overview}",
        "",
        "---",
        "",
        "## 第一部分：议题完成情况一览表",
        "",
        "| 议程序号 | 议题名称 | 汇报人 | 结论/定调状态 | 核心结论与后续安排 |",
        "| :---: | :--- | :---: | :---: | :--- |",
    ]

    for it in items:
        seq = it.get("agenda_seq") or "01"
        it_title = it.get("agenda_title") or "议题"
        pres = it.get("presenter") or "未记录"
        state = it.get("discussion_state") or "discussed"
        status = it.get("status_tag") or ("[本次未讨论]" if state == "skipped" else "[审议通过]")
        res = it.get("resolution") or ""
        res_summary = res.splitlines()[0] if res else ("—" if state == "skipped" else "（本次未形成明确决议）")
        if len(res_summary) > 60:
            res_summary = res_summary[:57] + "..."
        lines.append(f"| **议题 {seq}** | {it_title} | {pres} | `{status}` | {res_summary} |")

    lines.extend([
        "",
        "---",
        "",
        "## 第二部分：既定议程逐项详实记录",
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

        props = it.get("proposal_highlights") or []
        lines.append("#### 1. 方案背景与核心诉求")
        if props:
            for p in props:
                lines.append(f"- {p}")
        else:
            lines.append("- 按既定方案申报，重点推进版本商用与技术演进。")
        lines.append("")

        delib = it.get("deliberation_details") or {}
        key_metrics = delib.get("key_metrics") or []
        concerns = delib.get("feedback_concerns") or []

        lines.append("#### 2. 研讨过程与关键论据")
        if key_metrics:
            lines.append("- **量化参数与指标**：")
            for m in key_metrics:
                lines.append(f"  - {m}")
        if concerns:
            lines.append("- **讨论交锋与各方反馈**：")
            for c in concerns:
                lines.append(f"  - {c}")
        if not key_metrics and not concerns:
            lines.append("- 现场就方案细节进行了深入评估，各项关键指标基本符合要求。")
        lines.append("")

        res = str(it.get("resolution") or "").strip()
        lines.append("#### 3. 最终定调与决议共识")
        if res:
            lines.extend([f"> {res}", ""])
        else:
            lines.extend(["> （本次会议未记录到明确决议）", ""])

        actions = it.get("action_commitments") or []
        lines.append("#### 4. 后续行动与跟进责任")
        if actions:
            lines.extend([
                "| 责任人 | 跟进事项与交付目标 | 时限节点 |",
                "| :--- | :--- | :--- |",
            ])
            for act in actions:
                owner = act.get("owner") or "待定"
                task = act.get("task") or "后续闭环"
                deadline = act.get("deadline") or "近期"
                lines.append(f"| {owner} | {task} | {deadline} |")
        else:
            lines.append("- 暂无额外待办，由主讲团队按常规流程推进。")
        lines.append("")

    if adhoc:
        lines.extend([
            "---",
            "",
            "## 第三部分：临时追加议题与重要定调",
            "",
        ])
        for a in adhoc:
            a_title = a.get("title") or "临时指示"
            spk = a.get("speaker") or "定调领导"
            content = a.get("content") or ""
            act = a.get("action") or ""
            lines.extend([
                f"### 临时议题 · {a_title}",
                "",
                f"- **定调发言人**：{spk}",
                f"- **核心指示与决议**：{content}",
                f"- **督办与跟进要求**：{act}",
                "",
            ])

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
    """渲染现代化、响应式卡片风格的 HTML 纪要页面。"""
    draft = data or {}
    meta = draft.get("meeting_meta") or {}
    items = draft.get("agenda_items") or []
    adhoc = draft.get("adhoc_items") or []

    theme = meta.get("theme") or title or "议程全景纪要"
    date_time = meta.get("date_time") or "2026年度会议"
    attendees = meta.get("attendees_summary") or "全体参会人"
    stats = meta.get("agenda_stats") or f"共 {len(items)} 项议题"
    overview = meta.get("overview_headline") or "全场议程推进平稳，核心技术与版本审议达成阶段共识。"

    total_cnt = len(items)
    discussed_cnt = sum(1 for it in items if it.get("discussion_state") != "skipped" and "[本次未讨论]" not in str(it.get("status_tag") or ""))
    skipped_cnt = total_cnt - discussed_cnt

    # 构建表格行
    table_rows = []
    for it in items:
        seq = _safe_str(it.get("agenda_seq") or "01")
        it_title = _safe_str(it.get("agenda_title") or "议题")
        pres = _safe_str(it.get("presenter") or "未记录")
        status = _safe_str(it.get("status_tag") or "[审议通过]")
        res = _safe_str(it.get("resolution") or "")
        badge_cls, badge_text = _status_class(status)

        table_rows.append(f"""
        <tr>
            <td class="col-seq"><strong>议题 {seq}</strong></td>
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
                <div class="card-meta">
                    <span><strong>汇报人/单位：</strong>{escape(pres)}</span>
                </div>
                <div class="skipped-banner">
                    <span class="icon">ℹ️</span> （本次会议录音转写未见本议题汇报或讨论记录）
                </div>
            </div>
            """
            cards.append(card_html)
            continue

        props = it.get("proposal_highlights") or []
        delib = it.get("deliberation_details") or {}
        key_metrics = delib.get("key_metrics") or []
        concerns = delib.get("feedback_concerns") or []
        res = _safe_str(it.get("resolution") or "")
        actions = it.get("action_commitments") or []

        props_li = "".join(f"<li>{_md_inline(p)}</li>" for p in props) if props else "<li>按既定方案申报，重点推进版本商用与技术演进。</li>"
        
        metrics_block = ""
        if key_metrics:
            metrics_li = "".join(f"<li>{_md_inline(m)}</li>" for m in key_metrics)
            metrics_block = f"""
            <div class="sub-block">
                <div class="sub-block-title">📊 量化参数与指标</div>
                <ul class="bullet-list">{metrics_li}</ul>
            </div>
            """

        concerns_block = ""
        if concerns:
            concerns_li = "".join(f"<li>{_md_inline(c)}</li>" for c in concerns)
            concerns_block = f"""
            <div class="sub-block">
                <div class="sub-block-title">💬 讨论交锋与各方反馈</div>
                <ul class="bullet-list">{concerns_li}</ul>
            </div>
            """

        action_table = ""
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
            action_table = "<p class='no-action'>暂无额外闭环待办，由主讲团队按常规流程推进。</p>"

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
                <span><strong>汇报人/单位：</strong>{escape(pres)}</span>
            </div>
            
            <div class="pillar-section">
                <div class="pillar-label"><span class="pillar-num">1</span> 方案背景与核心诉求</div>
                <ul class="bullet-list">{props_li}</ul>
            </div>

            <div class="pillar-section">
                <div class="pillar-label"><span class="pillar-num">2</span> 研讨过程与关键论据</div>
                {metrics_block}
                {concerns_block}
            </div>

            <div class="pillar-section">
                <div class="pillar-label"><span class="pillar-num">3</span> 最终定调与决议共识</div>
                <div class="resolution-box">
                    <span class="resolution-icon">📌</span>
                    <div class="resolution-text">{_md_inline(res)}</div>
                </div>
            </div>

            <div class="pillar-section">
                <div class="pillar-label"><span class="pillar-num">4</span> 后续行动与跟进责任</div>
                {action_table}
            </div>
        </div>
        """
        cards.append(card_html)

    # 临时追加事项
    adhoc_html = ""
    if adhoc:
        adhoc_cards = []
        for a in adhoc:
            a_t = _safe_str(a.get("title") or "临时定调")
            spk = _safe_str(a.get("speaker") or "定调领导")
            cnt = _safe_str(a.get("content") or "")
            act = _safe_str(a.get("action") or "")
            adhoc_cards.append(f"""
            <div class="adhoc-item">
                <div class="adhoc-header">
                    <h4>{escape(a_t)}</h4>
                    <span class="adhoc-speaker">定调人：<strong>{escape(spk)}</strong></span>
                </div>
                <div class="adhoc-content">{_md_inline(cnt)}</div>
                <div class="adhoc-action"><strong>督办要求：</strong>{_md_inline(act)}</div>
            </div>
            """)
        adhoc_html = f"""
        <div class="section-container adhoc-section">
            <h2 class="section-title">临时追加议题与重要定调</h2>
            <div class="adhoc-list">{''.join(adhoc_cards)}</div>
        </div>
        """

    css = f"""
    {_latex_paper_css()}
    
    :root {{
        --brand-blue: #1e40af;
        --brand-blue-bg: #eff6ff;
        --badge-green: #065f46;
        --badge-green-bg: #ecfdf5;
        --badge-amber: #92400e;
        --badge-amber-bg: #fffbeb;
        --badge-gray: #4b5563;
        --badge-gray-bg: #f3f4f6;
        --card-border: #e5e7eb;
        --card-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
    }}

    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
        background-color: #f8fafc;
        color: #1e293b;
        margin: 0;
        padding: 24px;
        line-height: 1.6;
    }}

    .agenda-container {{
        max-width: 1080px;
        margin: 0 auto;
    }}

    .hero-header {{
        background: white;
        padding: 32px;
        border-radius: 12px;
        border: 1px solid var(--card-border);
        box-shadow: var(--card-shadow);
        margin-bottom: 24px;
    }}

    .hero-title {{
        font-size: 26px;
        font-weight: 700;
        color: #0f172a;
        margin: 0 0 16px 0;
    }}

    .hero-meta-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 12px;
        font-size: 14px;
        color: #475569;
        margin-bottom: 16px;
        border-bottom: 1px solid #f1f5f9;
        padding-bottom: 16px;
    }}

    .overview-box {{
        background: #f8fafc;
        border-left: 4px solid var(--brand-blue);
        padding: 12px 16px;
        font-size: 14px;
        color: #334155;
        border-radius: 0 8px 8px 0;
    }}

    .stat-pill {{
        display: inline-block;
        background: #e2e8f0;
        padding: 2px 8px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 13px;
    }}

    .section-title {{
        font-size: 20px;
        font-weight: 700;
        color: #1e293b;
        margin: 32px 0 16px 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }}

    .summary-table-wrap {{
        background: white;
        border-radius: 12px;
        border: 1px solid var(--card-border);
        box-shadow: var(--card-shadow);
        overflow-x: auto;
        margin-bottom: 32px;
    }}

    .summary-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
        text-align: left;
    }}

    .summary-table th {{
        background: #f8fafc;
        padding: 12px 16px;
        color: #475569;
        font-weight: 600;
        border-bottom: 1px solid var(--card-border);
    }}

    .summary-table td {{
        padding: 12px 16px;
        border-bottom: 1px solid #f1f5f9;
        vertical-align: middle;
    }}

    .summary-table tr:hover {{
        background: #f8fafc;
    }}

    .col-seq {{
        width: 80px;
        white-space: nowrap;
    }}

    .col-title a {{
        color: #2563eb;
        text-decoration: none;
        font-weight: 500;
    }}

    .col-title a:hover {{
        text-decoration: underline;
    }}

    .col-pres {{
        width: 130px;
        white-space: nowrap;
    }}

    .col-status {{
        width: 110px;
        white-space: nowrap;
    }}

    .badge {{
        display: inline-block;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 0.02em;
    }}

    .badge-approved {{
        background: var(--badge-green-bg);
        color: var(--badge-green);
        border: 1px solid #a7f3d0;
    }}

    .badge-conditional {{
        background: var(--badge-amber-bg);
        color: var(--badge-amber);
        border: 1px solid #fde68a;
    }}

    .badge-consensus {{
        background: var(--brand-blue-bg);
        color: var(--brand-blue);
        border: 1px solid #bfdbfe;
    }}

    .badge-skipped {{
        background: var(--badge-gray-bg);
        color: var(--badge-gray);
        border: 1px solid #e5e7eb;
    }}

    .agenda-card {{
        background: white;
        border-radius: 12px;
        border: 1px solid var(--card-border);
        box-shadow: var(--card-shadow);
        padding: 24px;
        margin-bottom: 24px;
    }}

    .card-skipped {{
        background: #fafafa;
        border-style: dashed;
    }}

    .card-header {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 12px;
        gap: 16px;
    }}

    .card-title-group {{
        display: flex;
        align-items: baseline;
        gap: 10px;
    }}

    .topic-index {{
        font-size: 14px;
        font-weight: 700;
        color: var(--brand-blue);
        background: var(--brand-blue-bg);
        padding: 2px 8px;
        border-radius: 6px;
        white-space: nowrap;
    }}

    .topic-name {{
        font-size: 18px;
        font-weight: 700;
        margin: 0;
        color: #0f172a;
    }}

    .card-meta {{
        font-size: 14px;
        color: #64748b;
        margin-bottom: 18px;
        padding-bottom: 12px;
        border-bottom: 1px solid #f1f5f9;
    }}

    .pillar-section {{
        margin-bottom: 18px;
    }}

    .pillar-label {{
        font-size: 14px;
        font-weight: 700;
        color: #334155;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 6px;
    }}

    .pillar-num {{
        background: #e2e8f0;
        color: #475569;
        font-size: 11px;
        width: 18px;
        height: 18px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 50%;
    }}

    .bullet-list {{
        margin: 0;
        padding-left: 20px;
        font-size: 14px;
        color: #334155;
    }}

    .bullet-list li {{
        margin-bottom: 4px;
    }}

    .sub-block {{
        background: #f8fafc;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 10px;
        border: 1px solid #f1f5f9;
    }}

    .sub-block-title {{
        font-size: 13px;
        font-weight: 600;
        color: #475569;
        margin-bottom: 6px;
    }}

    .resolution-box {{
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-left: 4px solid #16a34a;
        border-radius: 6px;
        padding: 12px 14px;
        display: flex;
        align-items: flex-start;
        gap: 8px;
        font-size: 14px;
        color: #14532d;
    }}

    .resolution-icon {{
        font-size: 16px;
        line-height: 1.2;
    }}

    .skipped-banner {{
        background: #f1f5f9;
        border-radius: 6px;
        padding: 12px 16px;
        font-size: 13px;
        color: #64748b;
        display: flex;
        align-items: center;
        gap: 8px;
    }}

    .action-table-wrap {{
        overflow-x: auto;
    }}

    .action-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
        margin-top: 6px;
    }}

    .action-table th {{
        background: #f1f5f9;
        padding: 8px 12px;
        color: #475569;
        font-weight: 600;
        border-bottom: 1px solid var(--card-border);
        text-align: left;
    }}

    .action-table td {{
        padding: 8px 12px;
        border-bottom: 1px solid #f1f5f9;
    }}

    .deadline-tag {{
        background: #e2e8f0;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 12px;
        color: #475569;
    }}

    .no-action {{
        font-size: 13px;
        color: #94a3b8;
        margin: 4px 0 0 0;
    }}

    .adhoc-section {{
        margin-top: 32px;
    }}

    .adhoc-item {{
        background: #fffbeb;
        border: 1px solid #fef3c7;
        border-left: 4px solid #f59e0b;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    }}

    .adhoc-header {{
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin-bottom: 8px;
    }}

    .adhoc-header h4 {{
        margin: 0;
        font-size: 16px;
        color: #92400e;
    }}

    .adhoc-speaker {{
        font-size: 13px;
        color: #b45309;
    }}

    .adhoc-content {{
        font-size: 14px;
        color: #78350f;
        margin-bottom: 8px;
    }}

    .adhoc-action {{
        font-size: 13px;
        color: #92400e;
        border-top: 1px dashed #fde68a;
        padding-top: 8px;
    }}
    """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(theme)} · 议程全景纪要</title>
    <style>{css}</style>
</head>
<body>
    <div class="agenda-container">
        <!-- 头部大盘 -->
        <div class="hero-header">
            <h1 class="hero-title">{escape(theme)} · 议程全景纪要</h1>
            <div class="hero-meta-grid">
                <div>📅 <strong>会议时间：</strong>{escape(date_time)}</div>
                <div>📊 <strong>议题大盘：</strong>共 {total_cnt} 项（有效审议 {discussed_cnt} 项 · 本次未讨论 {skipped_cnt} 项）</div>
                <div>👥 <strong>与会概况：</strong>{escape(attendees[:80])}...</div>
            </div>
            <div class="overview-box">
                <strong>总体评价与结论导向：</strong>{_md_inline(overview)}
            </div>
        </div>

        <!-- 一览表 -->
        <h2 class="section-title"><span>📋</span> 第一部分：议题完成情况一览表</h2>
        <div class="summary-table-wrap">
            <table class="summary-table">
                <thead>
                    <tr>
                        <th class="col-seq">序号</th>
                        <th class="col-title">议题规范全称</th>
                        <th class="col-pres">汇报人/单位</th>
                        <th class="col-status">结论定调</th>
                        <th class="col-res">核心结论与后续安排</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(table_rows)}
                </tbody>
            </table>
        </div>

        <!-- 逐项详实记录 -->
        <h2 class="section-title"><span>📑</span> 第二部分：既定议程逐项详实记录</h2>
        <div class="agenda-cards-wrap">
            {''.join(cards)}
        </div>

        <!-- 临时追加议题 -->
        {adhoc_html}
    </div>
</body>
</html>
"""
    return html
