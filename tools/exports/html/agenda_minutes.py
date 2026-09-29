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


def _normalize_conclusion_points(val: Any) -> list[str]:
    """统一规范化结论与状态字段为干净的条目列表，剔除 Python repr 符号与多余空行。"""
    if val is None or val is False:
        return []
    if isinstance(val, (list, tuple, set)):
        res = []
        for x in val:
            res.extend(_normalize_conclusion_points(x))
        return [r for r in res if r]

    s = str(val).strip()
    if not s:
        return []

    # 1. 修复历史上因 str(list) 产生的 "['item1', 'item2']" 字符串
    if s.startswith("[") and s.endswith("]") and ("'," in s or '",' in s or "','" in s or '","' in s):
        import ast

        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple)):
                return _normalize_conclusion_points(parsed)
        except Exception:
            pass
        inner = s[1:-1].strip()
        parts = re.split(r"'\s*,\s*'|\"\s*,\s*\"", inner)
        cleaned = [p.strip().strip("'\"").strip() for p in parts if p.strip().strip("'\"").strip()]
        if len(cleaned) > 1:
            return _normalize_conclusion_points(cleaned)

    # 2. 预处理：解耦定调语句与前置约束标题（如 '...通过。生效前置约束：1）...' -> '...通过。\n1）...'）
    s = re.sub(r'^\s*(?:发布前置条件|生效前置约束|前置条件|前置约束|附带条件|后续要求|主要关注项|注意事项)[：:]\s*', '', s)
    s = re.sub(r'([。；;\n])?\s*(?:发布前置条件|生效前置约束|前置条件|前置约束|附带条件|后续要求|主要关注项|注意事项)[：:]\s*', lambda m: (m.group(1) or '。') + '\n', s)
    s = re.sub(r'([。；;\n])?\s*(?:现场未决卡点|现场卡点|未决卡点|遗留卡点)[：:]\s*', lambda m: (m.group(1) or '。') + '\n', s)

    # 3. 标号前置断行：在 1） 2） 1. (1) ① 一是 等标记前切开
    num_pattern = re.compile(r'(?<=[^0-9\n])(?=(?:[1-9]\d*[\.、）\)]|[(（][1-9]\d*[)）]|[①-⑩]|(?:一是|二是|三是|四是|五是)|(?:第一[，,、]|第二[，,、]|第三[，,、])))')
    s = num_pattern.sub('\n', s)

    # 4. 按行切分
    lines = [line.strip() for line in s.splitlines() if line.strip()]

    # 5. 若未成功分行，但包含 2 个及以上分号，按分号切分
    if len(lines) == 1 and (lines[0].count('；') >= 2 or lines[0].count(';') >= 2):
        lines = [p.strip() for p in re.split(r'[；;]\s*', lines[0]) if p.strip()]

    # 6. 清洗每条开头的数字标号与冗余前缀（如“生效前置约束 1：”等，实现一点一行干货直出）
    cleaned = []
    for it in lines:
        it = re.sub(r'^(?:[-*•·\s]+|(?:[1-9]\d*[\.、）\)]|[(（][1-9]\d*[)）]|[①-⑩]|(?:一是|二是|三是|四是|五是)|(?:第一[，,、]|第二[，,、]|第三[，,、])))\s*', '', it).strip()
        it = re.sub(r'^(?:发布前置条件|生效前置约束|前置条件|前置约束|附带条件|现场未决卡点|现场卡点|未决卡点|遗留卡点)\s*\d*\s*[：:]\s*', '', it).strip()
        if re.search(r'^(?:现场)?无(?:其他)?(?:阻塞|卡点|遗留|风险|问题)', it):
            continue
        if it:
            cleaned.append(it)

    return cleaned or [s]


def _safe_str(val: Any) -> str:
    if val is None or val is False:
        return ""
    pts = _normalize_conclusion_points(val)
    if len(pts) > 1:
        return "；".join(pts)
    if pts:
        return pts[0]
    return str(val).strip()


