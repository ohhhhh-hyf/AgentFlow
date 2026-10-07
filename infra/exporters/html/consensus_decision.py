"""Consensus Decision export module.

Generates:
1. Two-section, zero-emoji Markdown Report (Overview Table + Details)
2. Clean Executive Memo HTML Report (Status Pills, Decision Cards)
"""
from __future__ import annotations

from html import escape
import re
from typing import Any

from infra.exporters.html.paper_css import latex_paper_css as _latex_paper_css

GRADE_MAP = {
    "hard_alignment": ("一致赞成", "一致赞成", "grade-hard", "dot-hard"),
    "conditional_concession": ("附带前提", "附带前提", "grade-conditional", "dot-conditional"),
    "unresolved_concern": ("争执未决", "争执未决", "grade-unresolved", "dot-unresolved"),
    "active_disagreement": ("争执未决", "争执未决", "grade-disagreement", "dot-disagreement"),
}

ARCHETYPE_MAP = {
    "data_driven": "数据驱动",
    "authority_fiat": "最终拍板",
    "quid_pro_quo": "协同交换",
    "consensus": "讨论一致",
}

_EMOJI_RE = re.compile(
    r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\ufe0f\u200d]|[\u2300-\u23ff]|[\u2b50\u2b55]"
)


def _remove_emoji(text: str) -> str:
    """去除所有 emoji 符号。"""
    if not text:
        return ""
    return _EMOJI_RE.sub("", text).strip()


def _safe_str(val: Any) -> str:
    if val is None or val is False:
        return ""
    return _remove_emoji(str(val).strip())


def _normalize_grade(raw_grade: str) -> tuple[str, str]:
    """返回 (规范中文标签, css_suffix)。
    成色严格限定为三类：一致赞成 / 附带前提 / 争执未决。
    """
    g = (raw_grade or "").strip().replace("[", "").replace("]", "").replace("`", "")
    if any(k in g for k in ("一致", "hard", "赞成", "通过", "hard_alignment")):
        return "一致赞成", "hard"
    if any(k in g for k in ("附带", "前提", "条件", "conditional", "concession")):
        return "附带前提", "conditional"
    if any(k in g for k in ("争执", "未决", "分歧", "保留", "disagreement", "unresolved")):
        return "争执未决", "disagreement"
    return "一致赞成", "hard"


def _single_sentence(text: str) -> str:
    """提取单句核心陈述，去除首尾标点冗余与多余换行。"""
    if not text:
        return ""
    s = re.sub(r"\s+", " ", text).strip()
    return s


def _brief_accord(accord: str) -> str:
    """提取表格中展示的极简动作定调（15-25字以内一句话讲清核心动作）。"""
    if not accord:
        return "按会议共识推进执行。"
    s = _single_sentence(_remove_emoji(accord))
    if len(s) <= 25:
        return s
    # 优先在常见断句标点处截取第一分句
    parts = re.split(r"[，,；;。]", s)
    first = parts[0].strip()
    if 8 <= len(first) <= 25:
        return first + "。" if not first.endswith("。") else first
    if len(parts) > 1:
        second = parts[1].strip()
        combined = f"{first}，{second}"
        if len(combined) <= 25:
            return combined + "。" if not combined.endswith("。") else combined
    # 兜底截断
    return s[:22].rstrip("，,；;。") + "…"


