"""agenda_minutes.py -- 议程驱动型会议纪要的双模态导出（Markdown 与 LaTeX Paper 风格 HTML）。

包含：
1. format_agenda_minutes_markdown：结构化 draft 确定性渲染为 Markdown (result.md)；
2. render_agenda_minutes_html：渲染为高规格政企/学术 LaTeX Paper 风格 HTML 页面 (agenda_minutes.html)。
"""
from __future__ import annotations

from html import escape
import re
from typing import Any

from infra.exporters.html.paper_css import latex_paper_css as _latex_paper_css


def _is_nested_bullet_block(s: str) -> bool:
    """判断字符串是否为【加粗主题 + 二级列表项】的嵌套结构。"""
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if len(lines) <= 1:
        return False
    if not (lines[0].startswith("**") and "**" in lines[0][2:]):
        return False
    for ln in lines[1:]:
        if not re.match(r"^[-*•·]\s+", ln):
            return False
    return True


def auto_structure_bullet(text: str) -> str:
    """智能将单段式大段内容重构成 一级加粗主题 + 二级自然列表。

    若文本已经是多行结构，或主体较短，则保持原样；
    若包含“主题：长文本（多个句号分号）”，自动提炼加粗主题并拆出二级子列表。
    """
    s = str(text).strip()
    if not s:
        return ""
    if "\n" in s:
        return s

    # 匹配加粗或未加粗主题：如 **主题**： 或 主题：
    m = re.match(r"^(\*\*[^*]+?\*\*|[^\n：:]{2,20})[：:]\s*(.+)$", s)
    if not m:
        return s

    title, body = m.group(1).strip(), m.group(2).strip()
    if not title.startswith("**"):
        title = f"**{title}**"

    # 若主体文本较短或断句不足，保持原样
    if len(body) < 60 or (body.count("。") + body.count("；")) < 2:
        return f"{title}：{body}"

    # 按句号/分号切分句子
    raw_parts = re.split(r"([。；])", body)
    sentences = []
    curr = ""
    for p in raw_parts:
        curr += p
        if p in ("。", "；") and len(curr.strip()) >= 15:
            sentences.append(curr.strip())
            curr = ""
    if curr.strip():
        if sentences and len(curr.strip()) < 15:
            sentences[-1] += curr.strip()
        else:
            sentences.append(curr.strip())

    if len(sentences) >= 2:
        sub_bullets = "\n".join(
            f"- {sent.rstrip('；。')}；" if i < len(sentences) - 1 else f"- {sent.rstrip('；。')}。"
            for i, sent in enumerate(sentences)
        )
        return f"{title}：\n{sub_bullets}"

    return f"{title}：{body}"


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

    # 如果是多行二级嵌套结构（加粗标题 + 子列表），整块保留为一个条目
    if _is_nested_bullet_block(s):
        lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
        first = lines[0]
        subs = [re.sub(r"^[-*•·]\s*", "", ln).strip() for ln in lines[1:]]
        subs = [sub for sub in subs if sub]
        if subs:
            return [first + "\n" + "\n".join(f"- {sub}" for sub in subs)]
        return [first]

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

    # 6. 清洗每条开头的数字标号与冗余前缀（保留 ** 加粗标记）
    cleaned = []
    for it in lines:
        it = re.sub(r'^(?:[-•·]\s*|\*(?!\*)\s*|\s+|(?:[1-9]\d*[\.、）\)]|[(（][1-9]\d*[)）]|[①-⑩]|(?:一是|二是|三是|四是|五是)|(?:第一[，,、]|第二[，,、]|第三[，,、])))\s*', '', it).strip()
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


def _format_markdown_bullet(text: str) -> str:
    """把单个内容条目格式化为带层级的 Markdown 列表，支持二级子列表。"""
    s = auto_structure_bullet(text)
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return ""
    first = re.sub(r"^[-•·]\s*|^\*(?!\*)\s*", "", lines[0]).strip()
    res = [f"- {first}"]
    for ln in lines[1:]:
        sub = re.sub(r"^[-•·]\s*|^\*(?!\*)\s*", "", ln).strip()
        if sub:
            res.append(f"  - {sub}")
    return "\n".join(res)


