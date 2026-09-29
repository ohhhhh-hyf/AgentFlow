"""agenda_parser.py -- 解析会前既定议程单（txt/md 表格或 OCR 文本）。

支持：
1. 标准 Markdown / ASCII 管道表格（| 编号 | 议题名称 | 时长 | 汇报人 |）
2. 文本列表（如 1. 议题名称 汇报人：XXX）
3. 会议主题 (Subject)、时间 (Time)、与会人员 (Attendees) 顶层元数据提取
4. 汇报人姓名清洗（自动剥离工号、前缀如 汇报人:、标点分割）
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("agentflow.agenda_parser")



@dataclass
class AgendaItemParsed:
    """单项既定议程解析结果。"""

    seq: str
    title: str
    presenters: list[str] = field(default_factory=list)
    raw_presenter: str = ""
    recorders: list[str] = field(default_factory=list)
    members: list[str] = field(default_factory=list)
    duration: str = ""
    time_range: str = ""
    category: str = ""


@dataclass
class AgendaMeta:
    """议程顶层元数据。"""

    theme: str = ""
    date_time: str = ""
    attendees: str = ""


@dataclass
class AgendaPlan:
    """全会议程总表。"""

    meta: AgendaMeta = field(default_factory=AgendaMeta)
    items: list[AgendaItemParsed] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta": {
                "theme": self.meta.theme,
                "date_time": self.meta.date_time,
                "attendees": self.meta.attendees,
            },
            "items": [
                {
                    "seq": it.seq,
                    "title": it.title,
                    "presenters": it.presenters,
                    "duration": it.duration,
                    "time_range": it.time_range,
                }
                for it in self.items
            ],
        }


def _log_parser_record(text: str, plan: AgendaPlan, mode: str, cols: dict | None = None) -> None:
    """落盘解析审计记录到 logs/agenda_ocr/parser_debug.log，便于线上定位 OCR 解析效果。"""
    try:
        log_dir = Path("logs/agenda_ocr")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "parser_debug.log"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            f"[{now_str}] Mode: {mode}, Total Items: {len(plan.items)}",
            f"  Meta: theme={plan.meta.theme!r}, time={plan.meta.date_time!r}, attendees={plan.meta.attendees!r}",
        ]
        if cols:
            lines.append(f"  Resolved Columns: {cols}")
        for it in plan.items:
            lines.append(
                f"  - Item [{it.seq}] {it.title} | Presenter: {it.presenters} (raw: {it.raw_presenter!r}) | Dur: {it.duration} | Time: {it.time_range} | Cat: {it.category}"
            )
        if not plan.items:
            lines.append("  [WARNING] No items parsed! Raw text preview (first 300 chars):")
            lines.append("  " + text[:300].replace("\n", "\n  "))
        lines.append("-" * 70 + "\n")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as exc:  # noqa: BLE001
        logger.debug("write parser_debug.log failed: %s", exc)


def _resolve_columns(header_cells: list[str]) -> dict[str, int]:
    """解析表头各列职责。按语义优先级判定，避免多列含「议题」导致张冠李戴。"""
    title_idx = -1
    seq_idx = -1
    pres_idx = -1
    rec_idx = -1
    mem_idx = -1
    time_idx = -1
    dur_idx = -1
    cat_idx = -1

    for idx, raw in enumerate(header_cells):
        name = raw.strip().lower()
        if not name:
            continue
        # 序号/编号
        if any(k in name for k in ("序号", "编号", "no.", "no", "seq", "项")):
            seq_idx = idx
            continue
        # 时长
        if any(k in name for k in ("时长", "duration", "用时", "预计用时", "时长(min)", "时长（分）", "时间(分)")):
            dur_idx = idx
            continue
        # 起止时间
        if (any(k in name for k in ("起止时间", "时间段", "议题时间")) or (("时间" in name or "time" in name) and dur_idx != idx)):
            time_idx = idx
            continue
        # 汇报人类别
        if any(k in name for k in ("类别", "类型", "category", "性质")):
            cat_idx = idx
            continue
        # 汇报人/主讲人
        if any(k in name for k in ("汇报人", "reporter", "主讲人", "主讲", "报告人", "分享人", "责任人", "发言人", "汇报人员", "汇报")):
            pres_idx = idx
            continue
        # 纪要人
        if any(k in name for k in ("纪要人", "recorder", "记录人", "纪要")):
            rec_idx = idx
            continue
        # 参与人/成员
        if any(k in name for k in ("参与人", "成员", "members", "attendees", "列席人", "与会人", "参会人员")):
            mem_idx = idx
            continue
        # 议题名称（优先匹配含「名称」「全称」「主题」的列）
        if any(k in name for k in ("议题名称", "topic name", "议题全称", "主题", "topic", "讨论事项", "审议事项", "汇报内容", "议题内容")):
            if not any(k in name for k in ("类型", "材料", "参与人", "成员", "人员", "category", "material", "member", "recorder", "纪要", "时长")):
                title_idx = idx
                continue
        # 兜底：含「议题」但不含类型/材料/人员/时长
        if "议题" in name and not any(k in name for k in ("类型", "材料", "参与人", "成员", "人员", "category", "material", "member", "recorder", "纪要", "时长")):
            title_idx = idx
            continue
        # 兜底：含「事项」「内容」
        if any(k in name for k in ("事项", "内容", "项目")) and not any(k in name for k in ("类型", "材料", "参与人", "成员", "人员", "category", "material", "member", "recorder", "纪要", "时长")):
            if title_idx == -1:
                title_idx = idx
                continue

    # 若未识别到独立汇报人列，尝试参与人列
    if pres_idx == -1 and mem_idx != -1 and mem_idx != title_idx:
        pres_idx = mem_idx

    cols = {
        "seq": seq_idx,
        "title": title_idx,
        "presenter": pres_idx,
        "recorder": rec_idx,
        "members": mem_idx,
        "time": time_idx,
        "duration": dur_idx,
        "category": cat_idx,
    }
    logger.info("agenda_parser: resolved table columns -> %s", cols)
    return cols


def clean_presenter_names(raw: str) -> list[str]:
    """从原始单元格中提取干净的汇报人姓名列表。

    处理诸如：
    - '汇报人: 赵鑫岳 00585440' -> ['赵鑫岳']
    - '沙彬斌; 陈啟锴' -> ['沙彬斌', '陈啟锴']
    - '陆敬怡; 林宇珂; 赖朝辉' -> ['陆敬怡', '林宇珂', '赖朝辉']
    - '汇报人: 林宇珂 00939670 陆敬怡 00841266' -> ['林宇珂', '陆敬怡']
    - '张三、李四' -> ['张三', '李四']
    """
    if not raw or not raw.strip():
        return []
    # 剥离前缀
    text = re.sub(r"^(?:汇报人|主讲人|报告人|分享人|责任人|发言人)\s*[:：]\s*", "", raw.strip(), flags=re.I)
    # 剥离 5~8 位连续数字工号
    text = re.sub(r"\b\d{5,8}\b", "", text)
    # 剔除括号及其内工号或备注，如 (委托高雄)
    text = re.sub(r"\([^)]*\)|（[^）]*）", "", text)
    # 按常见分隔符拆分（包含顿号、分号、斜杠、逗号、空格）
    names = re.split(r"[;；,/，\s、]+", text)
    valid = []
    for n in names:
        n_clean = n.strip()
        if n_clean and len(n_clean) >= 2 and not n_clean.isdigit():
            # 过滤诸如 "非公开" "公开" 等标签
            if n_clean not in {"公开", "非公开", "汇报类", "审议类"}:
                valid.append(n_clean)
    return valid


def _split_table_row(line: str) -> list[str]:
    """切分管道表格行，自动剔除首尾空单元格。"""
    cells = [c.strip() for c in line.split("|")]
    if line.startswith("|") and cells:
        cells = cells[1:]
    if line.endswith("|") and cells:
        cells = cells[:-1]
    return cells


def parse_agenda_text(text: str) -> AgendaPlan:
    """从文本或 OCR 字符串中提取 AgendaPlan。"""
    normalized_text = (text or "").strip()
    # 制表符分隔的多行文本自动转为管道表格
    if "\t" in normalized_text and "|" not in normalized_text:
        lines_with_tab = [l for l in normalized_text.splitlines() if "\t" in l]
        if len(lines_with_tab) >= 2:
            normalized_text = "\n".join(
                "| " + " | ".join(c.strip() for c in l.split("\t")) + " |" if "\t" in l else l
                for l in normalized_text.splitlines()
            )

    raw_lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    logger.info("agenda_parser: parsing agenda text (%d chars, %d lines)", len(normalized_text), len(raw_lines))

    meta = AgendaMeta()
    table_lines: list[str] = []

    for line in raw_lines:
        # 元数据识别
        if any(h in line for h in ("会议主题", "Subject")) and not line.startswith("|"):
            meta.theme = re.sub(r"^(?:会议主题|Subject)\s*[:：]?\s*", "", line, flags=re.I).strip()
            continue
        if any(h in line for h in ("会议时间", "Time")) and not any(k in line for k in ("起止时间", "时长", "编号", "序号", "|")):
            meta.date_time = re.sub(r"^(?:会议时间|Time)\s*[:：]?\s*", "", line, flags=re.I).strip()
            continue
        if any(h in line for h in ("与会人", "Attendees")) and not any(k in line for k in ("参与人", "|")):
            val = re.sub(r"^(?:与会人|Attendees)\s*[:：]?\s*", "", line, flags=re.I).strip()
            meta.attendees = (meta.attendees + " " + val).strip() if meta.attendees else val
            continue
        if line.startswith(("全程与会人", "分段与会人")):
            meta.attendees = (meta.attendees + " " + line).strip() if meta.attendees else line
            continue

        # 表格行识别
        if "|" in line or line.startswith(("-", "+")):
            table_lines.append(line)

    # 寻找表格表头
    header_idx = -1
    for i, line in enumerate(table_lines):
        if "|" in line and not re.match(r"^[\s\+\-\|:]+$", line):
            cells = _split_table_row(line)
            has_topic = any("议题" in c or "topic" in c.lower() or "主题" in c or "事项" in c for c in cells)
            has_seq_and_role = any("序号" in c or "编号" in c or "no" in c.lower() for c in cells) and any(
                "汇报" in c or "主讲" in c or "报告" in c or "时长" in c or "内容" in c for c in cells
            )
            if has_topic or has_seq_and_role:
                header_idx = i
                break

    items: list[AgendaItemParsed] = []
    used_cols: dict[str, int] | None = None
    mode = "table"

    # 模式 A：表格提取
    if header_idx != -1:
        headers = _split_table_row(table_lines[header_idx])
        cols = _resolve_columns(headers)
        used_cols = cols
        logger.info("agenda_parser: matched table header at line %d: %s", header_idx, headers)

        for line in table_lines[header_idx + 1:]:
            if re.match(r"^[\s\+\-\|:]+$", line):
                continue
            cells = _split_table_row(line)

            t_col = cols["title"]
            if t_col == -1 or t_col >= len(cells):
                continue
            title = cells[t_col].strip()
            if not title or title.startswith(("-", "+")) or any(k in title for k in ("议题名称", "Topic", "序号", "编号")):
                continue

            s_col = cols["seq"]
            seq = ""
            if s_col != -1 and s_col < len(cells) and cells[s_col].strip():
                seq = cells[s_col].strip()
            if not seq:
                seq = str(len(items) + 1)
            # 格式化为 01, 02 规范序号
            if seq.isdigit():
                seq = f"{int(seq):02d}"

            p_col = cols["presenter"]
            raw_pres = cells[p_col].strip() if p_col != -1 and p_col < len(cells) else ""
            presenters = clean_presenter_names(raw_pres)

            rec_col = cols.get("recorder", -1)
            raw_rec = cells[rec_col].strip() if rec_col != -1 and rec_col < len(cells) else ""
            recorders = clean_presenter_names(raw_rec)

            mem_col = cols.get("members", -1)
            raw_mem = cells[mem_col].strip() if mem_col != -1 and mem_col < len(cells) else ""
            members = clean_presenter_names(raw_mem)

            dur_col = cols["duration"]
            dur = cells[dur_col].strip() if dur_col != -1 and dur_col < len(cells) else ""

            time_col = cols["time"]
            time_val = cells[time_col].strip() if time_col != -1 and time_col < len(cells) else ""

            cat_col = cols["category"]
            cat_val = cells[cat_col].strip() if cat_col != -1 and cat_col < len(cells) else ""

            items.append(
                AgendaItemParsed(
                    seq=seq,
                    title=title,
                    presenters=presenters,
                    raw_presenter=raw_pres,
                    recorders=recorders,
                    members=members,
                    duration=dur,
                    time_range=time_val,
                    category=cat_val,
                )
            )
        logger.info("agenda_parser: table mode extracted %d items", len(items))

    # 模式 B：若无表格或提取为0，回退至行列表扫描（如：1. 议题名称 汇报人：XXX 或 议题一：XXX）
    if not items:
        mode = "line_scan"
        logger.info("agenda_parser: falling back to line-scan mode")
        seq_counter = 1
        for line in raw_lines:
            # 匹配形如 "1. xxx" 或 "议题一：xxx" 或 "【议题1】xxx" 或 "1 xxx"
            m = re.match(
                r"^(?:(?:[第【]?\s*(\d+|[一二三四五六七八九十]+)\s*[项、.期】\s]?\s*)|(?:议题\s*(\d+)\s*[:：]?\s*))(.+)$",
                line,
            )
            if m:
                raw_seq = m.group(1) or m.group(2) or str(seq_counter)
                body = (m.group(3) or "").strip()
                # 检查 body 中是否含汇报人
                pres_match = re.search(r"(?:汇报人|主讲人|报告人|分享人|责任人|发言人)\s*[:：]\s*([^\s;；,，]+)", body)
                pres_list = []
                clean_title = body
                if pres_match:
                    pres_list = clean_presenter_names(pres_match.group(1))
                    clean_title = body[:pres_match.start()].strip()

                if clean_title:
                    seq_str = f"{seq_counter:02d}"
                    items.append(
                        AgendaItemParsed(
                            seq=seq_str,
                            title=clean_title,
                            presenters=pres_list,
                            raw_presenter=pres_match.group(0) if pres_match else "",
                        )
                    )
                    seq_counter += 1
        logger.info("agenda_parser: line-scan mode extracted %d items", len(items))

    if items:
        lines_summary = [
            f"[AGENDA_PARSER] 既定议程单识别成功 (来源: {mode}, 共 {len(items)} 项):",
        ]
        if meta.theme:
            lines_summary.append(f"  * 会议主题: {meta.theme}")
        if meta.date_time:
            lines_summary.append(f"  * 会议时间: {meta.date_time}")
        for it in items:
            pres_str = ", ".join(it.presenters) if it.presenters else "(未指定或未识别到演讲人)"
            dur_str = f" [预计时长: {it.duration}]" if it.duration else ""
            cat_str = f" [{it.category}]" if it.category else ""
            lines_summary.append(f"  -> 议题 {it.seq}: 《{it.title}》 | 演讲人/汇报人: {pres_str}{dur_str}{cat_str}")
        logger.info("\n".join(lines_summary))
    else:
        logger.warning(
            "[AGENDA_PARSER] ⚠ 未能从输入文本中识别出任何既定议程项！原始输入预览 (前300字): %s",
            normalized_text[:300].replace("\n", " "),
        )

    plan = AgendaPlan(meta=meta, items=items)
    _log_parser_record(normalized_text, plan, mode, used_cols)
    return plan

