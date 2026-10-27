"""agenda_parser.py -- 解析会前既定议程单（txt/md 表格或 OCR 文本）。

支持：
1. 标准 Markdown / ASCII 管道表格（| 编号 | 议题名称 | 时长 | 汇报人 |）
2. 文本列表（如 1. 议题名称 汇报人：XXX）
3. 会议主题 (Subject)、时间 (Time)、与会人员 (Attendees) 顶层元数据提取
4. 汇报人姓名清洗（自动剥离工号、前缀如 汇报人:、标点分割）
"""
from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("agentflow.agenda_parser")

_PARSED_AGENDA_CACHE: dict[tuple[str, tuple[str, ...]], AgendaPlan] = {}
_PARSED_AGENDA_RAW_CACHE: dict[str, AgendaPlan] = {}


def clear_agenda_parser_cache() -> None:
    """清理议程单解析缓存及全链路关联缓存。"""
    _PARSED_AGENDA_CACHE.clear()
    _PARSED_AGENDA_RAW_CACHE.clear()
    try:
        from domains.meeting.tasks.agenda_minutes.alignment_engine import clear_alignment_cache

        clear_alignment_cache()
    except Exception:
        pass
    try:
        from domains.meeting.agenda_engine import clear_agenda_engine_cache

        clear_agenda_engine_cache()
    except Exception:
        pass



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
    description: str = ""


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
    desc_idx = -1

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
        # 内容说明 / 描述 / 备注
        if any(k in name for k in ("内容说明", "具体内容", "内容介绍", "说明", "备注", "描述", "议题描述")):
            desc_idx = idx
            continue
        # 议题名称（优先匹配含「名称」「全称」「主题」的列，以及「环节」「活动环节」「议程」）
        if any(k in name for k in ("议题名称", "topic name", "议题全称", "主题", "topic", "讨论事项", "审议事项", "汇报内容", "议题内容", "环节", "活动环节", "议程", "议程环节")):
            if not any(k in name for k in ("类型", "材料", "参与人", "成员", "人员", "category", "material", "member", "recorder", "纪要", "时长")):
                title_idx = idx
                continue
        # 兜底：含「议题」但不含类型/材料/人员/时长
        if "议题" in name and not any(k in name for k in ("类型", "材料", "参与人", "成员", "人员", "category", "material", "member", "recorder", "纪要", "时长")):
            title_idx = idx
            continue
        # 兜底：含「事项」「内容」
        if any(k in name for k in ("事项", "内容", "项目")) and not any(k in name for k in ("说明", "备注", "描述", "类型", "材料", "参与人", "成员", "人员", "category", "material", "member", "recorder", "纪要", "时长")):
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
        "description": desc_idx,
    }
    logger.debug("agenda_parser: resolved table columns -> %s", cols)
    return cols


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

# 强分隔符：分号/逗号/斜杠/竖线/顿号/换行/制表符、and、&、连续空格。
# 单空格不在这里拆，否则英文全名会被切成两个词。
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


def _has_cjk(text: str) -> bool:
    return bool(_CJK_PATTERN.search(text or ""))


def _split_name_chunk(chunk: str) -> list[str]:
    """拆分单个姓名片段：中文多人名按空格拆，英文全名保持完整。"""
    chunk = (chunk or "").strip()
    if not chunk:
        return []
    if _has_cjk(chunk):
        return [part.strip() for part in re.split(r"\s+", chunk) if part.strip()]
    return [chunk]


def clean_presenter_names(raw: str) -> list[str]:
    """从原始单元格中提取干净的汇报人姓名列表。

    处理诸如：
    - '汇报人: 张三 00585440' -> ['张三']
    - '张三; 李四' -> ['张三', '李四']
    - '汇报人: 李四 00939670 张三 00841266' -> ['李四', '张三']
    - 'Presenter: Alice Chen' -> ['Alice Chen']
    - 'Alice Chen；Bob Lee' -> ['Alice Chen', 'Bob Lee']
    - 'Alice Chen and Bob Lee' -> ['Alice Chen', 'Bob Lee']
    - '张三；Alice Chen' -> ['张三', 'Alice Chen']
    """
    if not raw or not raw.strip():
        return []
    # 剥离 Markdown 格式符号与首尾空白
    text = re.sub(r"[\*#_`]", "", raw.strip())
    # 剥离 5~8 位连续数字工号
    text = re.sub(r"\b\d{5,8}\b", "", text)
    # 剔除括号及其内工号或备注，如 (委托某某)
    text = re.sub(r"\([^)]*\)|（[^）]*）", "", text)

    names: list[str] = []
    for chunk in _NAME_SPLIT_RE.split(text):
        # 每个分段都剥离一次角色前缀，避免 "Alice；Moderator: Bob" 残留前缀
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
    """切分管道表格行，自动剔除首尾空单元格。"""
    cells = [c.strip() for c in line.split("|")]
    if line.startswith("|") and cells:
        cells = cells[1:]
    if line.endswith("|") and cells:
        cells = cells[:-1]
    return cells


