"""agenda parser -- 会前既定议程结构化解析器 (零旧代码依赖).

支持:
1. Markdown / ASCII 管道表格 (| 编号 | 议题名称 | 汇报人 | 时长 |)
2. 文本列表 (如 "1. 议题名称 汇报人：XXX" 或 "议题一：XXX")
3. VLM 视觉返回的结构化字典 ({"theme": ..., "agenda_items": [...]})
4. 汇报人姓名提纯清洗 (剥离 5~8 位工号、前缀如 汇报人:、职称头衔)
5. 结合会议转写出场人名单，自动纠偏 OCR 错别字/异体字人名
"""
from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("tasks.minutes.agenda.parser")

_CJK_PATTERN = re.compile(r"[\u4e00-\u9fa5]")

_NAME_ROLE_PREFIX_RE = re.compile(
    r"^(?:"
    r"(?:汇报人|主讲人|报告人|分享人|责任人|发言人|主持人|会议主持|全程与会人|与会人|列席人|分段列席人)\s*[:：]\s*"
    r"|"
    r"(?:presenters?|speakers?|reporters?|owners?|hosts?|moderators?|chairs?|chairpersons?|"
    r"facilitators?|leads?|minutes\s+taker|note\s+taker|session\s+chairs?|presented\s+by)"
    r"\b\s*(?:[:：\-–—]\s*)?"
    r")",
    re.IGNORECASE,
)

_NAME_SPLIT_RE = re.compile(
    r"[\r\n\t;；,，/|、]+|\s+and\s+|\s+&\s+|\s{2,}",
    re.IGNORECASE,
)

_NAME_LABELS = {
    "公开", "非公开", "汇报类", "审议类",
    "presenter", "presenters", "speaker", "speakers", "reporter", "reporters",
    "owner", "owners", "host", "hosts", "moderator", "moderators",
    "chair", "chairs", "chairperson", "chairpersons", "session chair", "session chairs",
    "facilitator", "facilitators", "lead", "leads", "minutes taker", "note taker",
    "tbd", "tbc", "n/a", "none", "all",
}
_NAME_LABELS_LOWER = {label.casefold() for label in _NAME_LABELS}

_COMMON_VARIANTS: dict[str, str] = {
    "错": "锴", "锴": "锴",
    "九": "旭", "旭": "旭",
    "倍": "培", "培": "培",
    "啟": "启", "啓": "启",
    "鋒": "锋", "峰": "锋",
    "恒": "恒", "恆": "恒",
    "强": "强", "強": "强",
    "伟": "伟", "偉": "伟",
    "华": "华", "華": "华",
}

_ENGLISH_NAME_PATTERN = r"[A-Z][A-Za-z.'’\-]*(?:\s+[A-Z][A-Za-z.'’\-]*){0,2}"

_SPEAKER_LABEL_PATTERN = (
    r"(?:[^\n:：\d]{1,16}"
    r"|(?:发言者|说话人|发言人|主讲人|参会人|与会人|Speaker|User|Participant)\s*[\-_#]?\s*\d{1,4}"
    rf"|{_ENGLISH_NAME_PATTERN})"
)

_SPEAKER_TS_PATTERN = re.compile(
    rf"^(?:"
    rf"(?:\[?(\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:\.\d+)?)]?\s+({_SPEAKER_LABEL_PATTERN}))"
    rf"|"
    rf"(?:({_SPEAKER_LABEL_PATTERN})\s*(?:[:：])?\s+\[?(\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:\.\d+)?)\]?)"
    rf")(?:\s*[:：]|\s*$|\s+(?=\S))",
    re.M,
)
_SPEAKER_COLON_PATTERN = re.compile(
    r"^(?:【([^】\n]{2,16})】|\[([A-Za-z][A-Za-z .'’\-]{1,31})\]|([^\n\d:：]{2,32})\s*[:：])\s*",
    re.M,
)
_SPEAKER_BRACKET_PATTERN = re.compile(
    r"^\[([A-Za-z][A-Za-z .'’\-]{1,31})\]", re.M
)

_SPEAKER_ROLE_LABELS = {"主持人", "评委", "现场发言人"}
_SPEAKER_ROLE_LABELS_LOWER = {
    "host", "moderator", "chair", "chairperson", "facilitator", "organizer",
    "mc", "session chair", "speaker", "panelist", "guest", "attendee",
    "tbd", "tbc", "n/a", "none", "all",
}