def _md_inline(text: str) -> str:
    """行内简易 Markdown 转 HTML。"""
    if not text:
        return ""
    escaped = escape(text, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped


def format_agenda_minutes_markdown(draft: dict[str, Any]) -> str:
    """把结构化草稿排版为标准 Markdown 纪要（result.md）。

    标题恒为「# 议程纪要」（H1 硬编码）。历史上这里收过一个 ``title`` 形参，
    但函数体从未引用它，调用方（编排无模板分支、Render.render_draft）传进来的
    计算值一直被丢弃——是未完成的接线而非可用开关，故删参以免误导。
    """
    meta = draft.get("meeting_meta") or {}
    items = draft.get("agenda_items") or []

    date_time = meta.get("date_time") or "2026年度会议"
    stats = meta.get("agenda_stats") or f"既定议题共 {len(items)} 项"

    lines = [
        "# 议程纪要",
        "",
        f"> **会议时间**：{date_time}  ",
        f"> **议程进展总览**：{stats}",
        "",
        "---",
        "",
        "## 议题总览",
        "",
        "| 议题名称 | 汇报人 | 议题时长 | 结论定调 |",
        "| :--- | :---: | :---: | :---: |",
    ]

    for it in items:
        it_title = it.get("agenda_title") or "议题"
        pres = it.get("presenter") or "未记录"
        state = it.get("discussion_state") or "discussed"
        raw_status = it.get("status_tag") or ("本次未讨论" if state == "skipped" else "审议通过")
        tag = _normalize_status_tag(raw_status, is_skipped=(state == "skipped"))
        time_range = str(it.get("time_range") or "—").strip() or "—"
        if state == "skipped" or tag == "本次未讨论":
            time_range = "—"
        lines.append(f"| {it_title} | {pres} | {time_range} | `{tag}` |")

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
        raw_status = it.get("status_tag") or ("本次未讨论" if state == "skipped" else "审议通过")
        tag = _normalize_status_tag(raw_status, is_skipped=(state == "skipped"))

        lines.extend([
            f"### 议题 {seq} · {it_title}",
            "",
            f"- **汇报人/责任单位**：{pres}",
            f"- **结论定调**：`{tag}`",
            "",
        ])

        if state == "skipped" or tag == "本次未讨论":
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
        conclusion_raw = it.get("conclusion_and_status") or it.get("resolution") or ""
        pts = _normalize_conclusion_points(conclusion_raw)
        lines.append("#### 4. 结论与状态")
        if not pts:
            lines.extend(["> （本次会议未记录到明确决议）", ""])
        else:
            lines.extend([f"> - {p}" for p in pts] + [""])

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


def _normalize_status_tag(tag: Any, is_skipped: bool = False) -> str:
    """归一化结论定调为标准四态体系：[审议通过, 有条件通过, 未通过, 本次未讨论]。"""
    if is_skipped:
        return "本次未讨论"
    if not tag:
        return "审议通过"
    s = str(tag).strip()
    s_clean = re.sub(r"^[\[【（(]\s*|\s*[\]】）)]$", "", s).strip()
    if not s_clean:
        return "审议通过"
    if "未讨论" in s_clean or "跳过" in s_clean or "skipped" in s_clean.lower():
        return "本次未讨论"
    if any(k in s_clean for k in ("未通过", "待补充", "补充材料", "材料", "延期", "再议", "否决", "不通过", "打回", "暂停")):
        return "未通过"
    if any(k in s_clean for k in ("条件", "原则", "共识", "认可", "建议", "预研")):
        return "有条件通过"
    if any(k in s_clean for k in ("通过", "放行", "同意", "采纳", "批准")):
        return "审议通过"
    return "审议通过"


def _status_class(status: str, is_skipped: bool = False) -> tuple[str, str]:
    """返回 (badge_class, display_text)。"""
    tag = _normalize_status_tag(status, is_skipped=is_skipped)
    if tag == "本次未讨论":
        return "badge-skipped", tag
    if tag == "未通过":
        return "badge-rejected", tag
    if tag == "有条件通过":
        return "badge-conditional", tag
    return "badge-approved", tag


def _format_action_items_text(
    action_items: list[Any] | None,
    is_skipped: bool = False,
    is_html: bool = False,
) -> str:
    """格式化议题总览表格中的「待办与要求」列：
    - 不加序号，每个待办末尾加分号；
    - 若包含 deadline 则拼接为 '{task} 时限：{deadline}；'，若无则直接 '{task}；'；
    - 多项待办逐行呈现（Markdown 使用 <br>，HTML 使用 div）；
    - 若讨论闭环无待办则显示 '现场闭环（无遗留待办）'；
    - 若未讨论则显示 '—'。
    """
    if is_skipped:
        return "—"

    raw_list = action_items or []
    lines: list[str] = []
    for item in raw_list:
        if isinstance(item, dict):
            task = str(item.get("task") or "").strip()
            deadline = str(item.get("deadline") or "").strip()
        elif isinstance(item, str):
            task = item.strip()
            deadline = ""
        else:
            continue

        task = re.sub(r"[；;。，,\s]+$", "", task).strip()
        deadline = re.sub(r"[；;。，,\s]+$", "", deadline).strip()
        if not task:
            continue

        if deadline:
            line_str = f"{task} 时限：{deadline}；"
        else:
            line_str = f"{task}；"
        lines.append(line_str)

    if not lines:
        return "现场闭环（无遗留待办）"

    if is_html:
        item_divs = "".join(f'<div class="action-item-line">{_md_inline(l)}</div>' for l in lines)
        return f'<div class="summary-actions-wrap">{item_divs}</div>'
    else:
        return "<br>".join(lines).replace("|", r"\|")


def render_agenda_minutes_html(
    title: str,
    text: str,
    data: dict[str, Any] | None = None,
) -> str:
    """渲染遵循 LaTeX Paper / 企业标准报告风格的 HTML 纪要页面。"""
    draft = data or {}
    meta = draft.get("meeting_meta") or {}
    items = draft.get("agenda_items") or []

    date_time = meta.get("date_time") or "2026年度会议"
    stats = meta.get("agenda_stats") or f"共 {len(items)} 项议题"

    total_cnt = len(items)
    discussed_cnt = sum(
        1 for it in items
        if it.get("discussion_state") != "skipped" and _normalize_status_tag(it.get("status_tag")) != "本次未讨论"
    )
    skipped_cnt = total_cnt - discussed_cnt

    # 构建议题总览表格行
    table_rows = []
    for it in items:
        seq = _safe_str(it.get("agenda_seq") or "01")
        it_title = _safe_str(it.get("agenda_title") or "议题")
        pres = _safe_str(it.get("presenter") or "未记录")
        raw_status = _safe_str(it.get("status_tag") or "审议通过")
        state = _safe_str(it.get("discussion_state") or "discussed")
        badge_cls, badge_text = _status_class(raw_status, is_skipped=(state == "skipped"))
        time_range = _safe_str(it.get("time_range") or "—")
        if state == "skipped" or badge_text == "本次未讨论":
            time_range = "—"

        table_rows.append(f"""
        <tr>
            <td class="col-title"><a href="#topic-{seq}">{escape(it_title)}</a></td>
            <td class="col-pres">{escape(pres)}</td>
            <td class="col-time">{escape(time_range)}</td>
            <td class="col-status"><span class="badge {badge_cls}">{escape(badge_text)}</span></td>
        </tr>
        """)

    # 构建议题卡片
    cards = []
    for it in items:
        seq = _safe_str(it.get("agenda_seq") or "01")
        it_title = _safe_str(it.get("agenda_title") or "议题")
        pres = _safe_str(it.get("presenter") or "未记录")
        raw_status = _safe_str(it.get("status_tag") or "审议通过")
        state = _safe_str(it.get("discussion_state") or "discussed")
        badge_cls, badge_text = _status_class(raw_status, is_skipped=(state == "skipped"))

        if state == "skipped" or badge_text == "本次未讨论":
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
        conclusion_raw = it.get("conclusion_and_status") or it.get("resolution") or ""
        pts = _normalize_conclusion_points(conclusion_raw)
        if not pts:
            conclusion_content = '<span class="no-res">（本次会议未形成明确决议）</span>'
        else:
            items_html = "".join(f"<li>{_md_inline(p)}</li>" for p in pts)
            conclusion_content = f'<ul class="res-box-list">{items_html}</ul>'

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
      width: 120px;
      text-align: center;
      white-space: nowrap;
    }
    .col-time {
      width: 130px;
      text-align: center;
      white-space: nowrap;
      color: #555555;
      font-variant-numeric: tabular-nums;
    }
    .col-status {
      width: 110px;
      text-align: center;
      white-space: nowrap;
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
    .badge-rejected {
      background: #fdecea;
      color: #b71c1c;
      border: 1px solid #ffcdd2;
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
      padding: 8px 14px;
      font-size: var(--ck-fs);
      color: #1b4d1d;
      line-height: 1.6;
    }
    .res-box-list {
      margin: 0;
      padding-left: 1.35em;
      list-style-type: disc;
    }
    .res-box-list li {
      margin: 4px 0;
      line-height: 1.6;
    }
    .res-single {
      margin: 0;
    }
    .summary-res-list {
      margin: 0;
      padding-left: 1.25em;
      line-height: 1.5;
    }
    .summary-res-list li {
      margin: 3px 0;
    }
    .no-res {
      color: #666666;
      font-style: italic;
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
    <title>议程纪要</title>
    <style>
{_latex_paper_css()}
{custom_css}
    </style>
</head>
<body>
    <main class="page">
        <div class="ck-doc">
            <header class="ck-doc-header">
                <h1>议程纪要</h1>
                <div class="ck-doc-meta">
                    <span>会议时间：{escape(date_time)}</span> &nbsp;|&nbsp;
                    <span>议程进展：共 {total_cnt} 项（有效审议 {discussed_cnt} 项，本次未讨论 {skipped_cnt} 项）</span>
                </div>
            </header>

            <div class="ck-doc-content">
                <h2 class="ck-doc-h2" style="margin-top: 20px;">议题总览</h2>
                <table class="ck-table summary-table">
                    <thead>
                        <tr>
                            <th class="col-title">议题名称</th>
                            <th class="col-pres">汇报人</th>
                            <th class="col-time">议题时长</th>
                            <th class="col-status">结论定调</th>
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
