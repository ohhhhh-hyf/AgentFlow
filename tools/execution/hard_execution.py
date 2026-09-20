"""强执行层：用程序强制约束终局产物，不完全依赖模型自觉。

三类机制（通用、不绑定具体栏目业务名）：

1. **上游硬对齐**：把 LLM 草稿中的「搬运类」字段强制改写为上游列表副本
2. **结构硬约束**：表格粘连修复、按模板「约 N 行」截断、空表占位
3. **验收门禁**：结构校验 + 模板评测；硬伤标记 gate_ok=False

业务字段名仅出现在「配置映射」中（如纪要搬运字段 ↔ understanding 字段），
新增 domain 时可复用同一套函数并传入映射。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from tools.templates.template_eval import (
    evaluate_output_against_template,
    extract_markdown_tables,
    extract_template_table_constraints,
    fix_glued_table_rows,
    parse_section_char_budgets,
)

logger = logging.getLogger(__name__)

# 硬伤：验收门禁失败（仍可落盘 JSON，但默认不落「通过」的 result.md）
HARD_ISSUE_MARKERS = (
    "残留占位符",
    "表格占位数据行未替换",
    "固定文字丢失",
    "输出为空",
    "缺少对应表",
    "无有效数据行",
    "同行粘连",
    "只有标题没有正文",
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")
# 单星号开头的 md 列表项 `* x`（会把 `**称呼**：…` 这类散文段误判成条目行，故用 (?!\*) 排除）
_STAR_BULLET_RE = re.compile(r"^\*(?!\*)")
# 问答/对话的一轮：`**称呼**：…`（`**问**：`/`**答**：` 同形）——一问一答各占一段，不拆段
_DIALOGUE_LINE_RE = re.compile(r"^\*\*[^*\n]{1,24}\*\*\s*[：:]")
# 模板里显式声明「不再分段」的栏，语义分两类、结果一致——都跳过确定性拆段：
# ① 一段一段型（通用纪要 [分段速览]「一个时间段就是一段、不再分段」）：拆了就把一个时间段切成两段；
# ② 问答型（各 Q&A 栏「仍单段连着写（不分段、不分点）」）：拆了就把一轮答话切成两段。
# 两类都是"声明即口径"（用户口径 2026-09-19）；超长仍由 _overlong_issue 记录，只是不再机械拆分。
_NO_SPLIT_SECTION_RE = re.compile(r"不再分段|不拆段|不分段")


def _no_split_sections(template: str) -> set[str]:
    """模板中声明「不再分段」的栏名（归一化）——这些栏跳过确定性拆段。"""
    out: set[str] = set()
    title = ""
    for line in (template or "").splitlines():
        s = line.strip()
        head = _HEADING_RE.match(s) if s else None
        if head:
            if len(head.group(1)) == 1:
                title = _norm_heading(head.group(2))
            continue
        if title and _NO_SPLIT_SECTION_RE.search(line):
            out.add(title)
    return out


def _is_non_prose_line(body: str) -> bool:
    """该行不是散文段（标题/表格/引用/列表项/**问答轮次**）→ 不参与段落字数上限。

    两处口径都是实测定的，改动前请一起看清：
    - 2026-09：`**发言人**：…` 曾被旧判定 `startswith("*")` 当条目行跳过，导致「每段 ≤400 字」
      对问答栏完全失效（742 字答话既不报超限也不拆段）——那一轮要求把它纳入段落上限。
    - 2026-09-18 用户口径：**一问一答＝一条记录，各占一段，再长也不拆段、不分点**。
      所以这里改成「称呼行＝对话轮次，按非散文处理」：既不拆段也不报超长
      （长度提示仍留在模板说明里，由模型自己收敛）。概况/背景等普通散文段不受影响。
    """
    if body.startswith(("#", "|", ">", "-", "+")):
        return True
    if _DIALOGUE_LINE_RE.match(body):
        return True
    return bool(_STAR_BULLET_RE.match(body))



def extract_labeled_json(text: str, label: str) -> dict[str, Any] | None:
    """从 ``{label}：\\n{...json...}`` 块解析对象。"""
    if not text:
        return None
    for marker in (f"{label}：\n", f"{label}:\n", f"{label}：", f"{label}:"):
        idx = text.find(marker)
        if idx >= 0:
            rest = text[idx + len(marker) :]
            break
    else:
        return None
    start = rest.find("{")
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(rest[start:])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if item is None:
            continue
        s = str(item).strip()
        if s:
            out.append(s)
    return out


_MODE_PREFIXES = ("视角模式：", "视角模式:")
_SUBSET_MODES = frozenset({"role_template", "personal"})
_MATCH_KEEP = 0.8


def parse_perspective_mode(shared_context: str | None) -> str:
    """从共享上下文头读取视角模式；读不到则按客观全量处理。"""
    for raw in (shared_context or "").splitlines()[:12]:
        line = raw.strip()
        for prefix in _MODE_PREFIXES:
            if line.startswith(prefix):
                mode = line[len(prefix) :].strip().lower()
                if mode in {"objective", "role_template", "personal"}:
                    return mode
                return "objective"
    return "objective"


def _norm_item(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip())


def _match_score(draft_item: str, upstream_item: str) -> float:
    a, b = _norm_item(draft_item), _norm_item(upstream_item)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        if len(shorter) >= 6 or (len(longer) and len(shorter) / len(longer) >= 0.4):
            return 0.92
        return 0.4
    sa, sb = set(a), set(b)
    jaccard = len(sa & sb) / max(len(sa | sb), 1)
    if min(len(a), len(b)) >= 16 and jaccard >= 0.72:
        return 0.8
    return jaccard


def subset_upstream_items(upstream: Any, draft: Any) -> list[str]:
    """职业/真人下采：只保留草稿选中的上游条目（不得增改）。

    对不上任何上游条目则回退为全量，避免空裁剪丢掉底座。
    选中条目按上游原序、上游原文返回。
    """
    up = _as_str_list(upstream)
    selected = _as_str_list(draft)
    if not up:
        return []
    if not selected:
        return up
    used: set[int] = set()
    picked: list[int] = []
    for item in selected:
        best_i = -1
        best = _MATCH_KEEP
        for i, src in enumerate(up):
            if i in used:
                continue
            score = _match_score(item, src)
            if score > best:
                best = score
                best_i = i
        if best_i >= 0:
            used.add(best_i)
            picked.append(best_i)
    if not picked:
        return up
    return [up[i] for i in sorted(picked)]


def enforce_upstream_carry(
    draft: dict[str, Any],
    upstream: dict[str, Any] | None,
    field_map: dict[str, str],
    *,
    headline_field: str | None = None,
    purpose_field: str | None = None,
) -> dict[str, Any]:
    """把 draft 中的搬运字段强制设为 upstream 对应列表的拷贝。

    Args:
        draft: 模型草稿 dict（会被拷贝后修改）
        upstream: 上游理解结果 dict
        field_map: {草稿字段名: 上游字段名}，如
            {"key_decisions": "decisions", "risks_and_blockers": "risks"}
        headline_field / purpose_field: 若 headline 为空，用 purpose 填充
    """
    out = dict(draft or {})
    upstream = upstream or {}
    for dst, src in field_map.items():
        out[dst] = _as_str_list(upstream.get(src))
    if headline_field and purpose_field:
        hl = str(out.get(headline_field) or "").strip()
        if not hl:
            purpose = str(upstream.get(purpose_field) or "").strip()
            out[headline_field] = purpose or "会议纪要"
    return out


# 纪要线默认搬运映射（配置，不是散落的 if 业务逻辑）
MINUTES_CARRY_MAP: dict[str, str] = {
    "key_decisions": "decisions",
    "risks_and_blockers": "risks",
    "unresolved_questions": "open_questions",
}


def enforce_minutes_draft(
    draft: dict[str, Any] | Any,
    understanding: dict[str, Any] | None,
    *,
    mode: str = "objective",
) -> dict[str, Any]:
    """纪要草稿硬对齐：搬运字段措辞以会议理解为准。

    客观：三项全量拷贝。职业/真人：按草稿下采（只删不改），对不上则回退全量。
    """
    if hasattr(draft, "model_dump"):
        data = draft.model_dump()
    elif isinstance(draft, dict):
        data = dict(draft)
    else:
        data = dict(draft)
    out = enforce_upstream_carry(
        data,
        understanding,
        MINUTES_CARRY_MAP,
        headline_field="headline",
        purpose_field="meeting_purpose",
    )
    if (mode or "objective").strip().lower() not in _SUBSET_MODES:
        return out
    upstream = understanding or {}
    for dst, src in MINUTES_CARRY_MAP.items():
        out[dst] = subset_upstream_items(upstream.get(src), data.get(dst))
    return out


_EMPTY_CELLS = frozenset(
    {"", "未提及", "未明确", "未提供", "未给出", "暂无", "待定", "无", "—", "-", "N/A", "n/a"}
)
# 「原文未提及」「暂未明确」这类框架式缺省说明（整条/整句都是它才算空）
_DEFAULT_ONLY_RE = re.compile(
    r"^(?:原文|本次|本栏|文中|此处)?(?:也|均|尚|暂|都)?(?:未提及|未明确|未提供|未给出|没有提及|无提及|暂无|待定|不明确|未涉及|未写|无)[。.；;]?$"
)


def _is_default_only(s: str) -> bool:
    """文本是否只是缺省词/框架式缺省说明（没有任何实际信息）。"""
    t = re.sub(r"[\s*`>#|()（）\[\]【】]+", "", s or "")
    if not t:
        return True
    return bool(_DEFAULT_ONLY_RE.match(t))


def _item_default_only(line: str) -> bool:
    """`- **过敏史**：未提及。` 这类整条只有缺省词的条目（只去行首列表符号，保留加粗标记）。"""
    s = re.sub(r"^\s*[-*>+•]\s+", "", line or "").strip()
    if not s:
        return True
    s = re.sub(r"^\*\*[^*]{1,16}\*\*\s*[:：]?", "", s)  # 去掉行首标签
    return _is_default_only(s)


# 表格对齐分隔行（`| --- | --- |`）；数据行判定一律用它排除
_TABLE_SEP_ROW_RE = re.compile(r"^\|[\s:\-|]+\|$")


def _row_all_empty_cells(row_line: str) -> bool:
    """整行单元格都是缺省词/空（`| 未提及 | — | … |`）——表格里的"没有"。"""
    cells = [c.strip() for c in (row_line or "").strip().strip("|").split("|")]
    return bool(cells) and all(c in _EMPTY_CELLS for c in cells)


def _table_default_keep_idx(body_lines: list[str]) -> set[int]:
    """表格「删到只剩表头」时保留首行缺省数据行，返回要保留的行下标。

    口径与栏级一致：整节/整栏都没有内容时保留一行缺省词——"没有"本身是信息。
    为什么（2026-09-19 就医咨询实测）：原文没有用药明细 → 模型留空表 → 程序自己写入缺省
    占位行（`| 未提及 | — | … |`）→ 本删除步把占位行删掉 → 门禁判「表格无有效数据行」
    （硬伤，模型无法修复：源里本就没有药名/剂量）→ 填充内部门禁重试 3 次 → 转自由渲染 →
    扩写两轮 + 修补一轮 + 再 3 次填充 → 单次渲染 10 次 LLM 调用、整单 115.8s 仍降级。
    """
    keep: set[int] = set()
    block: list[int] = []
    for idx, line in enumerate([*body_lines, ""]):  # 末尾补一行冲掉最后一块
        s = (line or "").strip()
        if s.startswith("|"):
            block.append(idx)  # 分隔行也留在块内：它会把表头与数据行切开
            continue
        if block:
            rows = [
                i
                for i in block
                if not _TABLE_SEP_ROW_RE.match(body_lines[i].strip())
            ]
            if len(rows) >= 2:  # 表头 + 至少一行数据
                data = rows[1:]
                if all(_row_all_empty_cells(body_lines[i]) for i in data):
                    keep.add(data[0])
        block = []
    return keep


def strip_default_only_content(text: str) -> tuple[str, list[str]]:
    """省略"只有缺省词"的内容：表格整行、正文整条、独立缺省句（**只删不改字**）。

    决策口径（2026-09-18 用户确认）：
    - 整节/整栏都没有内容时**保留**（标题 + 一行缺省词）——"没有"本身是信息；
    - 表格单元格保留（表格要对齐），只删"整行全缺省"；**整表都是缺省行时保留首行**
      （2026-09-19 补：否则门禁会判「表格无有效数据行」硬伤，而源里本就没有数据）；
    - 句子级只删"整句 ≤ 20 字且只是缺省说明"，并列/从句里的缺省词不动（避免语病）。
    """
    if not text:
        return text, []
    removed = 0

    def strip_body(body_lines: list[str]) -> tuple[list[str], int]:
        """行级 + 句子级删除，返回 (剩余行, 删除数)。"""
        n = 0
        keep_rows = _table_default_keep_idx(body_lines)
        kept_lines: list[str] = []
        for idx, line in enumerate(body_lines):
            s = line.strip()
            if idx in keep_rows:
                kept_lines.append(line)
                continue
            if s.startswith("|") and not _TABLE_SEP_ROW_RE.match(s):
                cells = [c.strip() for c in s.strip("|").split("|")]
                if cells and all(c in _EMPTY_CELLS for c in cells):
                    n += 1
                    continue
            elif re.match(r"^[-*+>]\s", s) and _item_default_only(s):
                n += 1
                continue
            kept_lines.append(line)
        sent_lines: list[str] = []
        for line in kept_lines:
            s = line.strip()
            if not s or re.match(r"^[#|>*+-]", s):
                sent_lines.append(line)
                continue
            kept: list[str] = []
            dropped = False
            for sent in re.split(r"(?<=[。；;])", line):
                if sent.strip() and len(sent.strip()) <= 20 and _is_default_only(sent):
                    n += 1
                    dropped = True
                    continue
                kept.append(sent)
            joined = "".join(kept)
            if joined.strip() or not dropped:
                sent_lines.append(joined)
            # 整行被清空：不额外计数（已按句计过），也不保留空行
        return sent_lines, n

    out: list[str] = []
    body: list[str] = []

    def close_section() -> None:
        nonlocal body, removed
        if not body:
            return
        stripped, n = strip_body(body)
        removed += n
        if n == 0:
            out.extend(body)
        elif any(b.strip() and not _is_default_only(b) for b in stripped):
            out.extend(stripped)          # 还有实际内容 → 用删完的版本
        elif any(b.strip() for b in stripped):
            out.extend(stripped)          # 只剩缺省词（整栏缺省）→ 保留
        else:
            out.append("未提及")           # 整节被清空 → 保留标题 + 一行缺省词
            if any(not b.strip() for b in body):  # 原体含空行 → 保留节间分隔
                out.append("")
        body = []

    for line in text.splitlines():
        if _HEADING_RE.match(line.strip()):
            close_section()
            out.append(line)
            continue
        body.append(line)
    close_section()

    result = "\n".join(out).rstrip()
    if text.endswith("\n"):
        result += "\n"
    line_delta = max(0, len(text.splitlines()) - len(result.splitlines()))
    total = removed + line_delta
    notes = [f"已省略 {total} 处只有缺省词的内容"] if total else []
    return result, notes


def _row_nonempty(row_line: str) -> bool:
    cells = [c.strip() for c in row_line.strip().strip("|").split("|")]
    if not any(cells):
        return False
    # 全是缺省词/空 视为无效（口径与 _row_confidence_score 共用；原先漏了「未明确」，
    # 导致就医咨询那种整行「未明确」被当数据行保留）
    return any(c not in _EMPTY_CELLS for c in cells)


def _row_confidence_score(row_line: str) -> tuple[int, int]:
    cells = [c.strip() for c in row_line.strip().strip("|").split("|")]
    text = " ".join(cells)
    empty_markers = {"", "未提及", "未明确", "无", "暂无", "—", "-", "N/A", "n/a"}
    meaningful = [c for c in cells if c not in empty_markers]
    score = 0
    score += len(meaningful) * 10
    score += min(len(re.findall(r"[\u4e00-\u9fff]", text)), 80)
    score += 12 if re.search(r"\d|月|日|周|前|后|截止|完成|负责人|负责", text) else 0
    score += 10 if re.search(r"张|王|李|赵|钱|孙|周|吴|郑|陈|林|刘|黄|负责人|团队|部门", text) else 0
    score += 8 if re.search(r"风险|阻塞|延期|超时|缺口|问题|影响|应对|缓解", text) else 0
    score -= 30 * sum(1 for c in cells if c in empty_markers)
    score -= 20 if re.search(r"待确认|不确定|可能|大概|似乎", text) else 0
    return score, len(text)


def apply_table_row_limits(text: str, template: str) -> tuple[str, list[str]]:
    """按模板约束硬截断表行、去掉空行；空表写一行占位。

    约束来自模板固定文字中的「约 N 行」等（通用解析），不绑定栏目名。
    """
    text = fix_glued_table_rows(text or "")
    notes: list[str] = []
    constraints = extract_template_table_constraints(template)
    tables = extract_markdown_tables(text)
    if not tables:
        return text, notes

    lines = text.splitlines(keepends=True)

    # 从后往前改，避免行号漂移
    for ti in range(len(tables) - 1, -1, -1):
        t = tables[ti]
        limit = None
        title = t.get("section_title") or f"表{ti + 1}"
        if ti < len(constraints):
            limit = constraints[ti].get("row_limit")
            title = constraints[ti].get("section_title") or title

        header_i = t["start_line"]
        # 数据行：header + sep + rows
        data_start = header_i + 2
        data_end = data_start + len(t["rows"])
        if data_start > len(lines):
            continue

        raw_rows = t["rows"]
        nonempty = [r for r in raw_rows if _row_nonempty(r)]
        if isinstance(limit, int) and limit > 0 and len(nonempty) > limit:
            notes.append(f"「{title}」按置信度取舍：{len(nonempty)}→{limit} 行")
            ranked = sorted(
                enumerate(nonempty),
                key=lambda item: (_row_confidence_score(item[1]), -item[0]),
                reverse=True,
            )
            keep_idx = sorted(idx for idx, _ in ranked[:limit])
            nonempty = [nonempty[idx] for idx in keep_idx]
        if not nonempty:
            # 按表头列数生成占位行；缺省词固定「未提及」（模板声明的缺省词由模型侧优先保证）
            cols = [c.strip() for c in t["header"].strip().strip("|").split("|")]
            cols = [c for c in cols if c != ""]
            n = max(len(cols), 1)
            placeholder_cells = ["未提及"] + ["—"] * (n - 1)
            nonempty = ["| " + " | ".join(placeholder_cells) + " |"]
            notes.append(f"「{title}」空表已写入占位行")

        # 替换数据行块。插入前先保证**上一行以换行结尾**：上游步骤会 strip 掉文末换行，
        # 否则占位行会粘在分隔行后面（`| --- |…|| 未提及 |…|` → 整块被当分隔行丢掉，
        # 表格仍被判「无有效数据行」；2026-09-19 就医咨询复现）。
        if data_start > 0 and not lines[data_start - 1].endswith("\n"):
            lines[data_start - 1] = lines[data_start - 1] + "\n"
        new_data = [r.rstrip("\r\n") + "\n" for r in nonempty]
        lines[data_start:data_end] = new_data

    return "".join(lines), notes


def clean_template_render_text(text: str) -> tuple[str, list[str]]:
    """Clean harmless template-render artifacts without changing factual content."""
    if not text:
        return "", []
    notes: list[str] = []
    lines = (text or "").splitlines()
    cleaned: list[str] = []
    removed_slash = False
    removed_dup = False
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.strip() == "\\":
            removed_slash = True
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if m:
            heading_text = re.sub(r"\s+", "", m.group(2))
            j = i + 1
            while j < len(lines) and (
                not lines[j].strip() or lines[j].strip() == "\\"
            ):
                j += 1
            if (
                j < len(lines)
                and len(heading_text) >= 24
                and re.sub(r"\s+", "", lines[j].strip()) == heading_text
            ):
                removed_dup = True
                i += 1
                continue
        cleaned.append(line)
        i += 1
    if removed_slash:
        notes.append("已清理模板输出中的单独反斜杠行")
    if removed_dup:
        notes.append("已清理标题占位误填导致的相邻重复段落")
    return "\n".join(cleaned).strip(), notes


def normalize_blank_lines(text: str) -> str:
    """标题行与表格块前后统一补空行（**只加空行，不改字、不删行**）。

    为什么需要（2026-09-20 用户实测）：装配层打印 `# 栏名` 后直接拼模型正文（正文常以
    `## 组名` 或 `- ` 开头），产物里 **76% 的标题行与下一行紧贴**（667 个标题中 507 个）：
    `# 栏名→正文` 124 个、`# 栏名→## 组名` 79 个、`## 组名→条目/段` 304 个。CommonMark
    允许"标题后直接跟段落/列表"，但**按空行分块的渲染器（查看器、粘贴到 Excel）会把下一行
    并进标题**，看起来"所有内容都成了一级标题"。补空行对所有渲染器无害，属渲染规范，
    不该交给模型（执行不稳且白吃 token）。

    规则：① 标题行之后、下一行非空 → 补空行；② 标题行之前、上一行非空 → 补空行；
    ③ 表格块（表头＋分隔＋数据行）前后各补一个空行；④ **表格块内部绝不插空行**（会把表断开）。
    """
    if not text:
        return text
    lines = text.splitlines()
    total = len(lines)

    def _is_heading(s: str) -> bool:
        t = s.strip()
        return bool(t) and bool(_HEADING_RE.match(t))

    def _is_row(s: str) -> bool:
        t = s.lstrip()
        return bool(t) and t.startswith("|")

    out: list[str] = []
    for i, line in enumerate(lines):
        cur = line.strip()
        nxt = lines[i + 1].strip() if i + 1 < total else ""
        prv = out[-1].strip() if out else ""
        interior = _is_row(cur) and _is_row(prv)  # 表格块内部（表头/分隔/数据行之间）
        if not interior and prv and (_is_heading(cur) or _is_row(cur)):
            out.append("")  # 标题 / 表格块首行之前
        out.append(line)
        if (
            nxt
            and (_is_heading(cur) or _is_row(cur))
            and not (_is_row(cur) and _is_row(nxt))
        ):
            out.append("")  # 标题 / 表格块末行之后
    result = "\n".join(out)
    if text.endswith("\n"):
        result += "\n"
    return result


def classify_issues(issues: list[str]) -> tuple[list[str], list[str]]:
    """拆成 (hard, soft)。"""
    hard: list[str] = []
    soft: list[str] = []
    for issue in issues:
        if any(m in issue for m in HARD_ISSUE_MARKERS):
            hard.append(issue)
        elif "超出" in issue:
            # 行数超出：硬截断后通常可消；截断前算 soft 提醒
            soft.append(issue)
        else:
            soft.append(issue)
    return hard, soft


def _split_one_paragraph(line: str, cap: int) -> list[str]:
    """按句界把一行拆成多段（每段 ≤ cap 汉字）；拆不动（单句超长）时原样返回。"""
    sentences = [s for s in re.split(r"(?<=[。！？；!?;])", line) if s.strip()]
    if len(sentences) < 2:
        return [line]
    out: list[str] = []
    buf = ""
    for sentence in sentences:
        candidate = f"{buf}{sentence}" if buf else sentence
        if buf and _han_count(candidate) > cap:
            out.append(buf)
            buf = sentence
        else:
            buf = candidate
    if buf:
        out.append(buf)
    return out if len(out) > 1 else [line]


def split_overlong_paragraphs_except_first(
    text: str, template: str
) -> tuple[str, list[str]]:
    """同 :func:`split_overlong_paragraphs`，但**跳过总述栏（首个 `# 栏名`）**。

    模板声明「一段写完」的首栏刚被合并成一段（用户口径：一段不拆），
    若不跳过，拆段函数会立刻把它拆回多段——两条规则打架（实测 89d781 项目概况）。
    其余栏照常拆。
    """
    lines = (text or "").splitlines(keepends=True)
    first_end = None
    seen_first = False
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("# ") and not s.startswith("## "):
            if not seen_first:
                seen_first = True
                continue
            first_end = i
            break
    if not seen_first or first_end is None:
        # 只有一栏或没有标题：整个就是首栏 → 完全不拆
        return text, []
    # 头段（首个栏名 + 其正文）原样保留——它就是"一段写完"的总述栏
    head_text = "".join(lines[:first_end])
    tail_text, tail_notes = split_overlong_paragraphs(
        "".join(lines[first_end:]), template
    )
    return head_text + tail_text, tail_notes


def split_overlong_paragraphs(text: str, template: str) -> tuple[str, list[str]]:
    """按模板声明的字数上限把超长散文段按句界拆开（**只加换行，不改文字**）。

    为什么需要（2026-09 性能复盘）：段落字数上限真生效后，`_overlong_issue` 会报
    「超出段落字数上限」，而渲染层原先对**任何** gate issue 都触发一次整篇重渲染
    （实测一条多花 30–60s）。形态问题用确定性拆分解决更划算：拆完重新过门禁即可，
    零额外 LLM 调用；拆不动（整段一句话）才留给上层兜底。

    只处理散文行（非标题/表格/引用/列表）。阈值分两种：
    - 段落级预算（「每段 ≤N 字」）：单段 > N×1.2 才拆（保留"约"的容差）；
    - 节级预算（「本栏约 N 字」，2026-09-18 补）：单段 > N 即拆——节上限本就是
      任何单段定义上的上界，实测「访谈概述」曾写出 418–517 字单段且静默不拆。
    """
    if not text or not template:
        return text, []
    limits: dict[str, tuple[int, float]] = {}
    for item in parse_section_char_budgets(template):
        hi = item.get("hi")
        if not hi:
            continue
        key = _norm_heading(str(item.get("title") or ""))
        para = str(item.get("scope") or "section") == "paragraph"
        limits[key] = (int(hi), 1.2 if para else 1.0)
    if not limits:
        return text, []
    no_split = _no_split_sections(template)

    notes: list[str] = []
    out: list[str] = []
    cur = ""
    top = ""  # 最近的一级标题（`# 栏名`）：子标题查不到预算时沿用它
    for line in text.splitlines():
        head = _HEADING_RE.match(line.strip()) if line.strip() else None
        if head:
            level = len(head.group(1))
            name = _norm_heading(head.group(2))
            if level == 1:
                top = name
            cur = name
            out.append(line)
            continue
        body = line.strip()
        if no_split and (top in no_split or cur in no_split):
            # 该栏声明「不再分段」（子标题继承父栏声明）：整栏不拆
            out.append(line)
            continue
        rule = limits.get(cur)
        if rule is None and cur:
            rule = next((v for k, v in limits.items() if k and (k in cur or cur in k)), None)
        if rule is None and top and top != cur:
            # 子标题（如 `## 08:00-12:30 现场检查`）继承父节预算：否则带子标题的栏目
            # 段落上限整体失效（实测 823 字单段不拆、也不报超限）
            rule = limits.get(top)
            if rule is None:
                rule = next(
                    (v for k, v in limits.items() if k and (k in top or top in k)), None
                )
        cap, ratio = rule if rule else (None, 1.0)
        if (
            cap
            and body
            and not _is_non_prose_line(body)
            and _han_count(body) > cap * ratio
        ):
            parts = _split_one_paragraph(body, cap)
            if len(parts) > 1:
                notes.append(
                    f"「{top or cur}」超长段（{_han_count(body)} 字）已按句界拆成 {len(parts)} 段",
                )
                out.append("\n\n".join(parts))
                continue
        out.append(line)
    return "\n".join(out), notes


def _top_level_sections(text: str) -> list[tuple[str, str]]:
    """按**一级标题**归并节：子标题（`##`/`###`）并入其父节正文。

    为什么（2026-09-18 实测）：`split_markdown_sections` 按任意级标题切分，
    `## 时间段 板块名` 会把 [分段速览] 的内容切成一个个无名小节 → 父节的字数预算
    查不到任何正文 → 该栏的段落上限检查整体失效（823 字单段原样通过）。
    """
    try:
        from tools.templates.template_eval import split_markdown_sections
    except Exception:  # noqa: BLE001
        return []
    merged: list[tuple[str, list[str]]] = []
    for title, body in split_markdown_sections(text or ""):
        first = next((ln for ln in body.splitlines() if ln.strip()), "")
        if first.strip().startswith("# ") or not merged:
            merged.append((title, [body]))
        else:
            merged[-1][1].append(body)
    return [(title, "\n".join(parts)) for title, parts in merged]


# 「一段写完，约 N–M 字」：总述栏（首栏）单段口径——模型写成多段时由程序合并成一段
_FIRST_COL_PARA_RE = re.compile(
    r"[（(]一段写完[，,]?\s*约?\s*\d+\s*[–—-]\s*\d+\s*字[)）]"
)


def _merge_first_column_paragraphs(text: str, template: str) -> tuple[str, str | None]:
    """总述栏（首栏）声明了「一段写完」时，把栏内多个段块合并成一段（确定性拼装）。

    为什么在 enforce 里做：拆段函数只看"单段超上限"，模型把首栏拆成 3 段每段 ≤400
    （合计 981 字）时既不拆也不报——"段数"从来没有程序约束。合并是零 LLM 调用的
    确定性手段，配合 prompt 里的字数口径把首栏压回一段。

    首栏定位：取**第一个其正文含散文段块的一级栏**——先收集所有一级标题（`# `，
    不含 `## `）的行号，逐栏看正文；文档主标题（`# 项目进度会`，正文为空）自然跳过。
    栏内表格行/列表/引用不动，只合并散文段块。
    """
    m = _FIRST_COL_PARA_RE.search(template or "")
    if not m:
        return text, None
    lines = (text or "").splitlines(keepends=True)

    def _is_h1(line: str) -> bool:
        s = line.strip()
        return s.startswith("# ") and not s.startswith("## ")

    h1s = [i for i, ln in enumerate(lines) if _is_h1(ln)]
    if not h1s:
        return text, None

    def _prose_blocks(seg: list[str]) -> list[list[str]]:
        blocks: list[list[str]] = []
        cur: list[str] = []
        for line in seg:
            if not line.strip():
                if cur:
                    blocks.append(cur)
                    cur = []
                continue
            blocks.append(cur) if False else None
            cur.append(line)
        if cur:
            blocks.append(cur)
        return [
            b
            for b in blocks
            if not any(
                ln.strip().startswith(("#", "|", ">", "-", "+", "*")) for ln in b
            )
        ]

    # 首栏定位（2026-09-20 收紧）：只认**第一个有正文的一级栏**——文档主标题（正文为空）
    # 跳过，其后遇到的第一栏即首栏，**只判断这一栏**、不再向后扫描其它栏。
    # 为什么改：旧实现"取第一个含 ≥2 段块的一级栏"在首栏只有 1 段时（[全文摘要] 本就要求
    # 一段写完，这是常态）会顺延到第 2 栏，把 [分段速览] 当总述栏合并——实测 10 个时间段
    # 被并成 1914 字一段（删空行、句间塞空格，不可逆）。名字叫 first-column merge，
    # 管到第 2 栏就是越界。
    first: tuple[int, int, list[str]] | None = None
    for k, h in enumerate(h1s):
        seg_end = h1s[k + 1] if k + 1 < len(h1s) else len(lines)
        body = lines[h + 1 : seg_end]
        if any(ln.strip() for ln in body):
            first = (h, seg_end, body)
            break
    if first is None:
        return text, None
    _h_idx, end, body = first
    start = _h_idx + 1
    first_title = lines[_h_idx].strip().lstrip("# ").strip() or "首栏"
    # 保险①：该栏声明过「不再分段」→ 跳过（两道独立判据同时失效才会误伤）
    if _norm_heading(first_title) in _no_split_sections(template):
        return text, None
    blocks = _prose_blocks(body)
    if len(blocks) < 2:
        return text, None

    merged_text = ""
    for j, b in enumerate(blocks):
        chunk = "".join(b).strip()
        merged_text += chunk if j == 0 else " " + chunk
    tail_newline = "\n" if lines[end - 1].endswith("\n") else ""
    new_block = merged_text + ("\n\n" if tail_newline else "\n")
    out = lines[:start] + [new_block] + lines[end:]
    return (
        "".join(out),
        f"「{first_title}」为总述栏（一段写完）：已把 {len(blocks)} 段合并成一段",
    )


def enforce_render_output(
    template: str,
    output: str,
) -> tuple[str, list[str], list[str]]:
    """对渲染正文做强执行：粘连修复 + 行数截断 + 评测。

    Returns:
        (enforced_text, enforce_notes, remaining_issues)
    """
    if not template or not (output or "").strip():
        return output or "", [], (["输出为空"] if not (output or "").strip() else [])

    from tools.template_router import (
        detect_template_kind,
        validate_rendered_output,
    )

    notes: list[str] = []
    text = fix_glued_table_rows(output)
    if text != output:
        notes.append("已修复表格行粘连（||）")
    text2, cnotes = clean_template_render_text(text)
    text = text2
    notes.extend(cnotes)

    # 总述栏一段化：模型把「一段写完」的首栏写成多段时，确定性合并（零 LLM 调用）
    text2, mnote = _merge_first_column_paragraphs(text, template)
    if mnote:
        text = text2
        notes.append(mnote)

    # 剔除误包的外层代码围栏 + 字数元说明
    try:
        from tools.template_router import (
            strip_char_budget_meta,
            strip_outer_markdown_fence,
        )

        unfenced = strip_outer_markdown_fence(text)
        if unfenced.strip() != text.strip():
            notes.append("已剥离外层 Markdown 代码围栏")
        text = unfenced
        cleaned = strip_char_budget_meta(text)
        if cleaned != text:
            notes.append("已剔除字数元说明")
            text = cleaned
    except Exception:  # noqa: BLE001
        pass

    if detect_template_kind(template) == "placeholder":
        text2, tnotes = apply_table_row_limits(text, template)
        text = text2
        notes.extend(tnotes)

    # 只有缺省词的内容不展示（表格整行/正文整条/独立缺省句）；整节都没内容时保留一行缺省词
    text2, dnotes = strip_default_only_content(text)
    if dnotes:
        text = text2
        notes.extend(dnotes)

    # 段落字数超限：确定性按句界拆段（只加换行），避免上层为篇幅问题整篇返工。
    # 总述栏例外：模板声明「一段写完」的栏刚被合并成一段，用户口径是一段不拆——
    # 拆段跳过该栏（否则合并完又被拆回 3 段，两条规则打架；实测 89d781 项目概况）。
    if _FIRST_COL_PARA_RE.search(template or ""):
        text2, snote_list = split_overlong_paragraphs_except_first(text, template)
    else:
        text2, snote_list = split_overlong_paragraphs(text, template)
    text = text2
    notes.extend(snote_list)

    # 标题/表格块前后统一补空行（只加空行、不改字）：装配层打印 `# 栏名` 后直接拼模型正文
    # （正文常以 `## 组名` 或 `- ` 起），实测 76% 的标题与下一行紧贴——按空行分块的渲染器
    # （查看器/粘贴 Excel）会把下一行并进标题，看起来"所有内容都成了一级标题"（2026-09-20）。
    text = normalize_blank_lines(text)

    struct = validate_rendered_output(text, template)
    eval_issues = evaluate_output_against_template(template, text)
    # 截断后行数超出类问题应消失，过滤已被强制处理的
    remaining = []
    for issue in list(dict.fromkeys(struct + eval_issues)):
        if "超出" in issue and any(("硬截断" in n or "取舍" in n) for n in notes):
            continue
        remaining.append(issue)
    return text, notes, remaining


def truncate_to_budget(text: str, hi: int, *, ratio: float = 1.05) -> str:
    """按句子边界截断到约 hi 字（保完整句，宁少勿多）。

    LLM 压缩仍有极限（对汉字数感知不准），作为字数门禁的最终兜底：
    优先整句保留（句号/分号/换行切句），超出部分丢弃；
    极端情况（连一个完整句都放不下）退回字符硬截断。
    """
    if not text:
        return ""
    han = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    if han <= hi * ratio:
        return text
    parts = re.split(r"(?<=[。！？；!?;])|\n", text)
    buf: list[str] = []
    total = 0
    for part in parts:
        part_han = sum(1 for ch in part if "\u4e00" <= ch <= "\u9fff")
        if buf and total + part_han > hi * ratio:
            break
        buf.append(part)
        total += part_han
    out = "".join(buf).strip()
    return out if out else text[:hi]


def gate_render_output(
    template: str,
    output: str,
) -> dict[str, Any]:
    """验收门禁结果。

    Returns dict:
        text, notes, issues, hard_issues, soft_issues, gate_ok
    """
    text, notes, issues = enforce_render_output(template, output)
    issues.extend(empty_section_issues(text, template))
    over = _overlong_issue(template, text)
    if over:
        issues.append(over)
    hard, soft = classify_issues(issues)
    # 咨询级检查（超长条/段、缺失说明句）：单独一栏，不进 issues/hard，不触发返工
    advisory = advisory_issues(text)
    # 再跑一轮：若仅有「超出」且已截断，gate 可通过
    gate_ok = len(hard) == 0
    return {
        "text": text,
        "notes": notes,
        "issues": issues,
        "hard_issues": hard,
        "soft_issues": soft,
        "advisory_issues": advisory,
        "gate_ok": gate_ok,
    }


def _han_count(text: str) -> int:
    return sum(1 for ch in (text or "") if "\u4e00" <= ch <= "\u9fff")


_LONG_ITEM_HAN = 200
_META_SENTENCE_RE = re.compile(
    r"原文(?:中|里)?\s*(?:未|没有|无)\s*(?:明确|提及|说明|给出|写)"
)


def advisory_issues(
    text: str,
    *,
    long_han: int = _LONG_ITEM_HAN,
    para_han: int = 320,
    limit: int = 4,
) -> list[str]:
    """咨询级形态检查（超长条/段 + 缺失说明句）：**记录用，不触发返工**。

    背景（2026-09，55 行实测）：>200 字的长条/长段是 now 最突出的形态问题
    （占比 before 的 13 倍，如「一条 736 字」「课程概况 631 字一段」）；
    另有「机构信息原文未提及」这类**缺失说明句**（应只写约定缺省词）。

    阈值分层：`- ` 条目用 ``long_han``（200 字，超过即为异常）；叙述段用
    ``para_han``（默认 320 字）——它是比规格更早的预警线（概况类规格为
    "最多 3 段、每段不超过 400 字"），231–275 字的概况段属正常，
    用 200 字会把 30+ 行误报（实测 36/55），失去观察价值。

    这两类先以 advisory 记录（日志 + monitor），观察一批再决定是否升级成
    issue（触发返工）或硬伤：软问题若直接进 ``issues`` 会让几乎每行都触发
    一次整篇返工（装配稿会被自由渲染稿替换），成本与内容风险都不小。
    """
    lines = (text or "").splitlines()
    out: list[str] = []

    def _add(msg: str) -> bool:
        out.append(msg)
        return len(out) < limit

    # ① 单条超长（`- ` / `  - ` 条目行）
    for raw in lines:
        s = raw.strip()
        if not re.match(r"^-\s+\S", s):
            continue
        n = _han_count(s)
        if n <= long_han:
            continue
        label = re.sub(r"^-\s+", "", s)[:14]
        if not _add(f"「{label}…」一条 {n} 字，超过 {long_han} 字：拆成多条或缩进子条 `  - `"):
            return out
    # ② 单段超长（连续正文行组成的段落；含单行成段，`- ` 条目已在 ① 覆盖）
    para: list[str] = []
    for raw in lines + [""]:
        s = raw.strip()
        is_body = bool(s) and not s.startswith(("#", "|", ">", "-"))
        if is_body:
            para.append(s)
            continue
        if para:
            n = _han_count("".join(para))
            if n > para_han:
                if not _add(f"「{para[0][:14]}…」一段 {n} 字，超过 {para_han} 字：拆段或改用 `- ` 分点"):
                    return out
        para = []
    # ③ 缺失说明句（"原文未提及…"这类应只写约定缺省词）
    for raw in lines:
        m = _META_SENTENCE_RE.search(raw)
        if m:
            if not _add(f"正文出现缺失说明句「{m.group(0)}」：缺内容只写约定缺省词，不写说明句"):
                return out
    return out


def _norm_heading(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().strip("[]"))


def empty_section_issues(text: str, template: str = "", *, limit: int = 5) -> list[str]:
    """光杆标题检查：某小节整棵子树里没有任何正文 → 报「只有标题没有正文」。

    两条渲染路径都会留空栏：占位符拼装路径的栏目标题由程序按模板打印，字段缺失时
    就是「只有标题」；自由渲染路径模型自己也会写光杆标题。父标题只带子标题
    （正文在子节里）不算空栏；「未提及」这类约定缺省词算有正文。
    文档标题（模板首行的 ``# 中文名``，不是 ``# [栏名]`` 占位）不带正文属正常，跳过。
    """
    lines = (text or "").splitlines()
    title = ""
    for line in (template or "").splitlines():
        m = _HEADING_RE.match(line.strip())
        if m:
            if "[" not in m.group(2):  # 首行 `# 中文名`＝文档标题，不是栏目
                title = _norm_heading(m.group(2))
            break
    heads: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line.strip())
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    issues: list[str] = []
    for k, (idx, level, head) in enumerate(heads):
        if title and _norm_heading(head) == title:
            continue
        end = len(lines)
        for j, lv, _t in heads[k + 1 :]:
            if lv <= level:
                end = j
                break
        body = "\n".join(
            ln for ln in lines[idx + 1 : end] if not _HEADING_RE.match(ln.strip())
        )
        if body.strip():
            continue
        issues.append(f"「{head[:24]}」只有标题没有正文（空栏）")
        if len(issues) >= limit:
            break
    return issues


def _overlong_issue(template: str, text: str) -> str | None:
    """字数超限时返回提示（触发渲染 repair）。

    - 全文预算（「全文合计约 N 字」）才约束整篇。
    - 「本段/本栏约 N 字」只检查对应小节，不拿来压整篇。
    - 不得把段落级「约 200 字」误当成全文上限。
    """
    if not template:
        return None
    try:
        from tools.templates.template_eval import (
            parse_document_char_budget,
            parse_section_char_budgets,
        )
    except Exception:  # pragma: no cover
        return None
    full = parse_document_char_budget(template or "")
    hi = full.get("hi")
    if hi:
        han = _han_count(text)
        if han > int(hi) * 1.2:
            return (
                f"超出全文上限：当前正文约 {han} 字，全文合计约 {hi} 字，"
                f"请把整篇压缩至 {hi} 字以内（保留结论/关键数字/责任人/时限，"
                "删除过程铺陈/套话/次要细节，语句保持完整通顺）。"
            )
        return None
    sections = parse_section_char_budgets(template or "")
    if not sections:
        return None
    # 用"顶层节"（一级标题）归并：`## 时间段 板块名` 这类子标题不再把自己的小节
    # 从这里切走（否则父节预算查不到内容 → 段落检查整栏失效，2026-09-18 实测）
    rendered = _top_level_sections(text or "")
    issues: list[str] = []
    for item in sections:
        title = str(item.get("title") or "")
        cap = int(item["hi"])
        scope = str(item.get("scope") or "section")
        body = ""
        for sec_title, sec_body in rendered:
            if title and (title in sec_title or sec_title in title):
                body = sec_body
                break
        if not body:
            continue
        if scope == "paragraph":
            # 「单段不超过约 N 字」：按行核（一段通常就是一行），条目行交给其它规则
            long_lines = [
                ln.strip()
                for ln in body.splitlines()
                if _han_count(ln) > cap * 1.2
                and not _is_non_prose_line(ln.strip())
            ]
            if long_lines:
                longest = max(_han_count(ln) for ln in long_lines)
                issues.append(
                    f"「{title}」有 {len(long_lines)} 段超过 {cap} 字（最长约 {longest} 字），"
                    "拆段或改用 `- ` 分点"
                )
            continue
        han = _han_count(body)
        if han > cap * 1.2:
            issues.append(f"「{title}」约 {han} 字，本段上限 {cap} 字")
        # 节级预算的栏也要兜单段：单段超过整节上限即超（×1.0，节上限本就是单段定义上的上界），
        # 与 split_overlong_paragraphs 的节级阈值一致——实测「访谈概述」曾静默写出 418 字单段。
        long_lines = [
            ln.strip()
            for ln in body.splitlines()
            if _han_count(ln) > cap and not _is_non_prose_line(ln.strip())
        ]
        if long_lines:
            longest = max(_han_count(ln) for ln in long_lines)
            issues.append(
                f"「{title}」有 {len(long_lines)} 段超过 {cap} 字（最长约 {longest} 字），"
                "拆段或改用 `- ` 分点"
            )
    if not issues:
        return None
    return (
        "超出段落字数上限："
        + "；".join(issues)
        + "。只压缩超限的那一节，其它节和表格不要为了凑字数而删。"
        "保留结论/关键数字/责任人/时限，语句保持完整通顺。"
    )


def should_write_result_md(gate_ok: bool | None, has_template: bool) -> bool:
    """是否写正式 ``result.md`` —— **总是写**（含门禁失败）。

    实测出现过"正文合格但门禁误判"（表格写法变体被判「固定文字丢失」），此时不落盘会让
    用户拿不到可用内容 ✗。质量信号改由两条承担：API 的 ``quality_warning`` 字段
    （带上门禁原因）与同目录的 ``result_rejected.md``（备查副本）。
    """
    return True


__all__ = [
    "HARD_ISSUE_MARKERS",
    "MINUTES_CARRY_MAP",
    "advisory_issues",
    "apply_table_row_limits",
    "classify_issues",
    "empty_section_issues",
    "enforce_minutes_draft",
    "enforce_render_output",
    "enforce_upstream_carry",
    "extract_labeled_json",
    "normalize_blank_lines",
    "parse_perspective_mode",
    "split_overlong_paragraphs",
    "subset_upstream_items",
    "gate_render_output",
    "should_write_result_md",
]