_TITLE_HEADER_ALIASES = {
    "议题名称", "序号", "编号",
    "topic", "topic name", "title", "subject", "agenda item", "session", "item",
    "no", "no.", "seq",
}


@dataclass
class AgendaItemParsed:
    """单项既定议程解析结果."""

    seq: str
    title: str
    presenters: list[str] = field(default_factory=list)
    time_range: str = ""


@dataclass
class AgendaMeta:
    """议程顶层元数据."""

    theme: str = ""
    attendees: str = ""


@dataclass
class AgendaPlan:
    """全会议程总表."""

    meta: AgendaMeta = field(default_factory=AgendaMeta)
    items: list[AgendaItemParsed] = field(default_factory=list)


def normalize_lang(lang: str | None) -> str:
    """把请求语种归一为 zh/en."""
    return "en" if (lang or "").strip().lower() == "en" else "zh"


def _has_cjk(text: str) -> bool:
    return bool(_CJK_PATTERN.search(text or ""))


def _split_name_chunk(chunk: str) -> list[str]:
    c = (chunk or "").strip()
    if not c:
        return []
    if _has_cjk(c):
        return [part.strip() for part in re.split(r"\s+", c) if part.strip()]
    return [c]


def clean_presenter_names(raw: str) -> list[str]:
    """从单元格或文本中提取干净的汇报人姓名列表 (剥离工号、前缀、标点)."""
    if not raw or not raw.strip():
        return []
    text = re.sub(r"[\*#_`]", "", raw.strip())
    # 剥离 5~8 位连续数字工号
    text = re.sub(r"\b\d{5,8}\b", "", text)
    # 剔除括号及其内工号或备注，如 (委托某某)
    text = re.sub(r"\([^)]*\)|（[^）]*）", "", text)

    names: list[str] = []
    for chunk in _NAME_SPLIT_RE.split(text):
        chunk = _NAME_ROLE_PREFIX_RE.sub("", chunk.strip(), count=1)
        names.extend(_split_name_chunk(chunk))

    valid: list[str] = []
    for name in names:
        n_clean = re.sub(r"\s+", " ", name).strip(" ,;；:：")
        if not n_clean or n_clean.isdigit():
            continue
        if not re.search(r"[A-Za-z\u4e00-\u9fa5]", n_clean):
            continue
        if n_clean in _NAME_LABELS or n_clean.casefold() in _NAME_LABELS_LOWER:
            continue
        max_len = 20 if _has_cjk(n_clean) else 64
        if 2 <= len(n_clean) <= max_len:
            valid.append(n_clean)
    return valid


def _split_table_row(line: str) -> list[str]:
    cells = [c.strip() for c in line.split("|")]
    if line.startswith("|") and cells:
        cells = cells[1:]
    if line.endswith("|") and cells:
        cells = cells[:-1]
    return cells


def _resolve_columns(header_cells: list[str]) -> dict[str, int]:
    title_idx = -1
    seq_idx = -1
    pres_idx = -1
    mem_idx = -1
    time_idx = -1
    dur_idx = -1

    for idx, raw in enumerate(header_cells):
        name = raw.strip().lower()
        if not name:
            continue
        if any(k in name for k in ("序号", "编号", "no.", "no", "seq", "项")):
            seq_idx = idx
            continue
        if any(k in name for k in ("时长", "duration", "用时", "预计用时", "时长(min)", "时长（分）", "时间(分)")):
            dur_idx = idx
            continue
        if (any(k in name for k in ("起止时间", "时间段", "议题时间")) or (("时间" in name or "time" in name) and dur_idx != idx)):
            time_idx = idx
            continue
        if any(k in name for k in ("汇报人", "reporter", "主讲人", "主讲", "报告人", "分享人", "责任人", "发言人", "汇报人员", "汇报")):
            pres_idx = idx
            continue
        if any(k in name for k in ("参与人", "成员", "members", "attendees", "列席人", "与会人", "参会人员")):
            mem_idx = idx
            continue
        if any(k in name for k in ("议题名称", "topic name", "议题全称", "主题", "topic", "讨论事项", "审议事项", "汇报内容", "议题内容", "环节", "活动环节", "议程", "议程环节")):
            if not any(k in name for k in ("类型", "材料", "参与人", "成员", "人员", "category", "material", "member", "recorder", "纪要", "时长")):
                title_idx = idx
                continue
        if "议题" in name and not any(k in name for k in ("类型", "材料", "参与人", "成员", "人员", "category", "material", "member", "recorder", "纪要", "时长")):
            title_idx = idx
            continue
        if any(k in name for k in ("事项", "内容", "项目")) and not any(k in name for k in ("说明", "备注", "描述", "类型", "材料", "参与人", "成员", "人员", "category", "material", "member", "recorder", "纪要", "时长")):
            if title_idx == -1:
                title_idx = idx
                continue

    if pres_idx == -1 and mem_idx != -1 and mem_idx != title_idx:
        pres_idx = mem_idx

    resolved_time_idx = time_idx if time_idx != -1 else dur_idx
    return {
        "seq": seq_idx,
        "title": title_idx,
        "presenter": pres_idx,
        "time": resolved_time_idx,
    }


