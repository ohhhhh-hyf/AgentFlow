"""模板输出通用评测（不绑定具体业务栏目）。

从模板固定文字中抽取「约 N 行 / 约 K 字」类约束，对照渲染结果做结构检查；
并修复自由渲染常见的 Markdown 表格粘连（``||`` 同行多数据行）。
"""
from __future__ import annotations

import re
from math import ceil
from typing import Any

# 通用数量词（不绑定风险/待办等栏目名）
_CN_NUM = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
_ROW_HINT_RE = re.compile(
    r"(?:不超过|最多|至多)\s*([一二三四五六七八九十\d]+)\s*行"
    r"|(?:约|大约)?\s*([一二三四五六七八九十\d]+)\s*行\s*(?:左右|上下)?"
)
_CHAR_HINT_RE = re.compile(
    r"(?:约|大约|左右)?\s*(\d+)\s*字"
    r"|(\d+)\s*字\s*(?:左右|上下)?"
)
# 区间：200-300字 / 200～300字 / 200至300字
_CHAR_RANGE_RE = re.compile(
    r"(\d+)\s*[-–—~～至到]\s*(\d+)\s*字"
)
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}")


def _to_int(token: str) -> int | None:
    token = (token or "").strip()
    if not token:
        return None
    if token.isdigit():
        n = int(token)
        return n if n > 0 else None
    return _CN_NUM.get(token)


def parse_row_hint(text: str) -> int | None:
    """从任意文本解析行数提示；解析不到返回 None（不硬编码业务）。"""
    m = _ROW_HINT_RE.search(text or "")
    if not m:
        return None
    tok = next((g for g in m.groups() if g), None)
    return _to_int(tok) if tok else None


def parse_char_hint(text: str) -> int | None:
    """解析单一字数提示；若有区间则返回上界。"""
    budget = parse_char_budget(text)
    if budget.get("hi"):
        return int(budget["hi"])
    return None


def parse_char_budget(text: str) -> dict[str, Any]:
    """从模板/描述中解析字数预算。

    Returns:
        lo: 建议下限（区间下界；单值时约 0.8x）
        hi: 目标/上限（区间上界或「约 x 字」的 x）
        cap: 软参考上限，``ceil(hi * 1.5)``——明显超过时可提示收束
        label: 可读说明
    """
    empty: dict[str, Any] = {"lo": None, "hi": None, "cap": None, "label": ""}
    raw = text or ""
    m = _CHAR_RANGE_RE.search(raw)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        lo, hi = (a, b) if a <= b else (b, a)
        cap = int(ceil(hi * 1.5))
        return {
            "lo": lo,
            "hi": hi,
            "cap": cap,
            "label": f"约{lo}-{hi}字量级（内部参考，略超可接受）",
        }
    m = _CHAR_HINT_RE.search(raw)
    if not m:
        return empty
    tok = next((g for g in m.groups() if g), None)
    if not tok or not str(tok).isdigit():
        return empty
    hi = int(tok)
    lo = max(1, int(hi * 0.8))
    cap = int(ceil(hi * 1.5))
    return {
        "lo": lo,
        "hi": hi,
        "cap": cap,
        "label": f"约{hi}字量级（内部参考，略超可接受）",
    }


def parse_document_char_budget(template: str) -> dict[str, Any]:
    """解析**全文**字数预算，忽略占位符内部的「100字以内」等字段级提示。

    优先从去掉 ``[...]`` 后的固定文字/自然语言描述中解析；
    避免滤芯模板里「[…，100字以内]」被误当成全文 100 字。
    自然语言编译后常见「全文合计约200-300字」写在占位说明内，也会识别。
    """
    raw = template or ""
    # 去掉占位符内容，只保留固定文字与自然语言描述
    outer = re.sub(r"\[[^\[\]]*\]", " ", raw)
    outer = re.sub(r"[ \t]+\n", "\n", outer).strip()
    budget = parse_char_budget(outer)
    if budget.get("hi"):
        return budget
    # 首行自然语言（# 标题之前）再试一次
    first = raw.strip().splitlines()[0] if raw.strip() else ""
    if first and not first.lstrip().startswith("#"):
        budget = parse_char_budget(first)
        if budget.get("hi"):
            return budget
    # 编译后的占位符：识别「全文合计约200-300字 / 全文约 x 字」等全文级提示
    full_doc_hints = re.findall(
        r"全文(?:合计)?[^\[\]\n]{0,12}?(?:约|大约)?\s*"
        r"(?:(\d+)\s*[-–—~～至到]\s*(\d+)\s*字|(\d+)\s*字)",
        raw,
    )
    for lo_s, hi_s, single in full_doc_hints:
        if lo_s and hi_s:
            lo, hi = int(lo_s), int(hi_s)
            if lo > hi:
                lo, hi = hi, lo
            cap = int(ceil(hi * 1.5))
            return {
                "lo": lo,
                "hi": hi,
                "cap": cap,
                "label": f"约{lo}-{hi}字量级（内部参考，略超可接受）",
            }
        if single:
            hi = int(single)
            cap = int(ceil(hi * 1.5))
            return {
                "lo": None,
                "hi": hi,
                "cap": cap,
                "label": f"约{hi}字量级（内部参考，略超可接受）",
            }
    return {"lo": None, "hi": None, "cap": None, "label": ""}