_COMMON_VARIANTS: dict[str, str] = {
    # 常见 OCR 易混形近字与变体
    "错": "锴", "锴": "锴",
    "九": "旭", "旭": "旭",
    "倍": "培", "培": "培",
    # 常用繁简与异体字归一化
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


def _normalize_ascii_name(text: str) -> str:
    """英文姓名归一：大小写、空格、连字符、撇号、点号差异不影响匹配。"""
    normalized = (text or "").casefold()
    return re.sub(r"[\s\-–—_.'’]", "", normalized)


def _ascii_name_in_text(name: str, text: str) -> bool:
    """英文姓名按整词边界查找，避免 Ann 误中 Joanne。"""
    if not name or not text:
        return False
    pattern = rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])"
    return bool(re.search(pattern, text, re.IGNORECASE))


def match_presenter_name(p: str, sp: str) -> float:
    """计算议程汇报人与实际发言人的匹配相似度（支持繁简异体、拼音同音与英文归一）。"""
    if not p or not sp:
        return 0.0
    p_strip = re.sub(r"[\*#_`\s]", "", p)
    sp_strip = re.sub(r"[\*#_`\s]", "", sp)
    if not p_strip or not sp_strip:
        return 0.0

    # 中文姓名：保留原有子串、异体字与拼音容错逻辑
    if _has_cjk(p_strip) or _has_cjk(sp_strip):
        if p_strip == sp_strip or p_strip in sp_strip or sp_strip in p_strip:
            return 1.0

        # 变体汉字归一化（繁简与常见异体）
        p_norm = "".join(_COMMON_VARIANTS.get(c, c) for c in p_strip)
        sp_norm = "".join(_COMMON_VARIANTS.get(c, c) for c in sp_strip)
        if p_norm == sp_norm or p_norm in sp_norm or sp_norm in p_norm:
            return 0.95

        # 语音转写 ASR 常见同音字容错（基于拼音同音比对）
        if len(p_strip) == len(sp_strip) and len(p_strip) >= 2:
            try:
                from pypinyin import lazy_pinyin

                if lazy_pinyin(p_strip) == lazy_pinyin(sp_strip):
                    return 0.9
            except Exception:
                pass

        return 0.0

    # 英文姓名：大小写/空格/连字符/撇号归一后精确匹配，再用整词边界包含
    p_clean = re.sub(r"[\*#_`]", "", p).strip()
    sp_clean = re.sub(r"[\*#_`]", "", sp).strip()
    if _normalize_ascii_name(p_clean) == _normalize_ascii_name(sp_clean):
        return 1.0
    if _ascii_name_in_text(p_clean, sp_clean) or _ascii_name_in_text(sp_clean, p_clean):
        return 0.95
    return 0.0


def extract_speakers_from_transcript(transcript: str) -> list[str]:
    """从会议转写文本中提取出所有出场的发言人姓名列表（保序且去重）。"""
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

    # 英文方括号发言人 [Alice Chen] 可与时间戳格式混用，单独补一轮
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
    """根据真实转写出场人名单，对议程计划中的 OCR 误识/异体字人名（如形似错别字、异体字）进行自动校对。"""
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
            logger.debug(
                "reconcile_presenter_names: reconciled '%s' -> '%s' (score=%.2f)",
                name,
                best_match,
                best_score,
            )
            return best_match
        return name

    for item in plan.items:
        if item.presenters:
            item.presenters = [_best_cand(p) for p in item.presenters]
        if item.recorders:
            item.recorders = [_best_cand(r) for r in item.recorders]
        if item.members:
            item.members = [_best_cand(m) for m in item.members]

    if plan.meta.attendees:
        for cand in cleaned_cands:
            for p in re.findall(r"[\u4e00-\u9fa5]{2,6}", plan.meta.attendees):
                if p not in cand_set and match_presenter_name(p, cand) >= 0.8:
                    logger.debug("reconcile_presenter_names (meta): reconciled '%s' -> '%s'", p, cand)
                    plan.meta.attendees = plan.meta.attendees.replace(p, cand)

    return plan


_TITLE_HEADER_ALIASES = {
    "议题名称", "序号", "编号",
    "topic", "topic name", "title", "subject", "agenda item", "session", "item",
    "no", "no.", "seq",
}