def _normalize_ascii_name(text: str) -> str:
    normalized = (text or "").casefold()
    return re.sub(r"[\s\-–—_.'’]", "", normalized)


def _ascii_name_in_text(name: str, text: str) -> bool:
    if not name or not text:
        return False
    pattern = rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])"
    return bool(re.search(pattern, text, re.IGNORECASE))


def match_presenter_name(p: str, sp: str) -> float:
    """计算议程汇报人与实际发言人的匹配相似度."""
    if not p or not sp:
        return 0.0
    p_strip = re.sub(r"[\*#_`\s]", "", p)
    sp_strip = re.sub(r"[\*#_`\s]", "", sp)
    if not p_strip or not sp_strip:
        return 0.0

    if _has_cjk(p_strip) or _has_cjk(sp_strip):
        if p_strip == sp_strip or p_strip in sp_strip or sp_strip in p_strip:
            return 1.0

        p_norm = "".join(_COMMON_VARIANTS.get(c, c) for c in p_strip)
        sp_norm = "".join(_COMMON_VARIANTS.get(c, c) for c in sp_strip)
        if p_norm == sp_norm or p_norm in sp_norm or sp_norm in p_norm:
            return 0.95

        if len(p_strip) == len(sp_strip) and len(p_strip) >= 2:
            try:
                from pypinyin import lazy_pinyin

                if lazy_pinyin(p_strip) == lazy_pinyin(sp_strip):
                    return 0.9
            except Exception:
                pass
        return 0.0

    p_clean = re.sub(r"[\*#_`]", "", p).strip()
    sp_clean = re.sub(r"[\*#_`]", "", sp).strip()
    if _normalize_ascii_name(p_clean) == _normalize_ascii_name(sp_clean):
        return 1.0
    if _ascii_name_in_text(p_clean, sp_clean) or _ascii_name_in_text(sp_clean, p_clean):
        return 0.95
    return 0.0


def extract_speakers_from_transcript(transcript: str) -> list[str]:
    """从会议转写文本中提取出所有出场的发言人姓名列表 (保序且去重)."""
    if not transcript or not transcript.strip():
        return []
    text = transcript.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(_SPEAKER_TS_PATTERN.finditer(text))
    if not matches:
        matches = list(_SPEAKER_COLON_PATTERN.finditer(text))
        raw_speakers = [(m.group(1) or m.group(2) or m.group(3) or "").strip() for m in matches]
    else:
        raw_speakers = [
            (m.group(2) if m.group(1) else m.group(3) or "").strip()
            for m in matches
        ]

    raw_speakers.extend(
        m.group(1).strip() for m in _SPEAKER_BRACKET_PATTERN.finditer(text)
    )

    seen = set()
    speakers: list[str] = []
    for s in raw_speakers:
        s_clean = re.sub(r"\b\d{5,8}\b", "", s).strip()
        if s_clean and s_clean not in seen and 2 <= len(s_clean) <= 32:
            if (
                s_clean not in _SPEAKER_ROLE_LABELS
                and s_clean.casefold() not in _SPEAKER_ROLE_LABELS_LOWER
            ):
                seen.add(s_clean)
                speakers.append(s_clean)
    return speakers