def _format_markdown_quote_bullet(text: str) -> str:
    """把单个认知条目格式化为引用块中的 Markdown 列表，支持二级子列表。"""
    s = auto_structure_bullet(text)
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return ""
    first = re.sub(r"^[-•·]\s*|^\*(?!\*)\s*", "", lines[0]).strip()
    res = [f"> - {first}"]
    for ln in lines[1:]:
        sub = re.sub(r"^[-•·]\s*|^\*(?!\*)\s*", "", ln).strip()
        if sub:
            res.append(f">   - {sub}")
    return "\n".join(res)


def _render_content_li(item: str) -> str:
    """把单个内容条目渲染为 HTML <li>，支持二级子列表。"""
    s = auto_structure_bullet(item)
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return ""
    if len(lines) == 1:
        return f"<li>{_md_inline(lines[0])}</li>"

    first = re.sub(r"^[-•·]\s*|^\*(?!\*)\s*", "", lines[0]).strip()
    sub_lis = []
    for sub in lines[1:]:
        clean_sub = re.sub(r"^[-•·]\s*|^\*(?!\*)\s*", "", sub).strip()
        if clean_sub:
            sub_lis.append(f"<li>{_md_inline(clean_sub)}</li>")

    if sub_lis:
        sub_ul = f'<ul class="sub-bullet-list">{"".join(sub_lis)}</ul>'
        return f'<li class="content-group"><span class="content-topic-title">{_md_inline(first)}</span>{sub_ul}</li>'
    return f"<li>{_md_inline(first)}</li>"


def _render_insight_li(item: str) -> str:
    """把单个核心认知条目渲染为 HTML <li>，支持二级子列表。"""
    s = auto_structure_bullet(item)
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return ""
    if len(lines) == 1:
        return f"<li>{_md_inline(lines[0])}</li>"

    first = re.sub(r"^[-•·]\s*|^\*(?!\*)\s*", "", lines[0]).strip()
    sub_lis = []
    for sub in lines[1:]:
        clean_sub = re.sub(r"^[-•·]\s*|^\*(?!\*)\s*", "", sub).strip()
        if clean_sub:
            sub_lis.append(f"<li>{_md_inline(clean_sub)}</li>")

    if sub_lis:
        sub_ul = f'<ul class="sub-bullet-list">{"".join(sub_lis)}</ul>'
        return f'<li class="insight-group"><span class="insight-topic-title">{_md_inline(first)}</span>{sub_ul}</li>'
    return f"<li>{_md_inline(first)}</li>"