def parse_agenda_text(
    text: str,
    transcript: str = "",
    candidate_speakers: set[str] | list[str] | None = None,
) -> AgendaPlan:
    """从文本或 OCR 字符串中提取 AgendaPlan，可结合 transcript 自动校对形似错别字人名。"""
    normalized_text = (text or "").strip()
    if not normalized_text:
        return AgendaPlan()

    # 提取发言人候选集合用于缓存键判定
    if candidate_speakers:
        spk_tuple = tuple(sorted(set(str(s).strip() for s in candidate_speakers if str(s).strip())))
    elif transcript:
        spk_tuple = tuple(sorted(set(extract_speakers_from_transcript(transcript))))
    else:
        spk_tuple = ()

    cache_key = (normalized_text, spk_tuple)
    if cache_key in _PARSED_AGENDA_CACHE:
        cached_plan = _PARSED_AGENDA_CACHE[cache_key]
        logger.debug("[AGENDA_PARSER] 命中议程单解析缓存 (共 %d 项)", len(cached_plan.items))
        return copy.deepcopy(cached_plan)

    if normalized_text in _PARSED_AGENDA_RAW_CACHE:
        raw_plan = copy.deepcopy(_PARSED_AGENDA_RAW_CACHE[normalized_text])
        logger.debug("[AGENDA_PARSER] 命中原始议程单解析缓存 (共 %d 项)", len(raw_plan.items))
        if transcript or candidate_speakers:
            raw_plan = reconcile_presenter_names(
                raw_plan,
                transcript=transcript,
                candidate_speakers=candidate_speakers,
            )
        if len(_PARSED_AGENDA_CACHE) >= 64:
            _PARSED_AGENDA_CACHE.pop(next(iter(_PARSED_AGENDA_CACHE)))
        _PARSED_AGENDA_CACHE[cache_key] = copy.deepcopy(raw_plan)
        return raw_plan

    # 制表符分隔的多行文本自动转为管道表格
    if "\t" in normalized_text and "|" not in normalized_text:
        lines_with_tab = [l for l in normalized_text.splitlines() if "\t" in l]
        if len(lines_with_tab) >= 2:
            normalized_text = "\n".join(
                "| " + " | ".join(c.strip() for c in l.split("\t")) + " |" if "\t" in l else l
                for l in normalized_text.splitlines()
            )

    raw_lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    logger.debug("agenda_parser: parsing agenda text (%d chars, %d lines)", len(normalized_text), len(raw_lines))

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
        # 人员元数据识别（支持 全程与会人/主持人/组织主席/分段列席 等多种格式）
        line_clean = re.sub(r"^[#\*\s\-]+", "", line).strip()
        if any(h in line_clean for h in ("与会人", "Attendees", "主持人", "组织主席", "会议主席", "执行主席", "评委", "主席")) and not any(k in line_clean for k in ("参与人", "|")):
            meta.attendees = (meta.attendees + "\n" + line_clean).strip() if meta.attendees else line_clean
            continue

        # 表格行识别
        if "|" in line or line.startswith(("-", "+")):
            table_lines.append(line)

    # 寻找表格表头
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
    used_cols: dict[str, int] | None = None
    mode = "table"

    # 模式 A：表格提取
    if header_idx != -1:
        headers = _split_table_row(table_lines[header_idx])
        cols = _resolve_columns(headers)
        used_cols = cols
        logger.debug("agenda_parser: matched table header at line %d: %s", header_idx, headers)

        for line in table_lines[header_idx + 1:]:
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

            desc_col = cols.get("description", -1)
            desc_val = cells[desc_col].strip() if desc_col != -1 and desc_col < len(cells) else ""

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
                    description=desc_val,
                )
            )
        logger.debug("agenda_parser: table mode extracted %d items", len(items))

    # 模式 B：若无表格或提取为0，回退至行列表扫描（如：1. 议题名称 汇报人：XXX 或 议题一：XXX）
    if not items:
        mode = "line_scan"
        logger.debug("agenda_parser: falling back to line-scan mode")
        seq_counter = 1
        for line in raw_lines:
            # 匹配形如 "1. xxx" 或 "议题一：xxx" 或 "【议题1】xxx" 或 "1 xxx"
            m = re.match(
                r"^(?:(?:[第【]?\s*(\d+|[一二三四五六七八九十]+)\s*[项、.期】\s]?\s*)|(?:议题\s*(\d+)\s*[:：]?\s*))(.+)$",
                line,
            )
            if m:
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
        logger.debug("agenda_parser: line-scan mode extracted %d items", len(items))

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

    base_plan = AgendaPlan(meta=meta, items=items)
    if len(_PARSED_AGENDA_RAW_CACHE) >= 64:
        _PARSED_AGENDA_RAW_CACHE.pop(next(iter(_PARSED_AGENDA_RAW_CACHE)))
    _PARSED_AGENDA_RAW_CACHE[normalized_text] = copy.deepcopy(base_plan)

    plan = copy.deepcopy(base_plan)
    if transcript or candidate_speakers:
        plan = reconcile_presenter_names(
            plan,
            transcript=transcript,
            candidate_speakers=candidate_speakers,
        )
    _log_parser_record(normalized_text, plan, mode, used_cols)

    # 存入缓存（限制最大缓存数量以防止内存泄露）
    if len(_PARSED_AGENDA_CACHE) >= 64:
        _PARSED_AGENDA_CACHE.pop(next(iter(_PARSED_AGENDA_CACHE)))
    _PARSED_AGENDA_CACHE[cache_key] = copy.deepcopy(plan)

    return plan


__all__ = [
    "AgendaItemParsed",
    "AgendaMeta",
    "AgendaPlan",
    "clean_presenter_names",
    "clear_agenda_parser_cache",
    "extract_speakers_from_transcript",
    "match_presenter_name",
    "parse_agenda_text",
    "reconcile_presenter_names",
]

