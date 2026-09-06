"""Consensus Spectrum & Causal Decision export module.

Generates:
1. Professional Markdown Report (McKinsey/Bain decision memo style)
2. Interactive Dialectic Decision Spine HTML Report (100% inheriting _latex_paper_css)
"""
from __future__ import annotations

from html import escape
import re
from typing import Any

from tools.meeting_memory.render import _latex_paper_css


GRADE_MAP = {
    "hard_alignment": ("坚实质朴共识", "Hard Alignment", "grade-hard", "dot-hard"),
    "conditional_concession": ("带保留条件的妥协", "Conditional Concession", "grade-conditional", "dot-conditional"),
    "unresolved_concern": ("未被采纳的关切", "Unresolved Concern", "grade-unresolved", "dot-unresolved"),
    "active_disagreement": ("悬而未决的暗礁", "Active Disagreement", "grade-disagreement", "dot-disagreement"),
}

ARCHETYPE_MAP = {
    "data_driven": "数据迫降型 · Data-Driven",
    "authority_fiat": "权威定夺型 · Authority Fiat",
    "quid_pro_quo": "利益妥协交换型 · Quid Pro Quo",
    "consensus": "自然充分共识型 · Consensus",
}


def _safe_str(val: Any) -> str:
    if val is None or val is False:
        return ""
    return str(val).strip()