def format_agenda_minutes_markdown(draft: dict[str, Any]) -> str:
    """把结构化草稿排版为标准 Markdown 纪要（result.md）。

    标题恒为「# 议程纪要」（H1 硬编码）。
    自适应规则：
    1. 宏观总览表格：若全场无审批类议题，折叠为 3 列精炼表；若有审批类议题，展示 4 列标准表；
    2. 微观议题详情：基础三栏（背景与目标、核心内容、核心认知）；仅当存在实际会后待办时输出第四栏（后续行动），否则自然圆满闭环。
    """
    meta = draft.get("meeting_meta") or {}
    items = draft.get("agenda_items") or []

    date_time = meta.get("date_time") or "2026年度会议"
    stats = meta.get("agenda_stats") or f"既定议题共 {len(items)} 项"

    has_approval = any(
        str(it.get("agenda_category") or "").strip().lower() == "approval"
        or (
            it.get("agenda_category") is None
            and _normalize_status_tag(it.get("status_tag"), category="approval") in {"审议通过", "原则同意", "待补充材料", "未通过"}
        )
        for it in items
    )

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
    ]

    if not has_approval:
        lines.extend([
            "| 议题名称 | 汇报人 | 议题时长 |",
            "| :--- | :---: | :---: |",
        ])
        for it in items:
            it_title = it.get("agenda_title") or "议题"
            pres = it.get("presenter") or "未记录"
            state = it.get("discussion_state") or "discussed"
            tag = _normalize_status_tag(it.get("status_tag"), category="share", is_skipped=(state == "skipped"))
            time_range = str(it.get("time_range") or "—").strip() or "—"
            if state == "skipped" or tag == "本次未讨论":
                time_range = "—"
                it_title = f"{it_title} `(本次未讨论)`"
            lines.append(f"| {it_title} | {pres} | {time_range} |")
    else:
        lines.extend([
            "| 议题名称 | 汇报人 | 议题时长 | 结论定调 |",
            "| :--- | :---: | :---: | :---: |",
        ])
        for it in items:
            it_title = it.get("agenda_title") or "议题"
            pres = it.get("presenter") or "未记录"
            state = it.get("discussion_state") or "discussed"
            cat = str(it.get("agenda_category") or "approval").strip().lower()
            raw_status = it.get("status_tag") or ("本次未讨论" if state == "skipped" else "")
            tag = _normalize_status_tag(raw_status, category=cat, is_skipped=(state == "skipped"))
            time_range = str(it.get("time_range") or "—").strip() or "—"
            if state == "skipped" or tag == "本次未讨论":
                time_range = "—"
                status_cell = "`本次未讨论`"
            elif cat != "approval" or not tag:
                status_cell = "—"
            else:
                status_cell = f"`{tag}`"
            lines.append(f"| {it_title} | {pres} | {time_range} | {status_cell} |")

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
        cat = str(it.get("agenda_category") or "approval").strip().lower()
        raw_status = it.get("status_tag") or ("本次未讨论" if state == "skipped" else "")
        tag = _normalize_status_tag(raw_status, category=cat, is_skipped=(state == "skipped"))

        item_header_lines = [
            f"### {it_title}",
            "",
            f"- **汇报人/责任单位**：{pres}",
        ]
        if state == "skipped" or tag == "本次未讨论":
            item_header_lines.append("- **结论定调**：`本次未讨论`")
        elif cat == "approval" and tag:
            item_header_lines.append(f"- **结论定调**：`{tag}`")
        item_header_lines.append("")
        lines.extend(item_header_lines)

        if state == "skipped" or tag == "本次未讨论":
            lines.extend([
                "> （本次会议录音转写未见本议题汇报或讨论记录）",
                "",
            ])
            continue

        # 1. 背景与目标
        lines.append("#### 1. 背景与目标")
        bg_val = it.get("background_and_goals")
        if not bg_val:
            target_list = it.get("target_and_audience") or it.get("proposal_highlights") or []
            if target_list:
                if len(target_list) == 1:
                    bg_val = target_list[0]
                else:
                    bg_val = " ".join(target_list)
            else:
                bg_val = "按既定方案申报，明确核心诉求与预期目标。"
        if isinstance(bg_val, list):
            for p in bg_val:
                lines.append(f"- {p}")
        else:
            lines.append(str(bg_val).strip())
        lines.append("")

        # 2. 核心内容
        content_list = it.get("core_content")
        if not content_list:
            content_raw = it.get("content_and_evidence")
            c_list = []
            if isinstance(content_raw, list):
                c_list.extend(content_raw)
            elif isinstance(content_raw, dict):
                c_list.extend(content_raw.get("key_metrics") or [])
                c_list.extend(content_raw.get("facts_and_options") or [])
            else:
                delib = it.get("deliberation_details") or {}
                if isinstance(delib, dict):
                    c_list.extend(delib.get("key_metrics") or [])

            process_raw = it.get("process_and_interaction")
            p_list = []
            if isinstance(process_raw, list):
                p_list.extend(process_raw)
            elif isinstance(process_raw, dict):
                p_list.extend(process_raw.get("feedback_concerns") or [])
                p_list.extend(process_raw.get("focus_debates") or [])
            else:
                delib = it.get("deliberation_details") or {}
                if isinstance(delib, dict):
                    p_list.extend(delib.get("feedback_concerns") or [])

            content_list = c_list + p_list

        lines.append("#### 2. 核心内容")
        if content_list:
            for m in content_list:
                formatted = _format_markdown_bullet(m)
                if formatted:
                    lines.append(formatted)
        else:
            lines.append("- 依据现场方案申报材料与基线指标开展审议。")
        lines.append("")

        # 3. 核心认知
        insights_raw = it.get("core_insights") or it.get("conclusion_and_status") or it.get("resolution") or ""
        pts = _normalize_conclusion_points(insights_raw)
        lines.append("#### 3. 核心认知")
        if not pts:
            lines.extend(["> （本次会议未记录到特别沉淀内容）", ""])
        else:
            for p in pts:
                formatted_quote = _format_markdown_quote_bullet(p)
                if formatted_quote:
                    lines.append(formatted_quote)
            lines.append("")

        # 4. 后续行动 (仅当存在实际 action_items 时输出，否则彻底不渲染)
        actions = it.get("action_items") or it.get("action_commitments") or []
        if actions:
            lines.append("#### 4. 后续行动")
            lines.extend([
                "| 责任人 | 跟进事项与交付目标 | 时限节点 |",
                "| :--- | :--- | :--- |",
            ])
            for act in actions:
                owner = act.get("owner") or "待定"
                task = act.get("task") or "后续跟进"
                deadline = act.get("deadline") or "近期"
                lines.append(f"| {owner} | {task} | {deadline} |")
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def _normalize_status_tag(tag: Any, category: str = "approval", is_skipped: bool = False) -> str:
    """归一化结论定调为标准状态体系。"""
    if is_skipped:
        return "本次未讨论"

    cat = str(category or "approval").strip().lower()
    if cat not in ("approval", "share", "consensus"):
        cat = "approval"

    if cat != "approval":
        if not tag:
            return ""
        s_raw = str(tag).strip()
        if any(k in s_raw for k in ("未讨论", "跳过", "skipped")):
            return "本次未讨论"
        return ""

    if not tag:
        return ""

    s = str(tag).strip()
    s_clean = re.sub(r"^[\[【（(]\s*|\s*[\]】）)]$", "", s).strip()
    if not s_clean or s_clean in ("—", "-", "无", "留空", "无表决", "无需表决", "未记录", "null", "none"):
        return ""

    if "未讨论" in s_clean or "跳过" in s_clean or "skipped" in s_clean.lower():
        return "本次未讨论"

    if any(k in s_clean for k in ("未通过", "待补充", "补充材料", "材料", "延期", "再议", "否决", "不通过", "打回", "暂停")):
        return "未通过"
    if any(k in s_clean for k in ("条件", "原则", "共识", "认可", "建议", "预研")):
        return "有条件通过"
    if any(k in s_clean for k in ("通过", "放行", "同意", "采纳", "批准")):
        return "审议通过"
    return ""