def format_consensus_decision_markdown(draft: dict[str, Any], title: str = "共识决策") -> str:
    """把结构化草稿格式化为两栏、零 emoji 的决策备忘录 Markdown。
    表格中输出极简动作定调；第二栏决策细节严格按【背景 ➔ 讨论要点 ➔ 得失权衡 ➔ 最终决议】展开。
    """
    issues = draft.get("issues") or []

    display_title = _safe_str(title) or "共识决策"
    if not any(display_title.endswith(s) for s in ("决策", "共识", "决议", "报告")):
        display_title = f"{display_title} · 共识决策"

    md_lines: list[str] = [f"# {display_title}\n"]

    # 第一栏：决策总览（首屏30秒速览看板）
    md_lines.append("## 决策总览\n")
    md_lines.append("| 议题 | 共识成色 | 最终决议 |")
    md_lines.append("| :--- | :---: | :--- |")

    if not issues:
        md_lines.append("| 本次会议暂无重大共识分歧或决策妥协 | [一致赞成] | 各项议题均按常规流程平稳推进 |")
    else:
        for it in issues:
            topic = _safe_str(it.get("topic")) or "核心议题"
            grade_key = _safe_str(it.get("consensus_grade"))
            grade_label, _ = _normalize_grade(grade_key)
            full_accord = _safe_str(it.get("accord")) or "按会议共识推进执行。"
            short_accord = _brief_accord(full_accord)
            md_lines.append(f"| **{topic}** | [{grade_label}] | {short_accord} |")

    md_lines.append("")

    # 第二栏：决策细节（严格按 背景 -> 讨论要点 -> 得失权衡 -> 最终决议 顺序压轴呈现）
    md_lines.append("## 决策细节\n")
    if not issues:
        md_lines.append("本次会议未识别出重大分歧或妥协决议事项，各项议题均以常规流程平稳推进。\n")
        return "\n".join(md_lines)

    for idx, item in enumerate(issues, start=1):
        topic = _safe_str(item.get("topic")) or f"议题 #{idx}"
        trigger = _safe_str(item.get("trigger")) or "议题现状痛点研讨与目标对齐。"
        full_accord = _safe_str(item.get("accord")) or "按会议共识推进执行。"

        md_lines.append(f"### {idx}. {topic}")

        # 1. 决策背景
        md_lines.append("- **决策背景**：")
        md_lines.append(f"  - {_single_sentence(trigger)}")

        # 2. 讨论要点（弹性输出，多项独立成点）
        key_quote = _safe_str(item.get("key_quote"))
        pro = item.get("pro_side") or {}
        con = item.get("con_side") or {}
        pro_stance = _safe_str(pro.get("stance"))
        con_stance = _safe_str(con.get("stance"))
        pro_speakers = "、".join(pro.get("speakers") or [])
        con_speakers = "、".join(con.get("speakers") or [])

        disc_points: list[str] = []
        if pro_stance:
            p_label = f"{pro_speakers}主张{pro_stance}" if pro_speakers else f"主张推进：{pro_stance}"
            disc_points.append(p_label)
        if con_stance and con_stance != pro_stance:
            c_label = f"{con_speakers}关注{con_stance}" if con_speakers else f"重点考量：{con_stance}"
            disc_points.append(c_label)
        if key_quote and not disc_points:
            disc_points.append(f"现场定调：“{key_quote}”")

        if disc_points:
            md_lines.append("- **讨论要点**：")
            for pt in disc_points:
                md_lines.append(f"  - {_single_sentence(pt)}")

        # 3. 得失权衡（弹性输出，收益与代价独立成点）
        tradeoff = item.get("trade_off") or {}
        gain = _safe_str(tradeoff.get("gain"))
        sacrifice = _safe_str(tradeoff.get("sacrifice"))
        gain = re.sub(r"^[▲▼\s\-\:：]+", "", gain).strip()
        sacrifice = re.sub(r"^[▲▼\s\-\:：]+", "", sacrifice).strip()

        trade_points: list[str] = []
        if gain and "无" not in gain:
            trade_points.append(f"收益：{_single_sentence(gain)}")
        if sacrifice and "无" not in sacrifice:
            trade_points.append(f"代价：{_single_sentence(sacrifice)}")

        if trade_points:
            md_lines.append("- **得失权衡**：")
            for pt in trade_points:
                md_lines.append(f"  - {pt}")

        # 4. 最终决议（压轴呈现完整落地决议）
        md_lines.append("- **最终决议**：")
        md_lines.append(f"  - {_single_sentence(full_accord)}")

        md_lines.append("")

    return "\n".join(md_lines).strip() + "\n"