def fix_glued_table_rows(text: str) -> str:
    """把同一行里用 ``||`` 粘连的多条表格数据拆成多行（通用 Markdown 修复）。"""
    if not text or "||" not in text:
        return text
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        eol = "\n" if line.endswith("\n") else ""
        body = line.rstrip("\r\n")
        # 至少像「两行粘一起」：多个单元格 + 出现 ||
        if body.count("|") < 6 or "||" not in body or _TABLE_SEP_RE.match(body):
            out.append(line)
            continue
        parts = [p.strip() for p in re.split(r"\|\s*\|", body) if p.strip()]
        if len(parts) < 2:
            out.append(line)
            continue
        rebuilt: list[str] = []
        for p in parts:
            row = p
            if not row.startswith("|"):
                row = "| " + row
            if not row.rstrip().endswith("|"):
                row = row.rstrip() + " |"
            rebuilt.append(row)
        out.append("\n".join(rebuilt) + eol)
    return "".join(out)


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return s.count("|") >= 2 and not _TABLE_SEP_RE.match(s)


def extract_markdown_tables(text: str) -> list[dict[str, Any]]:
    """解析输出中的 Markdown 表：[{header, rows, section_title, start_line}]。"""
    lines = (text or "").splitlines()
    tables: list[dict[str, Any]] = []
    i = 0
    last_heading = ""
    while i < len(lines):
        hm = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", lines[i])
        if hm:
            last_heading = hm.group(2).strip()
        # 表头 + 分隔 + 数据
        if (
            i + 1 < len(lines)
            and _is_table_row(lines[i])
            and _TABLE_SEP_RE.match(lines[i + 1].strip())
        ):
            header = lines[i].strip()
            rows: list[str] = []
            j = i + 2
            while j < len(lines) and _is_table_row(lines[j]):
                rows.append(lines[j].strip())
                j += 1
            tables.append(
                {
                    "header": header,
                    "rows": rows,
                    "section_title": last_heading,
                    "start_line": i,
                }
            )
            i = j
            continue
        i += 1
    return tables


def extract_template_table_constraints(template: str) -> list[dict[str, Any]]:
    """从模板中找「表格行模板」附近的小节标题，读取可选行数提示。"""
    lines = (template or "").splitlines()
    constraints: list[dict[str, Any]] = []
    last_heading = ""
    last_heading_full = ""
    i = 0
    while i < len(lines):
        hm = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", lines[i])
        if hm:
            last_heading = hm.group(2).strip()
            last_heading_full = lines[i]
        if (
            i + 1 < len(lines)
            and _is_table_row(lines[i])
            and _TABLE_SEP_RE.match(lines[i + 1].strip())
        ):
            # 找带占位符的数据行模板
            j = i + 2
            has_ph = False
            while j < len(lines) and _is_table_row(lines[j]):
                if "[" in lines[j] and "]" in lines[j]:
                    has_ph = True
                j += 1
            if has_ph:
                ctx = last_heading_full + "\n" + last_heading
                # 标题上下两行也扫一下
                window = "\n".join(lines[max(0, i - 3) : i + 1])
                row_limit = parse_row_hint(ctx) or parse_row_hint(window)
                constraints.append(
                    {
                        "section_title": last_heading,
                        "row_limit": row_limit,
                        "header": lines[i].strip(),
                    }
                )
            i = j
            continue
        i += 1
    return constraints


