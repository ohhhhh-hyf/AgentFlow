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


def _row_nonempty(row_line: str) -> bool:
    cells = [c.strip() for c in row_line.strip().strip("|").split("|")]
    cells = [c for c in cells if c != ""]
    if not cells:
        return False
    # 全是未提及/—/空 视为无效
    meaningful = [
        c
        for c in cells
        if c not in {"未提及", "—", "-", "无", "N/A", "n/a", "暂无"}
    ]
    return bool(meaningful)


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
            # 按表头列数生成占位行
            cols = [c.strip() for c in t["header"].strip().strip("|").split("|")]
            cols = [c for c in cols if c != ""]
            n = max(len(cols), 1)
            placeholder_cells = ["未提及"] + ["—"] * (n - 1)
            nonempty = ["| " + " | ".join(placeholder_cells) + " |"]
            notes.append(f"「{title}」空表已写入占位行")

        # 替换数据行块
        new_data = []
        for r in nonempty:
            row = r.rstrip("\r\n")
            if not row.endswith("\n"):
                # lines 用 keepends，统一补 \n
                pass
            new_data.append(row + "\n")
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
    ``para_han``（默认 320 字）——概况类模板允许"4–10 句"，231–275 字的概况段
    属正常，用 200 字会把 30+ 行误报（实测 36/55），失去观察价值。

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
            split_markdown_sections,
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
    rendered = split_markdown_sections(text or "")
    issues: list[str] = []
    for item in sections:
        title = str(item.get("title") or "")
        cap = int(item["hi"])
        body = ""
        for sec_title, sec_body in rendered:
            if title and (title in sec_title or sec_title in title):
                body = sec_body
                break
        if not body:
            continue
        han = _han_count(body)
        if han > cap * 1.2:
            issues.append(f"「{title}」约 {han} 字，本段上限 {cap} 字")
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
    "parse_perspective_mode",
    "subset_upstream_items",
    "gate_render_output",
    "should_write_result_md",
]