def _match_group_heading(line: str) -> tuple[str | None, str]:
    """识别行是否为四组之一的标题行，返回 (组名, 行内剩余文本)。
    支持 - **决策背景**：、决策背景：、**决策背景**：、#### 决策背景、- 决策背景： 等全部自然产出形态。
    """
    clean = line.strip()
    # 先剥离行首的 Markdown 标记：如 -、*、#、数字序号
    core = re.sub(r"^[-*•#\s\d\.\(\)（）]+", "", clean).strip()
    # 剥除可能包裹的加粗或括号，如 **决策背景** 或 【决策背景】
    core = re.sub(r"^[\*\[【]+", "", core).strip()

    group_keywords = [
        ("决策背景", "background"),
        ("讨论要点", "discussion"),
        ("研讨要点", "discussion"),
        ("得失权衡", "tradeoff"),
        ("权衡取舍", "tradeoff"),
        ("最终决议", "accord"),
    ]
    for key, group_name in group_keywords:
        if core.startswith(key):
            rest = core[len(key):].strip()
            # 剥除可能残留的收尾符号，如 **、】、]、：、:
            rest = re.sub(r"^[\*\]】]+", "", rest).strip()
            rest = re.sub(r"^[：:\s]+", "", rest).strip()
            return group_name, rest
    return None, ""


def parse_consensus_decision_markdown(md: str) -> dict[str, Any]:
    """从 Markdown 文本解析出决策总览与决策细节结构化数据。
    同时支持子列表（  - ）、单行内联、未加粗文本小标题以及历史格式。
    """
    cleaned_md = _remove_emoji(md)
    lines = cleaned_md.splitlines()

    title = "共识决策"
    for line in lines:
        m_title = re.match(r"^#\s+(.+)$", line)
        if m_title:
            title = m_title.group(1).strip()
            break

    # 解析表格（决策总览）
    overview_items: list[dict[str, str]] = []
    in_table = False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("|") and s.endswith("|"):
            parts = [p.strip() for p in s[1:-1].split("|")]
            if len(parts) >= 3:
                col0, col1, col2 = parts[0], parts[1], parts[2]
                if "议题" in col0 or "---" in col0 or ":---" in col0:
                    in_table = True
                    continue
                if in_table:
                    clean_topic = re.sub(r"^\*+|\*+$", "", col0).strip()
                    clean_grade, _ = _normalize_grade(col1)
                    clean_brief_accord = col2.strip()
                    overview_items.append({
                        "topic": clean_topic,
                        "grade": clean_grade,
                        "brief_accord": clean_brief_accord,
                    })
        elif in_table and not s.startswith("|"):
            in_table = False

    # 解析细节条目（决策细节）
    issues: list[dict[str, Any]] = []
    detail_blocks = re.split(r"\n(?=###\s+)", cleaned_md)

    for block in detail_blocks:
        b_lines = block.strip().splitlines()
        if not b_lines or not b_lines[0].startswith("###"):
            continue
        first_line = b_lines[0].replace("###", "").strip()
        # 去除序号：1. 网关架构自研 -> 网关架构自研
        topic_match = re.search(r"^(?:ISS-\d+\s*[·:]\s*|\d+[.、]\s*)(.+)$", first_line)
        topic_name = topic_match.group(1).strip() if topic_match else first_line

        bg_items: list[str] = []
        disc_items: list[str] = []
        trade_items: list[str] = []
        accord_items: list[str] = []
        cur_group: str | None = None

        for b_line in b_lines[1:]:
            bl = b_line.strip()
            if not bl:
                continue

            # 组头识别（兼容加粗、未加粗、列表符、标题符等多种自然变体）
            group_name, inline_text = _match_group_heading(bl)
            if group_name is not None:
                cur_group = group_name
                if inline_text:
                    if cur_group == "background":
                        bg_items.append(inline_text)
                    elif cur_group == "discussion":
                        disc_items.append(inline_text)
                    elif cur_group == "tradeoff":
                        trade_items.append(inline_text)
                    elif cur_group == "accord":
                        accord_items.append(inline_text)
                continue

            # 子列表或正文行捕获
            m_sub = re.search(r"^[-*•]\s+(.*)$", bl)
            sub_content = m_sub.group(1).strip() if m_sub else bl

            if cur_group == "background":
                bg_items.append(sub_content)
            elif cur_group == "discussion":
                disc_items.append(sub_content)
            elif cur_group == "tradeoff":
                trade_items.append(sub_content)
            elif cur_group == "accord":
                accord_items.append(sub_content)

        # 匹配对应总览中的成色与极简决议
        matched_grade = "一致赞成"
        brief_accord = ""
        for ov in overview_items:
            if ov["topic"] in topic_name or topic_name in ov["topic"]:
                matched_grade = ov["grade"]
                brief_accord = ov.get("brief_accord", "")
                break

        full_accord = " ".join(accord_items).strip() if accord_items else brief_accord

        issues.append({
            "topic": topic_name,
            "grade": matched_grade,
            "brief_accord": brief_accord,
            "accord": full_accord,
            "accord_items": accord_items,
            "background_items": bg_items,
            "background": " ".join(bg_items).strip(),
            "tradeoff_items": trade_items,
            "tradeoff": "；".join(trade_items).strip(),
            "discussion_items": disc_items,
            "discussion": "；".join(disc_items).strip(),
        })

    # 若未成功切分出细节块，但有总览表格，按总览表格兜底生成基础细节
    if not issues and overview_items:
        for ov in overview_items:
            issues.append({
                "topic": ov["topic"],
                "grade": ov["grade"],
                "brief_accord": ov.get("brief_accord", ""),
                "accord": ov.get("brief_accord", ""),
                "accord_items": [ov.get("brief_accord", "")],
                "background_items": [],
                "background": "",
                "tradeoff_items": [],
                "tradeoff": "",
                "discussion_items": [],
                "discussion": "",
            })

    return {
        "title": title,
        "overview": overview_items,
        "issues": issues,
    }