def _md_to_html_inline(text: str) -> str:
    """把内联 Markdown 简单安全转为 HTML 标签（如 **加粗** 转 <strong>）。"""
    if not text:
        return ""
    escaped = escape(text, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped


def _get_speaker_initial(name_or_list: Any) -> str:
    """提取参会人姓名缩写/姓氏用于中轴线头像圆点展示。"""
    if isinstance(name_or_list, (list, tuple)):
        names = [str(n).strip() for n in name_or_list if str(n).strip()]
    else:
        raw = str(name_or_list or "").strip()
        names = [s.strip() for s in re.split(r"[、,，/]", raw) if s.strip()]

    if not names:
        return "论"

    if len(names) == 1:
        single = names[0]
        if re.search(r"[\u4e00-\u9fff]", single):
            return single[0]
        return single[:2].upper()

    initials = []
    for n in names[:2]:
        if re.search(r"[\u4e00-\u9fff]", n):
            initials.append(n[0])
        else:
            initials.append(n[:1].upper())
    return "·".join(initials)


def parse_consensus_decision_markdown(md: str) -> dict[str, Any]:
    """从 Markdown 文本容错解析出结构化草稿（确保在仅有 md 文本时依然能渲染出完整的脊柱流）。"""
    summary: dict[str, Any] = {}
    headline_m = re.search(r">\s*(?:🧭\s*)?【执行健康度总评】\s*\\?\n>\s*([^\n]+(?:\n>[^\n]+)*)", md)
    if headline_m:
        summary["health_headline"] = headline_m.group(1).replace("\n>", " ").strip()

    issues: list[dict[str, Any]] = []
    blocks = re.split(r"\n(?=###\s*议题\s*)", md)
    for b in blocks[1:]:
        lines = b.strip().splitlines()
        first_line = lines[0]
        m_head = re.search(r"###\s*议题\s*([A-Za-z0-9_-]+)\s*[·:]\s*(.+)", first_line)
        issue_id = m_head.group(1).strip() if m_head else "ISS-XX"
        topic = m_head.group(2).strip() if m_head else first_line.replace("###", "").strip()

        trigger = ""
        m_trig = re.search(r"-\s*\*\*议题起因\s*\(Trigger\)\*\*[：:]\s*([^\n]+)", b)
        if m_trig:
            trigger = m_trig.group(1).strip()

        grade = "hard_alignment"
        if "带保留妥协" in b or "conditional_concession" in b:
            grade = "conditional_concession"
        elif "未被采纳" in b or "unresolved_concern" in b:
            grade = "unresolved_concern"
        elif "悬而未决" in b or "active_disagreement" in b:
            grade = "active_disagreement"

        archetype = "consensus"
        if "权威裁定" in b or "authority_fiat" in b:
            archetype = "authority_fiat"
        elif "数据迫降" in b or "data_driven" in b:
            archetype = "data_driven"
        elif "妥协交换" in b or "quid_pro_quo" in b:
            archetype = "quid_pro_quo"

        # Pro side
        pro_speakers: list[str] = []
        pro_stance = ""
        pro_args: list[str] = []
        pro_quote = ""
        m_pro = re.search(r"-\s*\*\*【主张方】\s*([^：:\*]+)\*\*[：:]\s*\n\s*-\s*\*\*核心立场\*\*[：:]\s*([^\n]+)", b)
        if m_pro:
            pro_speakers = [s.strip() for s in m_pro.group(1).split("、") if s.strip()]
            pro_stance = m_pro.group(2).strip()

        m_pro_block = re.search(r"【主张方】[\s\S]*?(?=【质询方】|####\s*2\.)", b)
        if m_pro_block:
            pro_text = m_pro_block.group(0)
            in_args = False
            for line in pro_text.splitlines():
                ls = line.strip()
                if any(k in ls for k in ("主要论据", "支撑论据", "核心论据")):
                    in_args = True
                    continue
                if in_args and (ls.startswith("-") or ls.startswith("*")):
                    if any(k in ls for k in ("原文引句", "核心立场")):
                        in_args = False
                    else:
                        clean_arg = re.sub(r"^[-*]\s*", "", ls).strip()
                        if clean_arg:
                            pro_args.append(clean_arg)
            m_pq = re.search(r"-\s*\*\*原文引句\*\*[：:]\s*[“\"]([^”\"]+)[”\"]", pro_text)
            if m_pq:
                pro_quote = m_pq.group(1).strip()

        # Con side
        con_speakers: list[str] = []
        con_stance = ""
        con_args: list[str] = []
        con_quote = ""
        m_con = re.search(r"-\s*\*\*【质询方】\s*([^：:\*]+)\*\*[：:]\s*\n\s*-\s*\*\*核心立场\*\*[：:]\s*([^\n]+)", b)
        if m_con:
            con_speakers = [s.strip() for s in m_con.group(1).split("、") if s.strip()]
            con_stance = m_con.group(2).strip()

        m_con_block = re.search(r"【质询方】[\s\S]*?(?=####\s*2\.)", b)
        if m_con_block:
            con_text = m_con_block.group(0)
            in_args = False
            for line in con_text.splitlines():
                ls = line.strip()
                if any(k in ls for k in ("质询理由", "主要论据", "隐忧", "核心关切")):
                    in_args = True
                    continue
                if in_args and (ls.startswith("-") or ls.startswith("*")):
                    if any(k in ls for k in ("原文引句", "核心立场")):
                        in_args = False
                    else:
                        clean_arg = re.sub(r"^[-*]\s*", "", ls).strip()
                        if clean_arg:
                            con_args.append(clean_arg)
            m_cq = re.search(r"-\s*\*\*原文引句\*\*[：:]\s*[“\"]([^”\"]+)[”\"]", con_text)
            if m_cq:
                con_quote = m_cq.group(1).strip()

        # Accord
        accord = ""
        m_acc = re.search(r"####\s*2\.\s*破局妥协公约\s*\(Accord\)[\s\S]*?>\s*([^\n]+(?:\n>[^\n]+)*)", b)
        if m_acc:
            accord = m_acc.group(1).replace("\n>", " ").strip()

        # Caveat
        caveat = ""
        m_cav = re.search(r"####\s*3\.\s*(?:⚠️\s*)?附加保留条件与防范预警\s*\(Caveat\)[\s\S]*?>\s*([^\n]+(?:\n>[^\n]+)*)", b)
        if m_cav:
            caveat = m_cav.group(1).replace("\n>", " ").strip()
            if caveat.startswith("**保留前提与预警**："):
                caveat = caveat[len("**保留前提与预警**："):].strip()

        # Trade off
        gain = ""
        sacrifice = ""
        m_gain = re.search(r"-\s*\*\*(?:▲\s*)?换取的核心价值\s*\(Gain\)\*\*[：:]\s*([^\n]+)", b)
        m_sac = re.search(r"-\s*\*\*(?:▼\s*)?承受的主动代价\s*\(Sacrifice\)\*\*[：:]\s*([^\n]+)", b)
        if m_gain:
            gain = m_gain.group(1).strip()
        if m_sac:
            sacrifice = m_sac.group(1).strip()

        # Rollback
        rollback = ""
        m_roll = re.search(r"####\s*5\.\s*翻盘回滚红线\s*\(Rollback Trigger\)[\s\S]*?>\s*([^\n]+(?:\n>[^\n]+)*)", b)
        if m_roll:
            rollback = m_roll.group(1).replace("\n>", " ").strip()

        # Key quote
        key_quote = ""
        m_kq = re.search(r"-\s*\*\*现场关键(?:定调)?引句\*\*[：:]\s*[“\"]([^”\"]+)[”\"]", b)
        if m_kq:
            key_quote = m_kq.group(1).strip()

        issues.append({
            "issue_id": issue_id,
            "topic": topic,
            "trigger": trigger,
            "consensus_grade": grade,
            "archetype": archetype,
            "pro_side": {
                "speakers": pro_speakers,
                "stance": pro_stance,
                "arguments": pro_args,
                "quote": pro_quote,
            },
            "con_side": {
                "speakers": con_speakers,
                "stance": con_stance,
                "arguments": con_args,
                "quote": con_quote,
            },
            "accord": accord,
            "caveat": caveat,
            "trade_off": {
                "gain": gain,
                "sacrifice": sacrifice,
            },
            "rollback_trigger": rollback,
            "key_quote": key_quote,
        })
    return {"summary": summary, "issues": issues}


def format_consensus_decision_markdown(draft: dict[str, Any], title: str = "共识成色与因果决策推演报告") -> str:
    """把结构化草稿格式化为麦肯锡/高盛决策备忘录质感的高级 Markdown 文档。"""
    issues = draft.get("issues") or []
    summary = draft.get("summary") or {}
    health_headline = _safe_str(summary.get("health_headline"))

    total_issues = len(issues)
    hard_count = sum(1 for it in issues if it.get("consensus_grade") == "hard_alignment")
    conditional_count = sum(1 for it in issues if it.get("consensus_grade") == "conditional_concession")
    unresolved_count = sum(1 for it in issues if it.get("consensus_grade") in ("unresolved_concern", "active_disagreement"))

    all_speakers: list[str] = []
    for it in issues:
        pro = it.get("pro_side") or {}
        con = it.get("con_side") or {}
        for spk in (pro.get("speakers") or []):
            if spk and spk not in all_speakers:
                all_speakers.append(spk)
        for spk in (con.get("speakers") or []):
            if spk and spk not in all_speakers:
                all_speakers.append(spk)

    speaker_text = "、".join(all_speakers) if all_speakers else "全体参会人员"

    md_lines: list[str] = []
    display_title = title if title else "共识成色与因果决策推演报告"
    if not display_title.endswith("报告") and not display_title.endswith("推演"):
        display_title = f"{display_title} · 共识成色与因果决策推演报告"

    md_lines.append(f"# {display_title}\n")
    md_lines.append(f"> **研讨议题数**：{total_issues} 项重大深水区决议 | **共识分布**：{hard_count} 项坚实共识 · {conditional_count} 项带保留妥协 · {unresolved_count} 项未决暗礁  ")
    md_lines.append(f"> **核心研讨成员**：{speaker_text}\n")
    md_lines.append("---\n")

    md_lines.append("## 第一部分：全局共识罗盘与健康度总览 (Consensus Compass)\n")
    md_lines.append("| 统计指标 | 数量 | 战略诊断说明 |")
    md_lines.append("| :--- | :---: | :--- |")
    md_lines.append(f"| **深度研讨议题** | **{total_issues} 项** | 穿透研讨深水区决策 |")
    md_lines.append(f"| **坚实质朴共识** | **{hard_count} 项** | 各方理念自然闭环，无附加免责条件 |")
    md_lines.append(f"| **带保留条件的妥协** | **{conditional_count} 项** | **重点关注**：表面达成一致，但附带严苛前提或免责声明 |")
    md_lines.append(f"| **悬而未决分歧/暗礁** | **{unresolved_count} 项** | 未决关切或残留争议，需持续跟进防范 |")
    md_lines.append("")

    headline_text = health_headline if health_headline else ("本次会议共识整体收敛，执行风险可控。" if conditional_count == 0 else "需重点盯防带保留条件的议题，防范后续执行脱轨与翻盘风险。")
    md_lines.append(f"> **【执行健康度总评】**  \n> {headline_text}\n")
    md_lines.append("---\n")

    md_lines.append("## 第二部分：议题辩证推演与得失天平 (The Decision Arena)\n")

    if not issues:
        md_lines.append("本次会议未识别出重大分歧或妥协决议事项，各项议题均以常规流程平稳推进。\n")
        return "\n".join(md_lines)

    for idx, item in enumerate(issues, start=1):
        issue_id = _safe_str(item.get("issue_id")) or f"ISS-{idx:02d}"
        topic = _safe_str(item.get("topic")) or f"议题 #{idx}"
        trigger = _safe_str(item.get("trigger")) or "议题现状痛点研讨"

        grade_key = _safe_str(item.get("consensus_grade"))
        grade_label = GRADE_MAP.get(grade_key, (grade_key or "自然充分共识", "", ""))[0]

        archetype_key = _safe_str(item.get("archetype"))
        archetype_label = ARCHETYPE_MAP.get(archetype_key, archetype_key or "自然充分共识型")

        md_lines.append(f"### 议题 {issue_id} · {topic}\n")
        md_lines.append(f"- **议题起因 (Trigger)**：{trigger}")
        md_lines.append(f"- **共识成色定级**：`[{grade_label}]`")
        md_lines.append(f"- **裁决达成形态**：`[{archetype_label}]`\n")

        # 辩证交锋
        pro = item.get("pro_side") or {}
        con = item.get("con_side") or {}
        pro_speakers = "、".join(pro.get("speakers") or []) or "主张方"
        con_speakers = "、".join(con.get("speakers") or []) or "质询方"
        pro_stance = _safe_str(pro.get("stance")) or "推进实施"
        con_stance = _safe_str(con.get("stance")) or "审慎评估"
        pro_quote = _safe_str(pro.get("quote"))
        con_quote = _safe_str(con.get("quote"))

        md_lines.append("#### 1. 辩证论据交锋 (The Evidence Duel)")
        md_lines.append(f"- **[主张方] {pro_speakers}**：")
        md_lines.append(f"  - **核心立场**：{pro_stance}")
        for arg in (pro.get("arguments") or []):
            if _safe_str(arg):
                md_lines.append(f"  - **论据**：{arg}")
        if pro_quote:
            md_lines.append(f"  - **原文引句**：“{pro_quote}”")

        md_lines.append(f"- **[质询方] {con_speakers}**：")
        md_lines.append(f"  - **核心立场**：{con_stance}")
        for arg in (con.get("arguments") or []):
            if _safe_str(arg):
                md_lines.append(f"  - **质询**：{arg}")
        if con_quote:
            md_lines.append(f"  - **原文引句**：“{con_quote}”")
        md_lines.append("")

        # 破局公约
        accord = _safe_str(item.get("accord")) or "各方达成共识，按既定决议推进。"
        md_lines.append("#### 2. 破局妥协公约 (Accord)")
        md_lines.append(f"> {accord}\n")

        # 保留条件 Caveat
        caveat = _safe_str(item.get("caveat"))
        if caveat and caveat.lower() not in ("null", "none", "无", "无保留条件", "无附加保留条件"):
            md_lines.append("#### 3. 附加保留条件与防范预警 (Caveat)")
            md_lines.append(f"> **保留前提与预警**：{caveat}\n")
        else:
            md_lines.append("#### 3. 附加保留条件与防范预警 (Caveat)")
            md_lines.append("> 无附加保留条件，全员充分闭环对齐。\n")

        # 得失天平
        tradeoff = item.get("trade_off") or {}
        gain = _safe_str(tradeoff.get("gain")) or "换取业务推进确定性与执行节奏"
        sacrifice = _safe_str(tradeoff.get("sacrifice")) or "承担部分灵活性损失或过渡成本"
        gain = re.sub(r"^[▲▼\s\-\:：]+", "", gain).strip()
        sacrifice = re.sub(r"^[▲▼\s\-\:：]+", "", sacrifice).strip()
        md_lines.append("#### 4. 得失天平 (Trade-Off Balance)")
        md_lines.append(f"- **换取的核心价值 (Gain)**：{gain}")
        md_lines.append(f"- **承受的主动代价 (Sacrifice)**：{sacrifice}\n")

        # 翻盘红线
        rollback = _safe_str(item.get("rollback_trigger")) or "无明确翻盘红线，按定稿方案推进。"
        md_lines.append("#### 5. 翻盘回滚红线 (Rollback Trigger)")
        md_lines.append(f"> {rollback}\n")

        # 关键引句
        key_quote = _safe_str(item.get("key_quote"))
        if key_quote:
            md_lines.append(f"- **现场关键定调原句**：“{key_quote}”\n")

        md_lines.append("---\n")

    return "\n".join(md_lines)


def _custom_decision_css() -> str:
    """辩证因果脊柱流（The Dialectic Decision Spine）专属排版样式，极简学术高级感。"""
    return """
    html {
      scroll-behavior: smooth;
    }

    /* ── 全局共识罗盘与健康度 ── */
    .executive-compass {
      background: #ffffff;
      border: 1px solid #e4e4e7;
      border-radius: 4px;
      padding: 24px 28px;
      margin: 20px 0 32px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
    }
    .compass-score-deck {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 20px;
      padding-bottom: 20px;
      border-bottom: 1px solid #f4f4f5;
    }
    @media (max-width: 700px) {
      .compass-score-deck {
        grid-template-columns: repeat(2, 1fr);
      }
    }
    .score-card {
      display: flex;
      flex-direction: column;
    }
    .score-num {
      font-size: 2rem;
      font-weight: 700;
      font-family: "Latin Modern Roman", Georgia, serif;
      line-height: 1;
      color: #18181b;
    }
    .score-card.score-hard .score-num { color: #18181b; }
    .score-card.score-conditional .score-num { color: #27272a; }
    .score-card.score-unresolved .score-num { color: #3f3f46; }
    .score-label {
      font-size: 0.72rem;
      color: #71717a;
      margin-top: 6px;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }
    .compass-nav-rail {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      padding: 14px 0;
      border-bottom: 1px solid #f4f4f5;
    }
    .nav-rail-title {
      font-size: 0.75rem;
      font-weight: 700;
      color: #71717a;
      letter-spacing: 0.4px;
      margin-right: 4px;
    }
    .nav-rail-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      background: #fafafa;
      border: 1px solid #e4e4e7;
      border-radius: 3px;
      font-size: 0.76rem;
      color: #27272a;
      text-decoration: none;
      transition: all 0.15s ease;
    }
    .nav-rail-item:hover {
      background: #f4f4f5;
      border-color: #18181b;
      color: #18181b;
    }
    .compass-diagnosis {
      margin-top: 14px;
      font-size: 0.88rem;
      color: #3f3f46;
      line-height: 1.65;
    }
    .compass-diagnosis strong {
      color: #18181b;
    }

    /* ── 辩证因果脊柱流 (The Dialectic Decision Stream) ── */
    .stream-section {
      position: relative;
      margin: 40px 0 54px;
      padding-bottom: 24px;
      border-bottom: 1px solid #e4e4e7;
    }
    .stream-section:last-child {
      border-bottom: none;
    }
    .stream-header {
      display: flex;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 24px;
      padding-bottom: 12px;
      border-bottom: 1.5px solid #18181b;
    }
    .stream-seq {
      font-family: "Latin Modern Roman", Georgia, serif;
      font-size: 2rem;
      font-weight: 700;
      line-height: 1;
      color: #18181b;
      opacity: 0.85;
      min-width: 36px;
    }
    .stream-header-info {
      flex: 1;
    }
    .stream-meta-line {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }
    .stream-id {
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: #71717a;
      font-family: "Latin Modern Mono", Consolas, monospace;
    }
    .stream-topic {
      margin: 0;
      font-size: 1.28rem;
      font-weight: 700;
      color: #18181b;
      line-height: 1.35;
      letter-spacing: 0.2px;
    }

    /* 状态徽章 */
    .badge-capsule {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 0.72rem;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 3px;
      border: 1px solid transparent;
      letter-spacing: 0.2px;
    }
    .badge-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      display: inline-block;
    }
    .grade-hard { background: #f4f4f5; color: #18181b; border-color: #e4e4e7; }
    .dot-hard { background: #18181b; }
    .grade-conditional { background: #fafaf9; color: #44403c; border-color: #e7e5e4; }
    .dot-conditional { background: #78716c; }
    .grade-unresolved { background: #f8fafc; color: #334155; border-color: #cbd5e1; }
    .dot-unresolved { background: #64748b; }
    .grade-disagreement { background: #f4f4f5; color: #09090b; border-color: #a1a1aa; }
    .dot-disagreement { background: #09090b; }
    .badge-archetype { background: #fafafa; color: #52525b; border-color: #e4e4e7; }

    /* ── 中轴脊柱线与节点 ── */
    .stream-spine {
      position: relative;
      padding-left: 52px;
      margin-top: 18px;
    }
    /* 纵贯中轴线 */
    .stream-spine::before {
      content: "";
      position: absolute;
      top: 14px;
      bottom: 24px;
      left: 18px;
      width: 2px;
      background: #e4e4e7;
    }

    .spine-node {
      position: relative;
      margin-bottom: 24px;
    }
    .spine-node:last-child {
      margin-bottom: 0;
    }

    /* 竖线上的锚点圆圈 / 徽章 */
    .spine-marker {
      position: absolute;
      left: -52px;
      top: 2px;
      width: 38px;
      height: 38px;
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 2;
    }

    /* 节点 1：议题源起圆点 */
    .marker-origin-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: #ffffff;
      border: 2.5px solid #18181b;
      box-shadow: 0 0 0 3px #ffffff;
    }
    .origin-card {
      background: #fafaf9;
      border-left: 3px solid #18181b;
      padding: 10px 16px;
      border-radius: 2px;
    }
    .origin-eyebrow {
      font-size: 0.72rem;
      font-weight: 700;
      color: #18181b;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 3px;
    }
    .origin-narrative {
      font-size: 0.86rem;
      color: #3f3f46;
      line-height: 1.6;
    }

    /* 节点 2 & 3：发言人观点圆点与卡片 */
    .speaker-avatar-circle {
      width: 30px;
      height: 30px;
      border-radius: 50%;
      background: #ffffff;
      border: 1.5px solid #18181b;
      color: #18181b;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.8rem;
      font-weight: 700;
      font-family: "Songti SC", "SimSun", serif;
      box-shadow: 0 0 0 3px #ffffff;
    }
    .speaker-avatar-circle.avatar-con {
      border-color: #71717a;
      color: #52525b;
    }
    .stance-card {
      background: #ffffff;
      border: 1px solid #e4e4e7;
      border-radius: 3px;
      padding: 14px 18px;
    }
    .node-pro .stance-card {
      border-left: 3px solid #18181b;
    }
    .node-con .stance-card {
      border-left: 3px solid #71717a;
    }
    .stance-card-header {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;
    }
    .speaker-title-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .speaker-name-strong {
      font-size: 0.95rem;
      font-weight: 700;
      color: #18181b;
    }
    .stance-role-tag {
      font-size: 0.70rem;
      padding: 1px 6px;
      border-radius: 2px;
      font-weight: 600;
    }
    .role-pro { background: #f4f4f5; color: #18181b; border: 1px solid #e4e4e7; }
    .role-con { background: #fafafa; color: #52525b; border: 1px solid #e4e4e7; }
    .stance-thesis {
      font-size: 0.88rem;
      font-weight: 600;
      color: #18181b;
      line-height: 1.55;
      margin-bottom: 6px;
    }
    .argument-trail {
      margin: 6px 0 8px;
      padding-left: 18px;
      font-size: 0.84rem;
      color: #3f3f46;
      line-height: 1.6;
    }
    .argument-trail li {
      margin-bottom: 4px;
    }
    .verbatim-pullquote {
      position: relative;
      background: #fafaf9;
      border-left: 2px solid #a1a1aa;
      padding: 8px 12px;
      margin-top: 8px;
      font-size: 0.81rem;
      color: #52525b;
      font-style: italic;
      line-height: 1.55;
      border-radius: 0 2px 2px 0;
    }

    /* 节点 4：最终解决破局公约 (Convergence Hub) */
    .marker-seal-circle {
      width: 30px;
      height: 30px;
      border-radius: 50%;
      background: #18181b;
      border: 1.5px solid #18181b;
      color: #ffffff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.5px;
      box-shadow: 0 0 0 3px #ffffff;
    }
    .accord-resolution-dossier {
      background: #fafaf9;
      border: 1px solid #e4e4e7;
      border-left: 3.5px solid #18181b;
      border-radius: 3px;
      padding: 16px 20px;
    }
    .accord-top-eyebrow {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;
      padding-bottom: 6px;
      border-bottom: 1px solid #e4e4e7;
    }
    .accord-label-headline {
      font-size: 0.76rem;
      font-weight: 700;
      color: #18181b;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }
    .accord-archetype-tag {
      font-size: 0.72rem;
      color: #71717a;
      font-style: italic;
    }
    .accord-core-text {
      font-size: 0.90rem;
      color: #18181b;
      line-height: 1.68;
      font-weight: 500;
    }
    .ruling-quote-ribbon {
      margin-top: 10px;
      padding: 8px 12px;
      background: #ffffff;
      border: 1px solid #e4e4e7;
      border-left: 2.5px solid #18181b;
      font-size: 0.81rem;
      color: #3f3f46;
      line-height: 1.5;
    }
    .ruling-tag {
      font-weight: 700;
      color: #18181b;
      margin-right: 6px;
    }

    /* 节点 5：防线、天平与红线 */
    .marker-terminal-anchor {
      width: 10px;
      height: 10px;
      background: #71717a;
      border-radius: 2px;
      box-shadow: 0 0 0 3px #ffffff, 0 0 0 4px #e4e4e7;
    }
    .safeguards-container {
      background: #ffffff;
      border: 1px solid #e4e4e7;
      border-radius: 3px;
      padding: 14px 18px;
    }

    /* 保留条件 */
    .caveat-warning-strip {
      background: #fafaf9;
      border: 1px solid #e7e5e4;
      border-left: 3px solid #78716c;
      border-radius: 2px;
      padding: 8px 12px;
      margin-bottom: 12px;
      font-size: 0.83rem;
      color: #292524;
      line-height: 1.55;
    }
    .caveat-warning-strip strong {
      color: #1c1917;
    }
    .caveat-clean-strip {
      background: #fafaf9;
      border: 1px solid #e7e5e4;
      border-radius: 2px;
      padding: 6px 12px;
      margin-bottom: 12px;
      font-size: 0.81rem;
      color: #52525b;
    }

    /* 得失天平双拼卡 */
    .balance-scale-grid {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      gap: 12px;
      align-items: stretch;
      margin: 10px 0;
    }
    @media (max-width: 650px) {
      .balance-scale-grid {
        grid-template-columns: 1fr;
      }
      .scale-pivot-cell {
        display: none;
      }
    }
    .scale-card-gain {
      background: #fafaf9;
      border: 1px solid #e4e4e7;
      border-top: 2px solid #18181b;
      border-radius: 2px;
      padding: 10px 14px;
    }
    .scale-card-sacrifice {
      background: #fafaf9;
      border: 1px solid #e4e4e7;
      border-top: 2px solid #71717a;
      border-radius: 2px;
      padding: 10px 14px;
    }
    .scale-pivot-cell {
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.78rem;
      font-family: "Latin Modern Roman", Georgia, serif;
      font-style: italic;
      color: #a1a1aa;
      padding: 0 4px;
    }
    .scale-head-label {
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.4px;
      margin-bottom: 4px;
      text-transform: uppercase;
    }
    .scale-card-gain .scale-head-label { color: #18181b; }
    .scale-card-sacrifice .scale-head-label { color: #52525b; }
    .scale-body-text {
      font-size: 0.83rem;
      color: #3f3f46;
      line-height: 1.55;
    }

    /* 翻盘红线 */
    .rollback-tripwire-bar {
      margin-top: 10px;
      padding: 8px 12px;
      background: #fafaf9;
      border: 1px solid #e4e4e7;
      border-left: 2.5px solid #52525b;
      border-radius: 2px;
      font-size: 0.81rem;
      color: #3f3f46;
      line-height: 1.5;
    }
    .tripwire-label {
      font-weight: 700;
      color: #18181b;
      margin-right: 6px;
    }
    """


def render_consensus_decision_html(title: str, text: str, data: dict | None = None) -> str:
    """渲染共识成色与因果决策推演为中轴脊柱流（The Dialectic Decision Spine）沉浸式学术页面。"""
    draft = data if (isinstance(data, dict) and ("issues" in data or "summary" in data)) else {}
    if not draft and isinstance(data, dict):
        draft = data.get("draft") or {}
    if not draft and text:
        draft = parse_consensus_decision_markdown(text)

    issues = draft.get("issues") or []
    summary = draft.get("summary") or {}
    health_headline = _safe_str(summary.get("health_headline"))

    total_issues = len(issues)
    hard_count = sum(1 for it in issues if it.get("consensus_grade") == "hard_alignment")
    conditional_count = sum(1 for it in issues if it.get("consensus_grade") == "conditional_concession")
    unresolved_count = sum(1 for it in issues if it.get("consensus_grade") in ("unresolved_concern", "active_disagreement"))

    display_title = title if title else "共识成色与因果决策推演报告"
    doc_title = escape(display_title, quote=False)

    headline_text = health_headline if health_headline else ("本次会议共识整体收敛，执行意志明确，各项议题均形成阶段性公约。" if conditional_count == 0 else "本次会议存在关键妥协项带有明确免责前提，需重点监控后续兑现与翻盘风险。")

    # 顶部快速导航导轨
    nav_items_html = []
    for idx, it in enumerate(issues, start=1):
        issue_id = _safe_str(it.get("issue_id")) or f"ISS-{idx:02d}"
        topic = _safe_str(it.get("topic")) or f"议题 #{idx}"
        short_topic = topic[:12] + "…" if len(topic) > 12 else topic
        grade_key = _safe_str(it.get("consensus_grade"))
        grade_info = GRADE_MAP.get(grade_key, ("共识", "", "grade-hard", "dot-hard"))
        dot_cls = grade_info[3]
        nav_items_html.append(
            f'<a class="nav-rail-item" href="#stream-{issue_id}">'
            f'<span class="badge-dot {dot_cls}"></span>'
            f'<span>{issue_id} · {escape(short_topic, quote=False)}</span>'
            f'</a>'
        )
    nav_rail_html = "".join(nav_items_html) if nav_items_html else '<span style="font-size:0.78rem;color:#888;">常规平稳议题</span>'

    compass_html = f"""
    <div class="executive-compass compass-container">
      <div class="compass-score-deck">
        <div class="score-card">
          <div class="score-num">{total_issues}</div>
          <div class="score-label">深度研讨议题</div>
        </div>
        <div class="score-card score-hard">
          <div class="score-num">{hard_count}</div>
          <div class="score-label">坚实硬共识 (Zero Caveat)</div>
        </div>
        <div class="score-card score-conditional">
          <div class="score-num">{conditional_count}</div>
          <div class="score-label">带保留妥协 (高危监控)</div>
        </div>
        <div class="score-card score-unresolved">
          <div class="score-num">{unresolved_count}</div>
          <div class="score-label">未决暗礁 / 关切残留</div>
        </div>
      </div>
      <div class="compass-nav-rail">
        <span class="nav-rail-title">议题脉络导轨：</span>
        {nav_rail_html}
      </div>
      <div class="compass-diagnosis">
        <strong>战略健康度总评：</strong>{_md_to_html_inline(headline_text)}
      </div>
    </div>
    """

    # 渲染每一个议题的因果脊柱流 (Dialectic Decision Stream)
    streams_html = []
    for idx, item in enumerate(issues, start=1):
        issue_id = escape(_safe_str(item.get("issue_id")) or f"ISS-{idx:02d}", quote=False)
        topic = escape(_safe_str(item.get("topic")) or f"议题 #{idx}", quote=False)
        trigger = _md_to_html_inline(_safe_str(item.get("trigger")) or "议题现状痛点与方案博弈研讨")

        grade_key = _safe_str(item.get("consensus_grade"))
        grade_info = GRADE_MAP.get(grade_key, (grade_key or "自然充分共识", "", "grade-hard", "dot-hard"))
        grade_label = escape(grade_info[0], quote=False)
        grade_capsule_cls = grade_info[2]
        grade_dot_cls = grade_info[3]

        archetype_key = _safe_str(item.get("archetype"))
        archetype_label = escape(ARCHETYPE_MAP.get(archetype_key, archetype_key or "充分共识型"), quote=False)

        # Pro side
        pro = item.get("pro_side") or {}
        pro_speakers = pro.get("speakers") or []
        pro_speaker_text = escape("、".join(pro_speakers) or "主张方", quote=False)
        pro_initial = _get_speaker_initial(pro_speakers) if pro_speakers else "主"
        pro_stance = _md_to_html_inline(_safe_str(pro.get("stance")) or "推进方案")
        pro_quote = escape(_safe_str(pro.get("quote")), quote=False)
        pro_args = [_md_to_html_inline(_safe_str(a)) for a in (pro.get("arguments") or []) if _safe_str(a)]
        pro_args_li = "".join(f"<li>{a}</li>" for a in pro_args) if pro_args else "<li>推进既定方案落地实施</li>"
        pro_quote_html = f'<div class="verbatim-pullquote">“{pro_quote}”</div>' if pro_quote else ""

        # Con side
        con = item.get("con_side") or {}
        con_speakers = con.get("speakers") or []
        con_speaker_text = escape("、".join(con_speakers) or "质询方", quote=False)
        con_initial = _get_speaker_initial(con_speakers) if con_speakers else "审"
        con_stance = _md_to_html_inline(_safe_str(con.get("stance")) or "审慎关切")
        con_quote = escape(_safe_str(con.get("quote")), quote=False)
        con_args = [_md_to_html_inline(_safe_str(a)) for a in (con.get("arguments") or []) if _safe_str(a)]
        con_args_li = "".join(f"<li>{a}</li>" for a in con_args) if con_args else "<li>审慎评估执行风险与隐患</li>"
        con_quote_html = f'<div class="verbatim-pullquote">“{con_quote}”</div>' if con_quote else ""

        # Accord (最终解决)
        accord = _md_to_html_inline(_safe_str(item.get("accord")) or "各方达成共识，按既定决议推进。")

        # Caveat
        caveat = _safe_str(item.get("caveat"))
        if caveat and caveat.lower() not in ("null", "none", "无", "无保留条件", "无附加保留条件"):
            caveat_html = f"""
            <div class="caveat-warning-strip">
              <strong>附加保留条件与履约预警：</strong>{_md_to_html_inline(caveat)}
            </div>
            """
        else:
            caveat_html = """
            <div class="caveat-clean-strip">
              全员无附加保留条件，逻辑闭环对齐
            </div>
            """

        # Trade off
        tradeoff = item.get("trade_off") or {}
        raw_gain = re.sub(r"^[▲▼\s\-\:：]+", "", _safe_str(tradeoff.get("gain"))).strip()
        raw_sacrifice = re.sub(r"^[▲▼\s\-\:：]+", "", _safe_str(tradeoff.get("sacrifice"))).strip()
        gain = _md_to_html_inline(raw_gain or "换取业务推进确定性与执行节奏")
        sacrifice = _md_to_html_inline(raw_sacrifice or "承担部分灵活性损失或过渡成本")

        # Rollback & Key quote
        rollback = _md_to_html_inline(_safe_str(item.get("rollback_trigger")) or "无明确翻盘红线，按定稿方案推进。")
        key_quote = escape(_safe_str(item.get("key_quote")), quote=False)
        ruling_quote_html = f'<div class="ruling-quote-ribbon"><span class="ruling-tag">现场定调决议：</span>“{key_quote}”</div>' if key_quote else ""

        stream_item_html = f"""
        <section class="stream-section" id="stream-{issue_id}">
          <div class="stream-header">
            <div class="stream-seq">{idx:02d}</div>
            <div class="stream-header-info">
              <div class="stream-meta-line">
                <span class="stream-id">{issue_id}</span>
                <span class="badge-capsule {grade_capsule_cls}">
                  <span class="badge-dot {grade_dot_cls}"></span>
                  {grade_label}
                </span>
                <span class="badge-capsule badge-archetype">{archetype_label}</span>
              </div>
              <h3 class="stream-topic">{topic}</h3>
            </div>
          </div>

          <!-- 纵贯因果脊柱线 (The Dialectic Spine) -->
          <div class="stream-spine duel-grid">

            <!-- Node 1: 议题源起 -->
            <div class="spine-node node-trigger">
              <div class="spine-marker">
                <div class="marker-origin-dot" title="议题起因"></div>
              </div>
              <div class="origin-card">
                <div class="origin-eyebrow">议题源起与冲突动因 · Inception & Trigger</div>
                <div class="origin-narrative">{trigger}</div>
              </div>
            </div>

            <!-- Node 2: 主张方博弈观点 -->
            <div class="spine-node node-pro">
              <div class="spine-marker">
                <div class="speaker-avatar-circle" title="主张方: {pro_speaker_text}">{pro_initial}</div>
              </div>
              <div class="stance-card">
                <div class="stance-card-header">
                  <div class="speaker-title-wrap">
                    <span class="speaker-name-strong">{pro_speaker_text}</span>
                    <span class="stance-role-tag role-pro">主张推进 · Proponent</span>
                  </div>
                </div>
                <div class="stance-thesis">{pro_stance}</div>
                <ul class="argument-trail">
                  {pro_args_li}
                </ul>
                {pro_quote_html}
              </div>
            </div>

            <!-- Node 3: 质询方/关切观点 -->
            <div class="spine-node node-con">
              <div class="spine-marker">
                <div class="speaker-avatar-circle avatar-con" title="质询方: {con_speaker_text}">{con_initial}</div>
              </div>
              <div class="stance-card">
                <div class="stance-card-header">
                  <div class="speaker-title-wrap">
                    <span class="speaker-name-strong">{con_speaker_text}</span>
                    <span class="stance-role-tag role-con">审慎质询 · Interrogator</span>
                  </div>
                </div>
                <div class="stance-thesis">{con_stance}</div>
                <ul class="argument-trail">
                  {con_args_li}
                </ul>
                {con_quote_html}
              </div>
            </div>

            <!-- Node 4: 破局决议与终局公约 (Convergence Hub · 最终如何解决) -->
            <div class="spine-node node-accord">
              <div class="spine-marker">
                <div class="marker-seal-circle" title="破局决议公约">决</div>
              </div>
              <div class="accord-resolution-dossier">
                <div class="accord-top-eyebrow">
                  <div class="accord-label-headline">
                    破局决议与终局公约 · The Accord & Resolution
                  </div>
                  <div class="accord-archetype-tag">{archetype_label}</div>
                </div>
                <div class="accord-core-text">{accord}</div>
                {ruling_quote_html}
              </div>
            </div>

            <!-- Node 5: 履约防线、得失天平与翻盘红线 -->
            <div class="spine-node node-safeguards">
              <div class="spine-marker">
                <div class="marker-terminal-anchor" title="执行保障与红线"></div>
              </div>
              <div class="safeguards-container">
                {caveat_html}
                <div class="balance-scale-grid tradeoff-deck">
                  <div class="scale-card-gain">
                    <div class="scale-head-label">换取的核心价值 · Gain</div>
                    <div class="scale-body-text">{gain}</div>
                  </div>
                  <div class="scale-pivot-cell">VS</div>
                  <div class="scale-card-sacrifice">
                    <div class="scale-head-label">承受的主动代价 · Sacrifice</div>
                    <div class="scale-body-text">{sacrifice}</div>
                  </div>
                </div>
                <div class="rollback-tripwire-bar">
                  <span class="tripwire-label">翻盘回滚红线：</span>{rollback}
                </div>
              </div>
            </div>

          </div>
        </section>
        """
        streams_html.append(stream_item_html)

    streams_content = "\n".join(streams_html) if streams_html else "<p style='text-align:center; color:#888; padding:32px;'>本次会议未识别出重大深水区争议决议。</p>"

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{doc_title}</title>
  <style>
{_latex_paper_css()}
{_custom_decision_css()}
  </style>
</head>
<body>
  <main class="page">
    <div class="ck-doc">
      <header class="ck-doc-header">
        <h1>{doc_title}</h1>
        <div class="ck-doc-meta">麦肯锡决策备忘录规范 · 共识成色光谱 × 辩证因果脉络脊柱流</div>
      </header>
      <div class="ck-doc-content">
        {compass_html}
        <h2 style="margin: 32px 0 20px; border-bottom: 2px solid #111111; padding-bottom: 6px;">
          议题辩证推演与收敛脉络 (The Dialectic Decision Streams)
        </h2>
        {streams_content}
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