def reconcile_presenter_names(
    plan: AgendaPlan,
    transcript: str = "",
    candidate_speakers: set[str] | list[str] | None = None,
) -> AgendaPlan:
    """根据真实转写出场人名单，对议程计划中的 OCR 误识/异体字人名进行自动校对."""
    cands: list[str] = []
    if candidate_speakers:
        cands.extend(candidate_speakers)
    if transcript:
        cands.extend(extract_speakers_from_transcript(transcript))

    cand_set = set()
    cleaned_cands: list[str] = []
    for c in cands:
        c_str = str(c).strip()
        if c_str and c_str not in cand_set:
            cand_set.add(c_str)
            cleaned_cands.append(c_str)

    if not cleaned_cands:
        return plan

    def _best_cand(name: str) -> str:
        if not name or name in cand_set:
            return name
        best_score = 0.0
        best_match = name
        for cand in cleaned_cands:
            score = match_presenter_name(name, cand)
            if score > best_score:
                best_score = score
                best_match = cand
        if best_score >= 0.8:
            return best_match
        return name

    for item in plan.items:
        if item.presenters:
            item.presenters = [_best_cand(p) for p in item.presenters]

    return plan


def parse_agenda_text(
    text: str,
    transcript: str = "",
    candidate_speakers: set[str] | list[str] | None = None,
) -> AgendaPlan:
    """从文本或表格字符串中提取 AgendaPlan，可结合 transcript 自动校对人名."""
    normalized_text = (text or "").strip()
    if not normalized_text:
        return AgendaPlan()

    # 制表符转管道表格
    if "\t" in normalized_text and "|" not in normalized_text:
        lines_with_tab = [l for l in normalized_text.splitlines() if "\t" in l]
        if len(lines_with_tab) >= 2:
            normalized_text = "\n".join(
                "| " + " | ".join(c.strip() for c in l.split("\t")) + " |" if "\t" in l else l
                for l in normalized_text.splitlines()
            )

    raw_lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    meta = AgendaMeta()
    table_lines: list[str] = []

    for line in raw_lines:
        if any(h in line for h in ("会议主题", "Subject")) and not line.startswith("|"):
            meta.theme = re.sub(r"^(?:会议主题|Subject)\s*[:：]?\s*", "", line, flags=re.I).strip()
            continue
        line_clean = re.sub(r"^[#\*\s\-]+", "", line).strip()
        if any(h in line_clean for h in ("与会人", "Attendees", "主持人", "组织主席", "会议主席", "执行主席", "评委", "主席")) and not any(k in line_clean for k in ("参与人", "|")):
            meta.attendees = (meta.attendees + "\n" + line_clean).strip() if meta.attendees else line_clean
            continue

        if "|" in line or line.startswith(("-", "+")):
            table_lines.append(line)

    header_idx = -1
    for i, line in enumerate(table_lines):
        if "|" in line and not re.match(r"^[\s\+\-\|:]+$", line):
            cells = _split_table_row(line)
            has_topic = any("议题" in c or "topic" in c.lower() or "主题" in c or "事项" in c or "环节" in c or "议程" in c for c in cells)
            has_seq_and_role = any("序号" in c or "编号" in c or "no" in c.lower() for c in cells) and any(
                "汇报" in c or "主讲" in c or "报告" in c or "时长" in c or "内容" in c for c in cells
            )
            if has_topic or has_seq_and_role:
                header_idx = i
                break

    items: list[AgendaItemParsed] = []

    # 模式 A：表格提取
    if header_idx != -1:
        headers = _split_table_row(table_lines[header_idx])
        cols = _resolve_columns(headers)

        for line in table_lines[header_idx + 1 :]:
            if re.match(r"^[\s\+\-\|:]+$", line):
                continue
            cells = _split_table_row(line)

            t_col = cols["title"]
            if t_col == -1 or t_col >= len(cells):
                continue
            title = cells[t_col].strip()
            title_key = title.strip().casefold()
            if not title or title.startswith(("-", "+")) or title_key in _TITLE_HEADER_ALIASES:
                continue

            s_col = cols["seq"]
            seq = ""
            if s_col != -1 and s_col < len(cells) and cells[s_col].strip():
                seq = cells[s_col].strip()
            if not seq:
                seq = str(len(items) + 1)
            if seq.isdigit():
                seq = f"{int(seq):02d}"

            p_col = cols["presenter"]
            raw_pres = cells[p_col].strip() if p_col != -1 and p_col < len(cells) else ""
            presenters = clean_presenter_names(raw_pres)

            time_col = cols["time"]
            time_val = cells[time_col].strip() if time_col != -1 and time_col < len(cells) else ""

            items.append(
                AgendaItemParsed(
                    seq=seq,
                    title=title,
                    presenters=presenters,
                    time_range=time_val,
                )
            )

    # 模式 B：行列表扫描回退
    if not items:
        seq_counter = 1
        for line in raw_lines:
            m = re.match(
                r"^(?:(?:[第【]?\s*(\d+|[一二三四五六七八九十]+)\s*[项、.期】\s]?\s*)|(?:议题\s*(\d+)\s*[:：]?\s*))(.+)$",
                line,
            )
            if m:
                body = (m.group(3) or "").strip()
                pres_match = re.search(r"(?:汇报人|主讲人|报告人|分享人|责任人|发言人)\s*[:：]\s*([^\s;；,，]+)", body)
                pres_list = []
                clean_title = body
                if pres_match:
                    pres_list = clean_presenter_names(pres_match.group(1))
                    clean_title = body[: pres_match.start()].strip()

                if clean_title:
                    seq_str = f"{seq_counter:02d}"
                    items.append(
                        AgendaItemParsed(
                            seq=seq_str,
                            title=clean_title,
                            presenters=pres_list,
                            time_range="",
                        )
                    )
                    seq_counter += 1

    plan = AgendaPlan(meta=meta, items=items)
    if transcript or candidate_speakers:
        plan = reconcile_presenter_names(
            plan,
            transcript=transcript,
            candidate_speakers=candidate_speakers,
        )
    return plan