def _custom_decision_css() -> str:
    """企业级高管决策备忘录排版样式（极简现代、专业内敛、自适应）。"""
    return """
    /* ── 共识决策现代高管备忘录排版 ── */
    .cd-section-title {
      font-size: 1.15rem;
      font-weight: 700;
      color: #0f172a;
      margin: 28px 0 14px;
      padding-bottom: 8px;
      border-bottom: 1.5px solid #e2e8f0;
    }
    .cd-table-wrap {
      width: 100%;
      overflow-x: auto;
      margin-bottom: 28px;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
    }
    .cd-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      line-height: 1.6;
    }
    .cd-table th {
      background: #f8fafc;
      color: #334155;
      font-weight: 600;
      text-align: left;
      padding: 12px 16px;
      border-bottom: 1px solid #e2e8f0;
    }
    .cd-table td {
      padding: 12px 16px;
      border-bottom: 1px solid #f1f5f9;
      vertical-align: middle;
      color: #1e293b;
    }
    .cd-table tr:last-child td {
      border-bottom: none;
    }
    .cd-table tr:hover td {
      background: #f8fafc;
    }

    /* 状态微胶囊 (Status Pills) - 零 Emoji，内敛专业 */
    .cd-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 10px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      line-height: 1.4;
      white-space: nowrap;
    }
    .cd-pill-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    /* 一致赞成：深绿沉稳胶囊 */
    .cd-pill-hard {
      background: #ecfdf5;
      color: #065f46;
      border: 1px solid #a7f3d0;
    }
    .cd-pill-hard .cd-pill-dot {
      background: #10b981;
    }
    /* 附带前提：暖琥珀胶囊 */
    .cd-pill-conditional {
      background: #fffbeb;
      color: #92400e;
      border: 1px solid #fde68a;
    }
    .cd-pill-conditional .cd-pill-dot {
      background: #f59e0b;
    }
    /* 争执未决：玫瑰砖红胶囊 */
    .cd-pill-disagreement {
      background: #fff1f2;
      color: #9f1239;
      border: 1px solid #fecdd3;
    }
    .cd-pill-disagreement .cd-pill-dot {
      background: #f43f5e;
    }

    /* ── 逐项决策细节卡片 ── */
    .cd-details-wrap {
      display: flex;
      flex-direction: column;
      gap: 16px;
      margin-bottom: 32px;
    }
    .cd-card {
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      background: #ffffff;
      padding: 18px 20px;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
      transition: border-color 0.15s ease;
    }
    .cd-card:hover {
      border-color: #cbd5e1;
    }
    .cd-card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
      padding-bottom: 10px;
      border-bottom: 1px solid #f1f5f9;
    }
    .cd-card-title-wrap {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .cd-card-num {
      font-size: 13px;
      font-weight: 700;
      color: #64748b;
      background: #f1f5f9;
      padding: 2px 8px;
      border-radius: 4px;
    }
    .cd-card-title {
      font-size: 15px;
      font-weight: 700;
      color: #0f172a;
    }
    .cd-card-body {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .cd-row {
      display: flex;
      font-size: 14px;
      line-height: 1.6;
    }
    .cd-label {
      font-weight: 600;
      color: #475569;
      flex-shrink: 0;
      width: 84px;
    }
    .cd-val {
      color: #1e293b;
      flex: 1;
    }
    .cd-val-list {
      flex: 1;
    }
    .cd-val-list ul {
      margin: 0;
      padding-left: 18px;
      list-style-type: disc;
    }
    .cd-val-list li {
      margin-bottom: 4px;
      line-height: 1.5;
      color: #1e293b;
    }
    .cd-val-list li:last-child {
      margin-bottom: 0;
    }
    /* 最终决议压轴高亮卡槽 */
    .cd-row-accord {
      background: #f8fafc;
      padding: 10px 14px;
      border-radius: 6px;
      border-left: 3px solid #3b82f6;
      margin-top: 4px;
    }
    .cd-row-accord .cd-label {
      color: #1d4ed8;
      font-weight: 700;
    }
    .cd-row-accord .cd-val {
      font-weight: 500;
      color: #0f172a;
    }
    @media (max-width: 640px) {
      .cd-row {
        flex-direction: column;
        gap: 2px;
      }
      .cd-label {
        width: auto;
      }
    }
    """