def _status_class(status: str, category: str = "approval", is_skipped: bool = False) -> tuple[str, str]:
    """返回 (badge_class, display_text)。

    展示徽标：
    - 评审类：【✅ 审议通过】 / 【⚠️ 有条件通过】 / 【❌ 未通过】
    - 非评审类（分享、研讨、协同等）：直接留空 ("", "")
    - 跳过项：【本次未讨论】
    """
    tag = _normalize_status_tag(status, category=category, is_skipped=is_skipped)
    if is_skipped or tag == "本次未讨论":
        return "badge-skipped", "本次未讨论"
    if category != "approval" or not tag:
        return "", ""
    if tag == "未通过":
        return "badge-rejected", "❌ 未通过"
    if tag == "有条件通过":
        return "badge-conditional", "⚠️ 有条件通过"
    return "badge-approved", "✅ 审议通过"


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

    total_cnt = len(items)
    discussed_cnt = sum(
        1 for it in items
        if it.get("discussion_state") != "skipped" and _normalize_status_tag(it.get("status_tag")) != "本次未讨论"
    )
    skipped_cnt = total_cnt - discussed_cnt

    has_approval = any(
        str(it.get("agenda_category") or "").strip().lower() == "approval"
        or (
            it.get("agenda_category") is None
            and _normalize_status_tag(it.get("status_tag"), category="approval") in {"审议通过", "原则同意", "待补充材料", "未通过"}
        )
        for it in items
    )

    # 构建议题总览表格行
    table_rows = []
    for it in items:
        seq = _safe_str(it.get("agenda_seq") or "01")
        it_title = _safe_str(it.get("agenda_title") or "议题")
        pres = _safe_str(it.get("presenter") or "未记录")
        cat = str(it.get("agenda_category") or "approval").strip().lower()
        state = _safe_str(it.get("discussion_state") or "discussed")
        raw_status = _safe_str(it.get("status_tag") or ("本次未讨论" if state == "skipped" else ""))
        badge_cls, badge_text = _status_class(raw_status, category=cat, is_skipped=(state == "skipped"))
        time_range = _safe_str(it.get("time_range") or "—")
        if state == "skipped" or badge_text == "本次未讨论":
            time_range = "—"

        if not has_approval:
            skipped_note = ' <span style="font-size:0.8rem;color:#888;">(本次未讨论)</span>' if (state == "skipped" or badge_text == "本次未讨论") else ""
            table_rows.append(f"""
            <tr>
                <td class="col-title"><a href="#topic-{seq}">{escape(it_title)}</a>{skipped_note}</td>
                <td class="col-pres">{escape(pres)}</td>
                <td class="col-time">{escape(time_range)}</td>
            </tr>
            """)
        else:
            status_td = f'<span class="badge {badge_cls}">{escape(badge_text)}</span>' if badge_text else '<span style="color:#888;">—</span>'
            table_rows.append(f"""
            <tr>
                <td class="col-title"><a href="#topic-{seq}">{escape(it_title)}</a></td>
                <td class="col-pres">{escape(pres)}</td>
                <td class="col-time">{escape(time_range)}</td>
                <td class="col-status">{status_td}</td>
            </tr>
            """)

    if not has_approval:
        table_head_html = """<thead>
                        <tr>
                            <th class="col-title">议题名称</th>
                            <th class="col-pres">汇报人</th>
                            <th class="col-time">议题时长</th>
                        </tr>
                    </thead>"""
    else:
        table_head_html = """<thead>
                        <tr>
                            <th class="col-title">议题名称</th>
                            <th class="col-pres">汇报人</th>
                            <th class="col-time">议题时长</th>
                            <th class="col-status">结论定调</th>
                        </tr>
                    </thead>"""

    # 构建议题卡片
    cards = []
    for it in items:
        seq = _safe_str(it.get("agenda_seq") or "01")
        it_title = _safe_str(it.get("agenda_title") or "议题")
        pres = _safe_str(it.get("presenter") or "未记录")
        cat = str(it.get("agenda_category") or "approval").strip().lower()
        state = _safe_str(it.get("discussion_state") or "discussed")
        raw_status = _safe_str(it.get("status_tag") or ("本次未讨论" if state == "skipped" else ""))
        badge_cls, badge_text = _status_class(raw_status, category=cat, is_skipped=(state == "skipped"))
        badge_html = f'<span class="badge {badge_cls}">{escape(badge_text)}</span>' if (badge_text and (cat == "approval" or state == "skipped")) else ""

        if state == "skipped" or badge_text == "本次未讨论":
            card_html = f"""
            <div class="agenda-card card-skipped" id="topic-{seq}">
                <div class="card-header">
                    <div class="card-title-group">
                        <h3 class="topic-name">{escape(it_title)}</h3>
                    </div>
                    {badge_html}
                </div>
                <div class="card-skipped-body">
                    <span class="card-meta">汇报人/责任单位：{escape(pres)}</span>
                    <span class="skipped-banner">（本次会议录音转写未见本议题汇报或讨论记录）</span>
                </div>
            </div>
            """
            cards.append(card_html)
            continue

        # 1. 背景与目标
        bg_val = it.get("background_and_goals")
        if not bg_val:
            target = it.get("target_and_audience") or it.get("proposal_highlights") or []
            if target:
                if len(target) == 1:
                    bg_val = target[0]
                else:
                    bg_val = list(target)
            else:
                bg_val = "按既定方案申报，明确核心诉求与预期目标。"
        if isinstance(bg_val, list):
            bg_html = f'<ul class="bullet-list">{"".join(f"<li>{_md_inline(p)}</li>" for p in bg_val)}</ul>'
        else:
            bg_html = f'<p class="pillar-desc">{_md_inline(str(bg_val))}</p>'

        # 2. 核心内容
        content_list = it.get("core_content")
        if not content_list:
            content_raw = it.get("content_and_evidence")
            c_list = []
            if isinstance(content_raw, list):
                c_list.extend(content_raw)
            elif isinstance(content_raw, dict):
                c_list.extend(content_raw.get("key_metrics") or [])
                c_list.extend(content_raw.get("facts_and_options") or [])
            else:
                delib = it.get("deliberation_details") or {}
                if isinstance(delib, dict):
                    c_list.extend(delib.get("key_metrics") or [])

            process_raw = it.get("process_and_interaction")
            p_list = []
            if isinstance(process_raw, list):
                p_list.extend(process_raw)
            elif isinstance(process_raw, dict):
                p_list.extend(process_raw.get("feedback_concerns") or [])
                p_list.extend(process_raw.get("focus_debates") or [])
            else:
                delib = it.get("deliberation_details") or {}
                if isinstance(delib, dict):
                    p_list.extend(delib.get("feedback_concerns") or [])

            content_list = c_list + p_list

        content_li = "".join(_render_content_li(m) for m in content_list) if content_list else "<li>依据现场方案申报材料与基线指标开展审议。</li>"

        # 3. 核心认知
        conclusion_raw = it.get("core_insights") or it.get("conclusion_and_status") or it.get("resolution") or ""
        pts = _normalize_conclusion_points(conclusion_raw)
        if not pts:
            conclusion_content = '<span class="no-res">（本次会议未记录到特别沉淀内容）</span>'
        else:
            items_html = "".join(_render_insight_li(p) for p in pts)
            conclusion_content = f'<ul class="res-box-list">{items_html}</ul>'

        # 4. 后续行动 (仅当存在实际 action_items 时输出，否则彻底不渲染)
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
            action_section_html = f"""
            <div class="pillar-section">
                <div class="pillar-label"><span class="pillar-num">4</span> 后续行动</div>
                <div class="action-table-wrap">
                    <table class="action-table">
                        <thead>
                            <tr><th>责任人</th><th>跟进事项与交付目标</th><th>时限节点</th></tr>
                        </thead>
                        <tbody>{''.join(act_rows)}</tbody>
                    </table>
                </div>
            </div>
            """
        else:
            action_section_html = ""

        card_html = f"""
        <div class="agenda-card" id="topic-{seq}">
            <div class="card-header">
                <div class="card-title-group">
                    <h3 class="topic-name">{escape(it_title)}</h3>
                </div>
                {badge_html}
            </div>
            <div class="card-meta">
                <span>汇报人/责任单位：{escape(pres)}</span>
            </div>

            <div class="pillar-section">
                <div class="pillar-label"><span class="pillar-num">1</span> 背景与目标</div>
                {bg_html}
            </div>

            <div class="pillar-section">
                <div class="pillar-label"><span class="pillar-num">2</span> 核心内容</div>
                <ul class="bullet-list">{content_li}</ul>
            </div>

            <div class="pillar-section">
                <div class="pillar-label"><span class="pillar-num">3</span> 核心认知</div>
                <div class="resolution-box">
                    <div class="resolution-text">{conclusion_content}</div>
                </div>
            </div>

            {action_section_html}
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
    .badge-divergence {
      background: #fbe9e7;
      color: #bf360c;
      border: 1px solid #ffccbc;
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
    .bullet-list .content-group {
      margin: 6px 0;
    }
    .bullet-list .content-topic-title, .res-box-list .insight-topic-title {
      display: block;
      margin-bottom: 2px;
      color: #111111;
      font-weight: 600;
    }
    .sub-bullet-list {
      margin: 4px 0 6px 0;
      padding-left: 1.25em;
      list-style-type: circle;
      color: #333333;
    }
    .sub-bullet-list li {
      margin: 3px 0;
      line-height: 1.55;
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
    .res-box-list .insight-group {
      margin: 6px 0;
    }
    .res-box-list .sub-bullet-list {
      color: #1b4d1d;
      list-style-type: circle;
    }
    .res-box-list .insight-topic-title {
      color: #1b4d1d;
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
                    {table_head_html}
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