def ensure_agenda_plan(data: dict[str, Any] | list[Any] | AgendaPlan | str, transcript: str = "") -> AgendaPlan:
    """将来自 VLM 的 dict、list、或者文本统一转换为强类型 AgendaPlan."""
    if isinstance(data, AgendaPlan):
        return data
    if isinstance(data, str):
        return parse_agenda_text(data, transcript=transcript)
    if isinstance(data, list):
        items = []
        for it in data:
            if isinstance(it, dict):
                title = str(it.get("title") or it.get("topic") or "").strip()
                if title:
                    raw_pres = it.get("presenters") or it.get("speaker") or it.get("presenter") or []
                    if isinstance(raw_pres, str):
                        presenters = clean_presenter_names(raw_pres)
                    elif isinstance(raw_pres, list):
                        presenters = [str(p) for p in raw_pres]
                    else:
                        presenters = []
                    items.append(
                        AgendaItemParsed(
                            seq=str(it.get("seq") or f"{len(items)+1:02d}").strip(),
                            title=title,
                            presenters=presenters,
                            time_range=str(it.get("time_range") or "").strip(),
                        )
                    )
            elif isinstance(it, str) and it.strip():
                sub_plan = parse_agenda_text(it.strip())
                items.extend(sub_plan.items)
        plan = AgendaPlan(items=items)
        if transcript:
            plan = reconcile_presenter_names(plan, transcript=transcript)
        return plan
    if isinstance(data, dict):
        theme = str(data.get("theme") or "").strip()
        raw_att = data.get("attendees") or []
        attendees = "、".join(raw_att) if isinstance(raw_att, list) else str(raw_att).strip()
        items = []
        raw_items = data.get("agenda_items") or data.get("agenda_plan") or data.get("items") or []
        for it in raw_items:
            if isinstance(it, dict):
                title = str(it.get("title") or it.get("topic") or "").strip()
                if title:
                    raw_pres = it.get("presenters") or it.get("speaker") or it.get("presenter") or []
                    if isinstance(raw_pres, str):
                        presenters = clean_presenter_names(raw_pres)
                    elif isinstance(raw_pres, list):
                        presenters = [str(p) for p in raw_pres]
                    else:
                        presenters = []
                    items.append(
                        AgendaItemParsed(
                            seq=str(it.get("seq") or f"{len(items)+1:02d}").strip(),
                            title=title,
                            presenters=presenters,
                            time_range=str(it.get("time_range") or "").strip(),
                        )
                    )
        plan = AgendaPlan(meta=AgendaMeta(theme=theme, attendees=attendees), items=items)
        if transcript:
            plan = reconcile_presenter_names(plan, transcript=transcript)
        return plan
    return AgendaPlan()


def agenda_plan_to_markdown(plan: AgendaPlan) -> str:
    """将 AgendaPlan 规整化为 Markdown 管道表格文本."""
    if not plan or not plan.items:
        return ""
    lines = ["| 序号 | 议题名称 | 汇报人 | 起止时间 |", "| --- | --- | --- | --- |"]
    for i, it in enumerate(plan.items, 1):
        seq = it.seq or f"{i:02d}"
        pres = "、".join(it.presenters) if it.presenters else "-"
        time_r = it.time_range or "-"
        lines.append(f"| {seq} | {it.title} | {pres} | {time_r} |")
    return "\n".join(lines)