def render_consensus_decision_html(
    title: str,
    text: str,
    data: dict[str, Any] | None = None,
) -> str:
    """渲染共识决策为现代高管备忘录 HTML（两栏结构、状态微胶囊、自适应卡片、决议压轴）。"""
    parsed = parse_consensus_decision_markdown(text) if (text and text.strip()) else {}
    doc_title = _safe_str(title) or parsed.get("title") or "共识决策"
    if not any(doc_title.endswith(s) for s in ("决策", "共识", "决议", "报告")):
        doc_title = f"{doc_title} · 共识决策"

    issues = parsed.get("issues") or []

    # 兜底：若解析无议题但 data 存在 draft/issues
    if not issues and data:
        draft = data.get("draft") or data
        raw_issues = draft.get("issues") or []
        for it in raw_issues:
            grade_key = _safe_str(it.get("consensus_grade"))
            grade_label, _ = _normalize_grade(grade_key)
            trigger = _safe_str(it.get("trigger"))
            full_accord = _safe_str(it.get("accord"))
            brief_accord = _brief_accord(full_accord)

            tradeoff = it.get("trade_off") or {}
            gain = _safe_str(tradeoff.get("gain"))
            sacrifice = _safe_str(tradeoff.get("sacrifice"))
            td_items: list[str] = []
            if gain and "无" not in gain:
                td_items.append(f"收益：{gain}")
            if sacrifice and "无" not in sacrifice:
                td_items.append(f"代价：{sacrifice}")

            disc_items: list[str] = []
            quote = _safe_str(it.get("key_quote"))
            if quote:
                disc_items.append(f"现场定调：“{quote}”")

            issues.append({
                "topic": _safe_str(it.get("topic")),
                "grade": grade_label,
                "brief_accord": brief_accord,
                "accord": full_accord,
                "background": trigger,
                "tradeoff_items": td_items,
                "tradeoff": "；".join(td_items),
                "discussion_items": disc_items,
                "discussion": "；".join(disc_items),
            })

    # 构建决策总览表格行（首屏速览，展示 brief_accord）
    table_rows_html = []
    for it in issues:
        topic_esc = escape(it.get("topic") or "核心议题")
        grade_text, css_suffix = _normalize_grade(it.get("grade") or "")
        short_accord = it.get("brief_accord") or _brief_accord(it.get("accord") or "")
        accord_esc = escape(short_accord)

        pill_html = (
            f'<span class="cd-pill cd-pill-{css_suffix}">'
            f'<span class="cd-pill-dot"></span>{grade_text}</span>'
        )
        table_rows_html.append(
            f'<tr>\n'
            f'  <td><strong>{topic_esc}</strong></td>\n'
            f'  <td style="text-align: center;">{pill_html}</td>\n'
            f'  <td>{accord_esc}</td>\n'
            f'</tr>'
        )

    if not table_rows_html:
        table_rows_content = (
            '<tr><td colspan="3" style="text-align:center; color:#94a3b8; padding: 24px;">'
            '本次会议未识别出重大共识分歧或决策事项</td></tr>'
        )
    else:
        table_rows_content = "\n".join(table_rows_html)

    # 构建决策细节卡片（按 背景 ➔ 讨论要点 ➔ 得失权衡 ➔ 最终决议 顺序排版）
    cards_html = []
    for idx, it in enumerate(issues, start=1):
        topic_esc = escape(it.get("topic") or f"议题 #{idx}")
        grade_text, css_suffix = _normalize_grade(it.get("grade") or "")
        pill_html = (
            f'<span class="cd-pill cd-pill-{css_suffix}">'
            f'<span class="cd-pill-dot"></span>{grade_text}</span>'
        )

        rows = []

        # 1. 决策背景
        bg_items = it.get("background_items") or []
        if bg_items:
            if len(bg_items) > 1:
                lis = "".join(f"<li>{escape(pt)}</li>" for pt in bg_items)
                rows.append(
                    f'<div class="cd-row">'
                    f'<span class="cd-label">决策背景</span>'
                    f'<div class="cd-val-list"><ul>{lis}</ul></div>'
                    f'</div>'
                )
            else:
                rows.append(
                    f'<div class="cd-row">'
                    f'<span class="cd-label">决策背景</span>'
                    f'<span class="cd-val">{escape(bg_items[0])}</span>'
                    f'</div>'
                )
        elif it.get("background"):
            rows.append(
                f'<div class="cd-row">'
                f'<span class="cd-label">决策背景</span>'
                f'<span class="cd-val">{escape(it["background"])}</span>'
                f'</div>'
            )

        # 2. 讨论要点
        disc_items = it.get("discussion_items") or []
        if disc_items:
            lis = "".join(f"<li>{escape(pt)}</li>" for pt in disc_items)
            rows.append(
                f'<div class="cd-row">'
                f'<span class="cd-label">讨论要点</span>'
                f'<div class="cd-val-list"><ul>{lis}</ul></div>'
                f'</div>'
            )
        elif it.get("discussion"):
            rows.append(
                f'<div class="cd-row">'
                f'<span class="cd-label">讨论要点</span>'
                f'<span class="cd-val">{escape(it["discussion"])}</span>'
                f'</div>'
            )

        # 3. 得失权衡
        td_items = it.get("tradeoff_items") or []
        if td_items:
            lis = "".join(f"<li>{escape(pt)}</li>" for pt in td_items)
            rows.append(
                f'<div class="cd-row">'
                f'<span class="cd-label">得失权衡</span>'
                f'<div class="cd-val-list"><ul>{lis}</ul></div>'
                f'</div>'
            )
        elif it.get("tradeoff"):
            rows.append(
                f'<div class="cd-row">'
                f'<span class="cd-label">得失权衡</span>'
                f'<span class="cd-val">{escape(it["tradeoff"])}</span>'
                f'</div>'
            )

        # 4. 最终决议（压轴高亮呈现）
        accord_items = it.get("accord_items") or []
        if accord_items:
            if len(accord_items) > 1:
                lis = "".join(f"<li>{escape(pt)}</li>" for pt in accord_items)
                rows.append(
                    f'<div class="cd-row cd-row-accord">'
                    f'<span class="cd-label">最终决议</span>'
                    f'<div class="cd-val-list"><ul>{lis}</ul></div>'
                    f'</div>'
                )
            else:
                rows.append(
                    f'<div class="cd-row cd-row-accord">'
                    f'<span class="cd-label">最终决议</span>'
                    f'<span class="cd-val">{escape(accord_items[0])}</span>'
                    f'</div>'
                )
        else:
            accord = it.get("accord") or it.get("brief_accord") or ""
            if accord:
                rows.append(
                    f'<div class="cd-row cd-row-accord">'
                    f'<span class="cd-label">最终决议</span>'
                    f'<span class="cd-val">{escape(accord)}</span>'
                    f'</div>'
                )

        body_content = "\n".join(rows) if rows else '<div class="cd-val" style="color:#94a3b8;">常规流程平稳推进</div>'

        card = f"""
        <div class="cd-card">
          <div class="cd-card-header">
            <div class="cd-card-title-wrap">
              <span class="cd-card-num">{idx}</span>
              <span class="cd-card-title">{topic_esc}</span>
            </div>
            {pill_html}
          </div>
          <div class="cd-card-body">
            {body_content}
          </div>
        </div>
        """
        cards_html.append(card.strip())

    if not cards_html:
        cards_content = (
            '<div style="text-align:center; color:#94a3b8; padding: 32px; '
            'background:#f8fafc; border-radius:8px; border:1px dashed #e2e8f0;">'
            '本次会议未识别出重大分歧或妥协决议事项，各项议题均以常规流程平稳推进。</div>'
        )
    else:
        cards_content = "\n".join(cards_html)

    doc_title_esc = escape(doc_title)
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{doc_title_esc}</title>
  <style>
{_latex_paper_css()}
{_custom_decision_css()}
  </style>
</head>
<body>
  <main class="page">
    <div class="ck-doc">
      <header class="ck-doc-header">
        <h1>{doc_title_esc}</h1>
        <div class="ck-doc-meta">关键议题决策总览与共识分析</div>
      </header>
      <div class="ck-doc-content">
        <h2 class="cd-section-title">决策总览</h2>
        <div class="cd-table-wrap">
          <table class="cd-table">
            <thead>
              <tr>
                <th style="width: 28%;">议题</th>
                <th style="width: 18%; text-align: center;">共识成色</th>
                <th style="width: 54%;">最终决议</th>
              </tr>
            </thead>
            <tbody>
              {table_rows_content}
            </tbody>
          </table>
        </div>

        <h2 class="cd-section-title">决策细节</h2>
        <div class="cd-details-wrap">
          {cards_content}
        </div>
      </div>
    </div>
  </main>
</body>
</html>
"""
    return html


__all__ = [
    "ARCHETYPE_MAP",
    "GRADE_MAP",
    "format_consensus_decision_markdown",
    "parse_consensus_decision_markdown",
    "render_consensus_decision_html",
]