def extract_char_constraints(template: str) -> list[dict[str, Any]]:
    """从模板提取**全文级**字数提示（忽略占位内字段级「100字以内」）。"""
    out: list[dict[str, Any]] = []
    budget = parse_document_char_budget(template or "")
    if budget.get("hi"):
        out.append(
            {
                "hint": budget.get("label") or "document",
                "char_target": budget["hi"],
                "char_lo": budget["lo"],
                "char_cap": budget["cap"],
            }
        )
    return out


def evaluate_output_against_template(
    template: str,
    output: str,
    *,
    row_tolerance: int = 1,
    char_ratio_low: float = 0.4,
    char_ratio_high: float = 1.5,
) -> list[str]:
    """对照模板约束评测输出，返回问题列表（空=通过）。

    仅使用模板正文中写明的数量线索 + Markdown 结构，不绑定具体栏目名。
    """
    issues: list[str] = []
    if not (output or "").strip():
        return ["输出为空"]

    # 粘连表
    if "||" in output and re.search(r"\|\s*\|", output):
        # 允许正常单元格内没有 ||；检测「像两行粘一起」
        for line in output.splitlines():
            if line.count("|") >= 6 and "||" in line and not _TABLE_SEP_RE.match(line):
                issues.append("Markdown 表格存在同行粘连（||），应每条数据独占一行")
                break

    out_tables = extract_markdown_tables(output)
    tpl_constraints = extract_template_table_constraints(template)

    # 按顺序对齐表约束（通用：第 i 个带占位符的表 ↔ 输出第 i 张表）
    for i, cons in enumerate(tpl_constraints):
        limit = cons.get("row_limit")
        title = cons.get("section_title") or f"表{i + 1}"
        if i >= len(out_tables):
            issues.append(f"模板含表格「{title}」，输出中缺少对应表")
            continue
        n_rows = len(out_tables[i]["rows"])
        # 全空行
        nonempty = [
            r
            for r in out_tables[i]["rows"]
            if any(c.strip() for c in r.split("|") if c.strip() and c.strip() != "—")
        ]
        if n_rows == 0 or not nonempty:
            issues.append(f"「{title}」表格无有效数据行")
            continue
        if isinstance(limit, int) and limit > 0:
            if n_rows > limit + row_tolerance:
                issues.append(
                    f"「{title}」表格约需 {limit} 行，实际 {n_rows} 行（超出）"
                )
            # 有内容但明显过少（例如要求 3 行却只有 0——上面已处理；1 行且 limit>=3 可提示）
            if n_rows < max(1, limit - row_tolerance - 1) and limit >= 3 and n_rows == 1:
                # 仅当看起来像「该多却极少」时提示，避免误伤
                pass

    # 字数：正文汉字粗比（去掉标题和表）
    char_cons = extract_char_constraints(template)
    if char_cons:
        prose = []
        for line in output.splitlines():
            if _is_table_row(line) or _TABLE_SEP_RE.match(line.strip()):
                continue
            if re.match(r"^\s*#{1,6}\s+", line):
                continue
            if line.strip():
                prose.append(line.strip())
        blob = "".join(prose)
        # 优先计汉字；无汉字则退回全字符
        han = re.findall(r"[\u4e00-\u9fff]", blob)
        n = len(han) if han else len(re.sub(r"\s+", "", blob))
        target = max(c["char_target"] for c in char_cons)
        caps = [c.get("char_cap") for c in char_cons if c.get("char_cap")]
        cap = max(caps) if caps else int(target * char_ratio_high + 0.999)
        if n and n < target * char_ratio_low:
            issues.append(f"正文约需 {target} 字量级，实际约 {n} 字（偏短）")
        if n and n > cap:
            # 软提示：仅供门禁/日志参考，不写成用户可见硬条
            issues.append(
                f"正文汉字约 {n} 字，相对模板约 {target} 字量级偏长（可再收束）"
            )

    return issues


def evaluate_and_fix(
    template: str, output: str
) -> tuple[str, list[str]]:
    """先做通用表格粘连修复，再评测；返回 (fixed_output, issues)。"""
    fixed = fix_glued_table_rows(output or "")
    issues = evaluate_output_against_template(template, fixed)
    return fixed, issues


__all__ = [
    "evaluate_and_fix",
    "evaluate_output_against_template",
    "extract_char_constraints",
    "extract_markdown_tables",
    "extract_template_table_constraints",
    "fix_glued_table_rows",
    "parse_char_budget",
    "parse_document_char_budget",
    "parse_char_hint",
    "parse_row_hint",
]
