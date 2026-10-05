"""tools.templates.router.placeholder —— 模板路由·占位符层：占位符模板解析、填充计划与组装。"""
from __future__ import annotations
import asyncio
import contextlib
import json
import logging
import re
from typing import Any

from core.templates.body_rules import BODY_FORMAT_RULES

from ._base import (
    _TABLE_SEP_RE,
    _body_han_count,
    _char_budget_lines,
    _client_text,
    _describe_field,
    _extract_json_object,
    _hint_clean,
    _hint_short,
    _parse_row_list,
    _table_row_confidence_score,
    _TITLE_HINT_INSTRUCTION_RE,
    iter_placeholders,
    split_template_meta,
    strip_outer_markdown_fence,
    table_caption_lines,
)
from ._detect import (
    _is_placeholder_table_row,
    _looks_like_placeholder,
    _parse_field,
    _row_limit_for_template,
    detect_template_kind,
    strip_char_budget_meta,
)

logger = logging.getLogger(__name__)


def _line_placeholders(line: str) -> list[Any]:
    """行内占位符（含"整行一个占位、内容带方括号字面"的情形，见 ``iter_placeholders``）。"""
    out: list[Any] = []
    for m in iter_placeholders(line):
        nxt = line[m.end() : m.end() + 1]
        if _looks_like_placeholder(m.group(1), next_char=nxt):
            out.append(m)
    return out


_SECTION_TITLE_RE = re.compile(r"^(#{1,6})\s*\[([^\[\]]+)\]\s*$")

# 标题行上的占位（值 = 标题文字；正文写在标题下方）
_HEADING_LINE_RE = re.compile(r"^\s{0,3}#{1,6}\s")


def _section_title_match(line: str) -> re.Match[str] | None:
    """`# [项目概况]` 这类标题占位：栏名短、无句读 → 程序用栏名生成标题，不送 LLM。

    「自主概括的议程模块名称」这类是要模型起标题，不当固定栏名。
    """
    body = line.rstrip("\n")
    match = _SECTION_TITLE_RE.match(body)
    if not match:
        return None
    hint = match.group(2).strip()
    if not hint or len(hint) > 30 or "。" in hint or "，" in hint:
        return None
    if _TITLE_HINT_INSTRUCTION_RE.search(hint):
        return None
    return match


def _is_table_data_row(line: str) -> bool:
    body = line.rstrip("\n")
    if body.count("|") < 2:
        return False
    if _TABLE_SEP_RE.match(body):
        return False
    if _line_placeholders(body):
        return True
    return _is_placeholder_table_row(body)


def _table_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _ellipsis_row_fields(line: str, template: str) -> list[dict]:
    """无 [方括号] 的省略号样例行：按表头列名（或列序号）生成待填字段。"""
    n = max(len(_table_cells(line)), 1)
    headers = _table_header_cells(line, template)
    if len(headers) < n:
        headers = list(headers) + [f"列{i + 1}" for i in range(len(headers), n)]
    return [
        {
            "kind": "field",
            "raw": headers[i],
            "hint": headers[i],
            "enum": None,
            "missing": False,
        }
        for i in range(n)
    ]


def plan_placeholder_fill(template: str) -> dict[str, Any]:
    """分析模板结构（通用）：标量占位符顺序 + 表格行模板。

    表格行模板包括两类：单元格里的 ``[占位符]``，以及整行 ``| … | … |`` 样例。
    """
    template, _ = split_template_meta(template)
    scalars: list[dict] = []
    row_templates: list[dict[str, Any]] = []
    caption_lines = table_caption_lines(template)
    for idx, line in enumerate(template.splitlines(keepends=True)):
        if _section_title_match(line):
            continue
        if idx in caption_lines:
            continue  # 表格栏说明：不进字段清单（明细由下表承载，正文不另写）
        phs = _line_placeholders(line)
        if _is_table_data_row(line):
            fields = (
                [_parse_field(m.group(1)) for m in phs]
                if phs
                else _ellipsis_row_fields(line, template)
            )
            # 同一张表的**连续样例行**合并成一个行模板（表只填一组数据行，不重复展开）
            if row_templates and idx == row_templates[-1]["indices"][-1] + 1:
                row_templates[-1]["indices"].append(idx)
                continue
            header_cells = _table_header_cells(line, template)
            row_templates.append({
                "line": line,
                "fields": fields,
                "indices": [idx],
                "header_cells": header_cells,
            })
            continue
        if not phs:
            continue
        heading_line = bool(_HEADING_LINE_RE.match(line))
        for m in phs:
            field = _parse_field(m.group(1))
            if heading_line:
                field["heading"] = True
            scalars.append(field)
    first = row_templates[0] if row_templates else None
    return {
        "scalars": scalars,
        "row_templates": row_templates,
        "row_line": first["line"] if first else None,
        "row_fields": list(first["fields"]) if first else [],
    }


def normalize_fill_tables(
    tables: list[list[list[str]]],
    row_templates: list[dict[str, Any]],
) -> list[list[list[str]]]:
    """通用清洗：对齐列数、去掉整行空白、去重复表头行；若模板写了行数约束则截断。"""
    out: list[list[list[str]]] = []
    for i, rt in enumerate(row_templates):
        n_cols = max(len(rt.get("fields") or []), 1)
        raw_rows = tables[i] if i < len(tables) else []
        cleaned: list[list[str]] = []
        for row in raw_rows:
            cells = [("" if c is None else str(c).strip()) for c in row]
            if len(cells) < n_cols:
                cells.extend([""] * (n_cols - len(cells)))
            else:
                cells = cells[:n_cols]
            if not any(cells):
                continue
            cleaned.append(cells)
        # 支柱 3-2：表头数据行过滤（若模型提取的数据行与表头列名定义一致，说明误把表头当作数据行输出了）
        header_names = rt.get("header_cells") or [
            str(f.get("hint") or "").strip() for f in rt.get("fields") or []
        ]
        if header_names:
            norm_headers = [
                re.sub(r"[\s*`_#|]", "", str(h)) for h in header_names if str(h).strip()
            ]
            if norm_headers:
                cleaned = [
                    row
                    for row in cleaned
                    if [re.sub(r"[\s*`_#|]", "", str(c)) for c in row if str(c).strip()]
                    != norm_headers
                ]
        limit = _row_limit_for_template(rt)
        if limit and len(cleaned) > limit:
            ranked = sorted(
                enumerate(cleaned),
                key=lambda item: (_table_row_confidence_score(item[1]), -item[0]),
                reverse=True,
            )
            keep_idx = sorted(idx for idx, _ in ranked[:limit])
            cleaned = [cleaned[idx] for idx in keep_idx]
        out.append(cleaned)
    return out


def _emit_md_row(cells: list[str], ended: bool) -> str:
    body = "| " + " | ".join(cells) + " |"
    return body + ("\n" if ended else "")


def _render_table_data_row(
    line: str,
    values: list[str],
    fields: list[dict] | None = None,
) -> str:
    """把一行表格模板填成数据行。``[占位]`` 行替换括号；省略号样例行按列重建。"""
    if _line_placeholders(line):
        rendered = _replace_placeholders_in_line(line, values, fields)
        if not rendered.endswith("\n") and line.endswith("\n"):
            rendered += "\n"
        return rendered
    n = max(len(fields or []), len(_table_cells(line)), 1)
    cells = [("" if v is None else str(v).strip()) for v in values]
    if len(cells) < n:
        cells.extend(["—"] * (n - len(cells)))
    else:
        cells = cells[:n]
    return _emit_md_row(cells, ended=True)


def _replace_placeholders_in_line(
    line: str,
    values: list[str],
    fields: list[dict] | None = None,
) -> str:
    """按从左到右顺序，把一行内占位符替换为 values。"""
    phs = _line_placeholders(line)
    if not phs:
        return line
    ended = line.endswith("\n")
    body = line[:-1] if ended else line
    # 用 body 重新匹配，保证索引一致
    body_phs = _line_placeholders(body)
    parts: list[str] = []
    cursor = 0
    for i, m in enumerate(body_phs):
        parts.append(body[cursor : m.start()])
        val = values[i] if i < len(values) else ""
        if not val and fields and i < len(fields) and fields[i].get("missing"):
            val = "未提及"
        parts.append(str(val))
        cursor = m.end()
    parts.append(body[cursor:])
    return "".join(parts) + ("\n" if ended else "")


def _strip_redundant_column_heading(text: str, title: str) -> str:
    """若模型在单栏正文开头复述了该栏栏名，剥离多余的首行标题。

    例如：模板已渲染 `# 核心政策`，模型若首行又输出 `## 核心政策：`、`# 核心政策`、
    `**核心政策**：`、`【核心政策】` 等，将其剥离，防止拼装后出现重复标题或光杆标题误判。
    """
    if not text or not title:
        return text
    norm_target = re.sub(r"^[0-9一二三四五六七八九十]+[\.、\s]*", "", title.strip())
    norm_target = re.sub(r"[#*_\s\[\]【】:：]", "", norm_target)
    if not norm_target:
        return text

    lines = text.splitlines(keepends=True)
    first_nonempty_idx = None
    for idx, line in enumerate(lines):
        if line.strip():
            first_nonempty_idx = idx
            break
    if first_nonempty_idx is None:
        return text

    first_line = lines[first_nonempty_idx].strip()
    norm_line = re.sub(r"^[0-9一二三四五六七八九十]+[\.、\s]*", "", first_line)
    norm_line = re.sub(r"[#*_\s\[\]【】:：]", "", norm_line)

    if norm_line == norm_target:
        next_idx = first_nonempty_idx + 1
        if next_idx < len(lines) and not lines[next_idx].strip():
            next_idx += 1
        return "".join(lines[next_idx:])

    return text


def _section_has_table(template: str, title: str) -> bool:
    """检查模板中指定栏目（title）所在小节内是否包含 Markdown 表格。"""
    if not template or not title:
        return False
    body, _ = split_template_meta(template)
    lines = body.splitlines()
    in_section = False
    norm_title = re.sub(r"^[0-9一二三四五六七八九十]+[\.、\s]*", "", title.strip())
    norm_title = re.sub(r"[#*_\s\[\]【】:：]", "", norm_title)

    for i, line in enumerate(lines):
        tm = _section_title_match(line)
        if tm:
            sec_title = tm.group(2).strip()
            norm_sec = re.sub(r"^[0-9一二三四五六七八九十]+[\.、\s]*", "", sec_title)
            norm_sec = re.sub(r"[#*_\s\[\]【】:：]", "", norm_sec)
            if in_section:
                # 遇到了下一个栏目标题，说明目标栏目已结束
                break
            if norm_sec == norm_title:
                in_section = True
                continue
        if in_section:
            line_s = line.strip()
            if line_s.startswith("|") and not _TABLE_SEP_RE.match(line_s):
                k = i + 1
                while k < len(lines) and not lines[k].strip():
                    k += 1
                if k < len(lines) and _TABLE_SEP_RE.match(lines[k].strip()):
                    return True
    return False


def _is_followed_by_table(
    template_lines: list[str],
    start_idx: int,
    caption_lines: set[int] | None = None,
) -> bool:
    """检查 template_lines[start_idx] 之后（跳过空行与表格说明行）是否紧跟着表格。"""
    j = start_idx + 1
    while j < len(template_lines):
        line_s = template_lines[j].strip()
        if not line_s:
            j += 1
            continue
        if caption_lines and j in caption_lines:
            j += 1
            continue
        if _section_title_match(template_lines[j]):
            return False
        if line_s.startswith("|") and not _TABLE_SEP_RE.match(line_s):
            k = j + 1
            while k < len(template_lines) and not template_lines[k].strip():
                k += 1
            if k < len(template_lines) and _TABLE_SEP_RE.match(template_lines[k].strip()):
                return True
        return False
    return False


def _strip_markdown_tables(text: str) -> str:
    """从标量文本中物理剥离模型私自绘制的 Markdown 表格（支持开头、中间、末尾任意位置）。

    通过识别表格表头 + 分隔行（_TABLE_SEP_RE）定位表格起始，连续剥离所有表格数据行，
    并缝合前后正文段落，保持段落间距自然。
    """
    if not text or "|" not in text:
        return text
    lines = text.splitlines()
    out_lines: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line_s = lines[i].strip()
        is_table_start = False
        if i + 1 < n and "|" in line_s and not _TABLE_SEP_RE.match(line_s):
            next_s = lines[i + 1].strip()
            if _TABLE_SEP_RE.match(next_s):
                is_table_start = True

        if is_table_start:
            # 找到了表格开始：lines[i] 是表头，lines[i+1] 是分隔线
            i += 2
            # 连续剥离所有表格数据行
            while i < n:
                row_s = lines[i].strip()
                if not row_s:
                    break
                if row_s.startswith(("- ", "* ", "#", "> ")) or re.match(r"^\d+\.\s+", row_s):
                    break
                if "|" in row_s:
                    i += 1
                else:
                    break
            # 剥离表格紧随的空行
            while i < n and not lines[i].strip():
                i += 1
            # 缝合前后正文：若前有正文且后有正文，缝合一个空行保持自然段落间隔
            while out_lines and not out_lines[-1].strip():
                out_lines.pop()
            if out_lines and i < n and lines[i].strip():
                out_lines.append("")
            continue

        out_lines.append(lines[i])
        i += 1

    res = "\n".join(out_lines).strip()
    res = re.sub(r"\n{3,}", "\n\n", res)
    return res


def assemble_placeholder_output(
    template: str,
    field_values: dict[str, str] | list[str],
    table_rows: list[list[str]] | None = None,
    tables: list[list[list[str]]] | None = None,
) -> str:
    """把字段值写回占位符模板（确定性拼装，不调 LLM）。

    Args:
        template: 占位符模板原文。
        field_values: 标量字段，按出现顺序；支持 ``{"1":..,"2":..}`` 或 list。
        table_rows: 兼容参数 = 第 0 张表的多行数据。
        tables: 多张表 ``[table0_rows, table1_rows, ...]``；优先于 table_rows。
    """
    template, _ = split_template_meta(template)
    if isinstance(field_values, list):
        scalar_list = [("" if v is None else str(v)) for v in field_values]
    else:
        # 按数字 key 排序；非数字 key 追加在后
        def _key_order(k: str) -> tuple[int, str]:
            return (int(k), k) if str(k).isdigit() else (10**9, str(k))

        scalar_list = [
            ("" if field_values[k] is None else str(field_values[k]))
            for k in sorted(field_values.keys(), key=_key_order)
        ]

    plan = plan_placeholder_fill(template)
    row_templates: list[dict[str, Any]] = plan["row_templates"]
    caption_lines = table_caption_lines(template)
    if tables is None:
        if table_rows is not None:
            tables = [table_rows]
        else:
            tables = []
    # 补齐表数量
    while len(tables) < len(row_templates):
        tables.append([])

    scalar_i = 0
    current_title = ""
    out_lines: list[str] = []
    # 行模板按**行号**定位（同表多行样例会重复出现同样文本，不能按文本匹配）；
    # 每个模板只在它的首行展开一次，其余样例行跳过
    head_idx_to_row: dict[int, int] = {
        int(rt["indices"][0]): i for i, rt in enumerate(row_templates)
    }
    skip_lines: set[int] = {
        int(idx) for rt in row_templates for idx in rt["indices"][1:]
    }

    template_lines = template.splitlines(keepends=True)
    for line_idx, line in enumerate(template_lines):
        if line_idx in skip_lines or line_idx in caption_lines:
            # 表格栏说明行：不打印正文位、不消耗标量值（否则后续字段全部错位）
            continue
        title_m = _section_title_match(line)
        if title_m:
            hashes, title = title_m.group(1), title_m.group(2).strip()
            current_title = title
            rendered = f"{hashes} {title}"
            out_lines.append(rendered + ("\n" if line.endswith("\n") else ""))
            continue
        phs = _line_placeholders(line)
        row_idx = head_idx_to_row.get(line_idx)
        if row_idx is None and not phs:
            out_lines.append(line)
            continue

        if row_idx is not None:
            rt = row_templates[row_idx]
            n_cols = max(len(rt["fields"]), 1)
            use_rows = list(tables[row_idx]) if tables[row_idx] else []
            # 无数据时一行占位，避免多行空白表（通用，无业务语义）
            # 缺省词固定「未提及」：程序读不到模板声明的词，模板声明优先由模型侧保证
            if not use_rows:
                use_rows = [["未提及"] + ["—"] * (n_cols - 1)]
            for row in use_rows:
                rendered = _render_table_data_row(line, list(row), rt["fields"])
                # 多行展开时每行必须独立成行；模板末行常无尾换行，
                # 若只在 line.endswith("\n") 时补换行，会把多行糊成一行（|| 粘连）
                if not rendered.endswith("\n"):
                    rendered += "\n"
                out_lines.append(rendered)
            continue

        if not phs:
            out_lines.append(line)
            continue

        # 标量行：按全局标量顺序取下一段 values
        n = len(phs)
        chunk = scalar_list[scalar_i : scalar_i + n]
        while len(chunk) < n:
            chunk.append("")
        if current_title:
            chunk = [_strip_redundant_column_heading(c, current_title) for c in chunk]
        # 支柱 3-1：标量文本去表（若该占位符后紧随静态表头或本栏含表格，剥离末尾私自绘制的 Markdown 表格）
        if _is_followed_by_table(template_lines, line_idx, caption_lines) or (
            current_title and _section_has_table(template, current_title)
        ):
            chunk = [_strip_markdown_tables(c) for c in chunk]
        fields = [_parse_field(m.group(1)) for m in phs]
        out_lines.append(_replace_placeholders_in_line(line, chunk, fields))
        scalar_i += n

    return "".join(out_lines)


def _table_header_cells(row_line: str, template: str) -> list[str]:
    """从模板中找表格行模板上方的表头行，返回列名列表（找不到返回空）。

    表头行特征：含 `|`、非分隔行（``|---|``）、不含占位符。
    """
    target = (row_line or "").rstrip("\n")
    lines = (template or "").splitlines()
    for idx, line in enumerate(lines):
        if line.rstrip("\n") != target:
            continue
        # 向上找最近的非空行，且是含 | 的表头行
        for j in range(idx - 1, -1, -1):
            up = lines[j].strip()
            if not up:
                continue
            if _TABLE_SEP_RE.match(up):
                continue
            if up.count("|") >= 2 and not _line_placeholders(up):
                cells = [c.strip() for c in up.strip().strip("|").split("|")]
                return [c for c in cells if c]
            break
    return []


def template_to_preview(
    template: str,
    *,
    default_rows: int = 2,
) -> dict[str, Any]:
    """把占位符模板翻译成**可编辑文档预览模型**（不展示任何模板语法）。

    预览模型（sections 有序段列表）：
    - ``{"type": "title", "level", "text"}`` —— 固定标题（只读结构，文字可改）
    - ``{"type": "label", "text"}`` —— 固定标签行（如「- 时间：」，文字可改）
    - ``{"type": "field", "hint", "value"}`` —— 段落输入区（灰字提示 + 空内容）
    - ``{"type": "table", "title", "headers", "rows", "row_hint", "min_rows"}``
      —— 表格（表头 + 可增删数据行，每格灰字提示）

    同时返回 ``char_budget``（全文/段落字数约束，内部用）与 ``template_raw``
    （回填用，调用方不得展示给用户）。
    """
    plan = plan_placeholder_fill(template or "")
    row_lines = {rt["line"].rstrip("\n") for rt in plan["row_templates"]}

    sections: list[dict[str, Any]] = []
    pending_text: list[str] = []  # 累积的非占位行，成段输出

    def _flush_text() -> None:
        nonlocal pending_text
        if not pending_text:
            return
        block = "\n".join(pending_text).strip()
        pending_text = []
        if not block:
            return
        # 表格行模板前的固定文字（表头/分隔行）由表格段处理，这里只留普通文本
        if re.search(r"^\|.*\|$", block, re.M):
            # 分离标题行与非表格文字，跳过纯表格线（表头/分隔）
            lines = block.splitlines()
            kept = [ln for ln in lines if not re.match(r"^\s*\|.*\|\s*$", ln)]
            if kept:
                sections.append(
                    {"type": "label", "text": "\n".join(kept).strip(), "raw": "\n".join(kept).strip()}
                )
            return
        sections.append({"type": "label", "text": block, "raw": block})

    # 逐行处理：识别表格行模板 → 表格段；其它行 → 标题/标签/字段
    lines = (template or "").splitlines(keepends=True)
    table_idx = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        body = line.rstrip("\n")
        if body in row_lines and table_idx < len(plan["row_templates"]):
            _flush_text()
            rt = plan["row_templates"][table_idx]
            fields = rt["fields"]
            # 表头优先取模板表头行（| 任务 | 负责人 |）的真实列名；
            # 找不到表头行时回退到行占位提示的短词
            header_cells = _table_header_cells(body, template)
            if header_cells and len(header_cells) == len(fields):
                headers = header_cells
            else:
                headers = [_hint_short(f["hint"]) for f in fields]
            # 表格标题：从刚 flush 的 label 段里找最近的 ## 标题行
            title = ""
            for j in range(len(sections) - 1, -1, -1):
                prev = sections[j]
                if prev["type"] == "title":
                    title = prev["text"]
                    break
                if prev["type"] == "label":
                    for ln in str(prev.get("text") or "").splitlines():
                        m = re.match(r"^\s*#{1,6}\s+(.+)$", ln)
                        if m:
                            title = m.group(1).strip()
                            break
                    if title:
                        break
                if prev["type"] in ("field", "table"):
                    break
            sections.append(
                {
                    "type": "table",
                    "title": title,
                    "headers": headers,
                    "rows": [["" for _ in fields] for _ in range(default_rows)],
                    "row_hint": [_hint_clean(f["hint"]) for f in fields],
                    "min_rows": default_rows,
                    "raw": body,  # 行模板原文，回写用
                    "raw_fields": [_parse_field(f["raw"]) for f in fields],
                }
            )
            table_idx += 1
            i += 1
            # 同一张表的连续样例行属于这一张表：整段跳过，避免被当成新表格或漏填字段
            while (
                i < len(lines)
                and _is_placeholder_table_row(lines[i].rstrip("\n"))
            ):
                i += 1
            continue
        # 非表格行：检查是否是含字段的行
        phs = _line_placeholders(body)
        if phs:
            _flush_text()
            if len(phs) == 1 and re.match(r"^\s*#+\s+.*$", body):
                # 标题行占位（# [标题]）→ 标题段
                head = re.match(r"^(\s*#+)\s+", body)
                level = len(head.group(1).strip()) if head else 1
                sections.append(
                    {
                        "type": "title",
                        "level": min(level, 6),
                        "text": _hint_clean(phs[0].group(1)),
                        "raw": body,
                        "raw_field": _parse_field(phs[0].group(1)),
                    }
                )
            elif len(phs) == 1 and (
                # 整行就是一个占位（含说明里带 `- [ ]` 字面、被行级识别合并成整行的那种）
                (
                    not body[: phs[0].start()].strip()
                    and not body[phs[0].end() :].strip()
                )
                # 或单占位在行尾且无冒号（如「## 纪要\n[内容]」展开成 field）
                or (
                    re.search(r"\[[^\[\]]+\]\s*$", body)
                    and not re.search(r"[:：]\s*\[", body)
                )
            ):
                # → 段落输入区（不再产生空 label 段）
                sections.append(
                    {
                        "type": "field",
                        "hint": _hint_clean(phs[0].group(1)),
                        "value": "",
                        "raw": body,
                        "raw_field": _parse_field(phs[0].group(1)),
                    }
                )
            else:
                # 行内含标签 + 占位（如「- **时间**：[时间]」）→ label 段 + 纯占位 field 段
                text_part = body[: phs[0].start()]
                ph_raw = body[phs[0].start() :]
                sections.append(
                    {"type": "label", "text": text_part.rstrip(), "raw": text_part.rstrip()}
                )
                sections.append(
                    {
                        "type": "field",
                        "hint": _hint_clean(phs[0].group(1)),
                        "value": "",
                        "raw": ph_raw,  # 只保留占位部分，标签由 label 段输出
                        "raw_field": _parse_field(phs[0].group(1)),
                    }
                )
            i += 1
            continue
        # 纯固定文字行
        pending_text.append(body)
        i += 1
    _flush_text()

    try:
        from core.templates.template_eval import parse_document_char_budget
        budget = parse_document_char_budget(template or "")
    except Exception:  # noqa: BLE001
        budget = {}

    return {
        "sections": sections,
        "char_budget": {
            "lo": budget.get("lo"),
            "hi": budget.get("hi"),
        },
        "template_raw": template or "",
    }


def preview_to_template(
    preview: dict[str, Any],
    *,
    default_rows: int = 2,
) -> str:
    """把用户编辑后的预览模型转回**占位符模板**（回填内容 / 应用结构改动）。

    - 字段段落：用户填的 ``value`` 写回占位（空值保留占位，让生成 agent 填）
    - 表格：用户加的行展开成多行数据行；表头文字变化时同步改表头行
    - 标题/标签文字：用户改了就替换原固定文字
    - 结构增删（新增段落/表格）不在此支持——增量结构变化走
      ``modify_template``（自然语言修改）；此处负责"同一结构内的内容/文字回写"。
    """
    sections = (preview or {}).get("sections") or []
    out_lines: list[str] = []

    for sec in sections:
        stype = sec.get("type")
        if stype == "title":
            raw = sec.get("raw") or ""
            text = str(sec.get("text") or "").strip()
            if raw and re.search(r"\[[^\[\]]+\]", raw):
                raw_field = sec.get("raw_field") or {}
                default_text = _hint_clean(
                    str(raw_field.get("hint") or raw_field.get("raw") or "")
                )
                if text and text != default_text:
                    # 用户确实改了标题 → 固定为用户标题；否则保留占位让生成器填写
                    level = re.match(r"^(\s*#+)", raw)
                    prefix = level.group(1) + " " if level else "# "
                    out_lines.append(f"{prefix}{text}")
                else:
                    out_lines.append(raw)
            else:
                out_lines.append(raw or text)
        elif stype == "label":
            out_lines.append(str(sec.get("raw") or sec.get("text") or ""))
        elif stype == "field":
            raw = sec.get("raw") or ""
            value = str(sec.get("value") or "").strip()
            raw_field = sec.get("raw_field") or {}
            if raw and re.search(r"\[[^\[\]]+\]", raw):
                if value:
                    # 有内容 → 替换占位为内容；若行内含标签前缀（如「- 时间：」），
                    # 该前缀由相邻 label 段单独输出，这里只补内容本身
                    replaced = re.sub(
                        r"\[[^\[\]]+\]",
                        value,
                        raw,
                        count=1,
                    )
                    out_lines.append(replaced)
                else:
                    out_lines.append(raw)  # 空 → 保留占位，生成时填
            else:
                out_lines.append(value or raw)
        elif stype == "table":
            raw = sec.get("raw") or ""
            headers = [str(h) for h in (sec.get("headers") or [])]
            rows = sec.get("rows") or []
            raw_fields = sec.get("raw_fields") or []
            if raw and raw_fields:
                # 用用户表头重建表头行 + 分隔行（保持 Markdown 表格形态）
                n = max(len(raw_fields), len(headers), 1)
                header_line = "| " + " | ".join(
                    (headers[i] if i < len(headers) else _hint_clean(
                        str(raw_fields[i].get("hint") or ""))) for i in range(n)
                ) + " |"
                sep_line = "| " + " | ".join("---" for _ in range(n)) + " |"
                out_lines.append(header_line)
                out_lines.append(sep_line)
                cleaned_rows = [
                    [str(c).strip() for c in (row or [])]
                    for row in (rows or [])
                    if any(str(c).strip() for c in (row or []))
                ]
                if not cleaned_rows:
                    out_lines.append(raw)
                for row in cleaned_rows:
                    cells = [str(c) for c in (row or [])]
                    while len(cells) < n:
                        cells.append("")
                    out_lines.append("| " + " | ".join(cells[:n]) + " |")
            else:
                # 无原始行模板：按表格标题生成简单占位表
                title = str(sec.get("title") or "").strip()
                if title:
                    out_lines.append(f"## {title}")
                n = max(len(headers), 1)
                out_lines.append("| " + " | ".join(headers) + " |")
                out_lines.append("| " + " | ".join("---" for _ in headers) + " |")
                for row in (rows or [])[: default_rows]:
                    cells = [str(c) for c in (row or [])]
                    while len(cells) < n:
                        cells.append("")
                    out_lines.append("| " + " | ".join(cells[:n]) + " |")
        else:
            out_lines.append(str(sec.get("raw") or sec.get("text") or ""))

    return "\n".join(out_lines).strip()


def _parse_tables_json_response(raw: str) -> list[list[list[str]]]:
    """解析表格抽取 JSON → tables（专供 extract_tables 使用）。"""
    data = _extract_json_object(raw) or {}
    tables: list[list[list[str]]] = []
    tables_raw = data.get("tables")
    if isinstance(tables_raw, list) and tables_raw:
        for t in tables_raw:
            tables.append(_parse_row_list(t))
    rows = _parse_row_list(data.get("rows") or [])
    if not tables and rows:
        tables = [rows]
    return tables


# ── 逐栏填充（可并发 + 流式早停）─────────────────────────────
# 2026-09-18 实测：整篇文档塞进一个 JSON 时，一次退化就是整篇重来——本地端点没有隐含输出
# 上限（托管 API 自带 ~8k），模型写到 49,074 token / 86,447 字符（约 40 倍目标），551 秒后
# 被 max_tokens 截断，JSON 不可解析 → 四栏全空 → 再整篇填一遍。逐栏填充把爆炸半径压到
# "一栏几百字"：每栏一次调用、输出纯文本（没有 JSON 转义风险）、失败只重试该栏、栏间可并发。
_COLUMN_FILL_SYSTEM = (
    "你只写「本栏」的正文。用户消息给出【内容来源】【模板原文】与【本栏说明】。\n"
    "只输出这一栏的 Markdown 正文：不要写栏目标题、不要写 JSON、不要解释、不要重复。\n"
    "有据才写；来源里没有依据时只写该栏约定的缺省词（模板没约定时写「未提及」）。写完即停。"
)
_DEGEN_REPEAT_MIN_LEN = 24  # 退化判据：同一段（≥24 字）…
_DEGEN_REPEAT_TIMES = 3  # …重复到第 3 次即中止
_DEGEN_CHECK_EVERY = 50  # 每收满这么多字符做一次重复检查（够密，且不每个 chunk 都扫）
_CHARS_PER_TOKEN = 1.6  # 早停字数阈值：实测 86,447 字符 / 49,074 token ≈ 1.76
# 超长条整改意见（逐栏填充把「单条超长」当硬问题后，重写那一栏时下发的具体修法）
_OVERLONG_ITEM_REVISION = (
    "上一版这一栏存在单条承载多项事实的长条目。请按照层级化写作范式进行清晰展开："
    "顶层保持数字序号或条目（如 `1. **事项/议题**：核心定调` 或 `- **事项/议题**：核心定调`）；"
    "主干条目提炼结论与定调，其下充分利用二级缩进（2 空格 `  - `）将问题成因、方案对比、量化参数与验收指标分项展开；"
    "遵循事实完整展开原则，条数宁多不漏，完整保留全场所有硬核数据与约束细节。"
)

# 高信息密度重点事实栏与不设上限意图识别（豁免/放宽单条超长重写，保护新闻发布核心信息、法庭举证、政策要点等专业事实完整性）
_HIGH_DENSITY_KEYWORDS = (
    "核心信息",
    "举证",
    "法庭调查",
    "核心政策",
    "重点工作",
    "病史",
    "诊断",
    "医嘱",
    "访谈详细记录",
    "核心论证",
    "核心观点与论证",
    "交锋",
    "条款梳理",
    "核心条款",
    "争议焦点",
    "未决分歧",
    "后续探索",
    "后期探索",
    "未决争议",
    "分歧焦点",
    "探索事项",
)

_EXEMPT_INTENT_KEYWORDS = (
    "不设字数上限",
    "不设上限",
    "写全优先",
    "不得精简",
    "不得省略",
    "一条一个主题",
    "量化指标逐项保留",
    "细节照原文写全",
    "照原文写全",
)

_SHORT_ITEM_LIMIT_RE = re.compile(r"每条\s*\d+[-–~至]\d+\s*字")

def _scalar_titles(template: str) -> list[str]:
    """标量字段所属栏名（与 ``plan_placeholder_fill`` 同序）：`# [栏名]` 之下的取栏名。

    用于逐栏填充时告诉模型"其它栏目在哪"、以及把门禁问题定位回具体栏。
    """
    body, _ = split_template_meta(template)
    captions = table_caption_lines(body)
    titles: list[str] = []
    current = ""
    for idx, line in enumerate(body.splitlines(keepends=True)):
        match = _section_title_match(line)
        if match:
            current = match.group(2).strip()
            continue
        if idx in captions or _is_table_data_row(line):
            continue
        titles.extend([current] * len(_line_placeholders(line)))
    return titles


def _target_line(source_han: int | None, template: str) -> str:
    """【本篇目标】一句话：有效预算（模板声明优先，否则按原文规模的档位）。

    prompt 里已有上下文里的【篇幅预算】，但它是"素材"的一部分；这里把它挪进写作指令区，
    让"该写多长"和"怎么写字数上限"贴在一起——上限之外还有 max_tokens 硬截断兜底。
    """
    try:
        from core.templates.length_budget import effective_doc_budget
    except Exception:  # noqa: BLE001
        return ""
    span = effective_doc_budget(source_han, template)
    if not span:
        return ""
    return (
        f"【本篇目标】正文总量约 {int(span[0])}–{int(span[1])} 汉字（含条目与表格）；"
        "超过上限会被截断，低于下限＝漏了原文事实。"
    )


def _prune_context_for_column(
    context: str,
    template: str,
    *,
    title: str,
    hint: str,
    directives: str = "",
) -> str:
    """根据栏目类型智能瘦身上下文（Targeted Column Context Pruning）。

    - 待办与风险栏：切除长篇会议原文讨论，仅注入 action_hints、user_hits（命中表）和 decisions；
    - 业务决策栏：仅注入与 focus_thing / focus_person 相关的议题讨论切片；
    - 概况局势栏：保留宏观决策与结论，切除超长技术细节实录。
    若 context 为简短无结构文本（如单元测试 mock），安全原样返回。
    """
    if not context or "\n\n" not in context:
        return context

    pattern = r"(?m)(?=^(?:视角模式：|objective_perspective：|用户画像：|会议理解：|已审核用户视角：|会议原文[^\n]*：|已批准[^\n]*草稿：|[^\n]*审核结论：|【[^\n]+】))"
    raw_parts = [p.strip() for p in re.split(pattern, context) if p.strip()]
    if len(raw_parts) < 3:
        return context

    sections: dict[str, str] = {}
    extra_blocks: list[str] = []
    head_block: str = ""

    for part in raw_parts:
        m = re.match(r"^([^：:\n]+[：:])\s*(.*)", part, re.DOTALL)
        if m:
            label = m.group(1).strip()
            body = m.group(2).strip()
            sections[label] = body
        elif part.startswith("【"):
            extra_blocks.append(part)
        else:
            if not head_block:
                head_block = part

    user_data: dict[str, Any] = {}
    for k, v in sections.items():
        if "用户画像" in k:
            try:
                user_data = json.loads(v)
            except Exception:
                pass
            break

    focus_things = [str(x).strip() for x in (user_data.get("focus_thing") or []) if str(x).strip()]
    focus_persons = [str(x).strip() for x in (user_data.get("focus_person") or []) if str(x).strip()]
    user_name = str(user_data.get("name") or "").strip()
    key_needles = [n for n in ([user_name] + focus_persons + focus_things) if len(n) >= 2]

    is_action_col = any(kw in title for kw in ("行动", "待办", "分工", "任务")) and not any(kw in title for kw in ("议题", "讨论", "决议", "方案"))
    is_risk_col = any(kw in title for kw in ("风险", "卡点", "待确认", "未决", "争议", "分歧", "探索"))
    is_overview_col = any(kw in title for kw in ("概况", "局势", "背景", "承接目标", "本人定调", "摘要", "概述", "简述"))
    is_decision_col = any(kw in title for kw in ("重点关注", "业务进展", "决策", "方案", "进展", "技术", "讨论", "议题"))

    # 1. 待办栏与风险栏：切除长篇非相关议题讨论，注入全量待办/风险/决策并保留关键分工与依赖实录
    if is_action_col or is_risk_col:
        out_parts = []
        if head_block:
            out_parts.append(head_block)
        for label, body in sections.items():
            if "会议原文" in label:
                # 从原文提取与分工、依赖、测试、排期、阻塞、风险相关的具体实录行，注入作为细节锚点
                # 标记使用「发言实录（分工与依赖线索）」，不含「会议原文」字样，兼顾测试契约与事实细节
                _CLUES = (
                    "负责", "安排", "测一下", "测试", "跟进", "排期", "提交", "申请", "改一下",
                    "问题单", "待办", "依赖", "阻塞", "卡点", "时延", "并发", "上线", "出包",
                    "提供", "确认", "答应", "承诺", "风险", "隐患", "瓶颈", "超时", "挂了",
                    "差一些", "搞完", "交付", "接口", "报告", "验证", "支撑", "配合", "卡住", "受限"
                )
                paras = [p.strip() for p in body.splitlines() if p.strip()]
                clue_paras = [p for p in paras if any(kw in p for kw in _CLUES)]
                if key_needles:
                    needle_clues = [p for p in clue_paras if any(n in p for n in key_needles)]
                    if needle_clues:
                        clue_paras = needle_clues
                if clue_paras:
                    out_parts.append("发言实录（分工与依赖线索）：\n" + "\n".join(clue_paras[:60]))
                continue
            if "会议理解" in label:
                try:
                    und = json.loads(body)
                    compact_und: dict[str, Any] = {}
                    for field in ("decisions", "risks", "meeting_purpose", "meeting_brief", "open_questions"):
                        if field in und and und[field]:
                            compact_und[field] = und[field]
                    if key_needles and "risks" in compact_und:
                        compact_und["risks"] = [
                            r for r in compact_und["risks"]
                            if any(n in json.dumps(r, ensure_ascii=False) for n in key_needles)
                        ]
                    if "topics" in und and isinstance(und["topics"], list):
                        compact_topics = []
                        for t in und["topics"]:
                            if not isinstance(t, dict):
                                continue
                            c_t: dict[str, Any] = {
                                "title": t.get("title") or t.get("topic") or t.get("name") or "议题",
                                "module": t.get("module") or "",
                                "actions": t.get("actions") or [],
                                "risks": t.get("risks") or [],
                                "decisions": t.get("decisions") or [],
                            }
                            if "key_points" in t:
                                c_t["key_points"] = t["key_points"]
                            compact_topics.append(c_t)
                        compact_und["topics"] = compact_topics
                    out_parts.append(f"{label}\n{json.dumps(compact_und, ensure_ascii=False)}")
                    continue
                except Exception:
                    pass
            if "已批准" in label and "草稿" in label and (user_name or focus_persons):
                try:
                    draft_obj = json.loads(body)
                    if isinstance(draft_obj, dict):
                        if is_action_col and "personally_relevant_points" in draft_obj:
                            fmt_act = _format_action_items_projection(
                                draft_obj["personally_relevant_points"],
                                user_name=user_name,
                                focus_persons=focus_persons,
                                focus_things=focus_things,
                            )
                            if fmt_act:
                                draft_obj["personally_relevant_points"] = fmt_act.splitlines()
                        if is_risk_col and "risks_and_blockers" in draft_obj:
                            fmt_risk = _format_risks_projection(
                                draft_obj["risks_and_blockers"],
                                user_name=user_name,
                                focus_persons=focus_persons,
                                focus_things=focus_things,
                            )
                            if fmt_risk:
                                draft_obj["risks_and_blockers"] = fmt_risk.splitlines()
                        out_parts.append(f"{label}\n{json.dumps(draft_obj, ensure_ascii=False)}")
                        continue
                except Exception:
                    pass
            out_parts.append(f"{label}\n{body}")
        filtered_extra = []
        for blk in extra_blocks:
            if "分栏分组骨架" in blk and (user_name or focus_persons):
                allowed_heads = {"**与我相关**："}
                if user_name:
                    allowed_heads.add(f"**{user_name}**：")
                for fp in focus_persons:
                    allowed_heads.add(f"**{fp}**：")
                g_lines = []
                for ln in blk.splitlines():
                    if ln.startswith("**") and "：" in ln:
                        if ln in allowed_heads or any(fp in ln for fp in focus_persons):
                            g_lines.append(ln)
                    else:
                        g_lines.append(ln)
                filtered_extra.append("\n".join(g_lines))
            else:
                filtered_extra.append(blk)
        out_parts.extend(filtered_extra)
        return "\n\n".join(out_parts)

    # 2. 业务决策栏：保留所有核心业务与技术议题切片，剔除明确无关的行政流程
    if is_decision_col and key_needles:
        out_parts = []
        if head_block:
            out_parts.append(head_block)
        for label, body in sections.items():
            if "会议理解" in label:
                try:
                    und = json.loads(body)
                    if "topics" in und and isinstance(und["topics"], list):
                        new_topics = []
                        _ADMIN_TOPIC_KEYWORDS = ("报销", "发票", "考勤", "行政", "团建", "工卡", "打卡", "贴票")
                        for t in und["topics"]:
                            if not isinstance(t, dict):
                                continue
                            t_str = json.dumps(t, ensure_ascii=False)
                            is_key_topic = any(needle in t_str for needle in key_needles)
                            is_admin_noise = any(noise in t_str for noise in _ADMIN_TOPIC_KEYWORDS) and not is_key_topic
                            if is_admin_noise:
                                continue

                            is_tier1 = any(ft in t_str for ft in focus_things) or (user_name and user_name in t_str)
                            is_tier2 = not is_tier1 and any(fp in t_str for fp in focus_persons)
                            tier_level = 1 if is_tier1 else (2 if is_tier2 else 3)

                            title_val = t.get("title") or t.get("topic") or t.get("name") or "议题"
                            discussion_val = t.get("context_and_debate") or t.get("discussion") or ""

                            new_topic: dict[str, Any] = {
                                "title": title_val,
                                "module": t.get("module") or "",
                                "tier": f"Tier {tier_level}",
                                "decisions": t.get("decisions") or [],
                                "key_metrics": t.get("key_metrics") or [],
                            }
                            if "key_points" in t:
                                new_topic["key_points"] = t["key_points"]
                            if discussion_val:
                                if tier_level <= 2 or len(discussion_val) <= 200:
                                    new_topic["discussion"] = discussion_val
                                    new_topic["context_and_debate"] = discussion_val
                                else:
                                    short_d = discussion_val[:200] + "..."
                                    new_topic["discussion"] = short_d
                                    new_topic["context_and_debate"] = short_d

                            if t.get("actions"):
                                new_topic["actions"] = t["actions"]
                            if t.get("risks"):
                                new_topic["risks"] = t["risks"]

                            new_topics.append(new_topic)
                        und["topics"] = new_topics
                        out_parts.append(f"{label}\n{json.dumps(und, ensure_ascii=False)}")
                        continue
                except Exception:
                    pass
            elif "会议原文" in label:
                paragraphs = [p.strip() for p in body.splitlines() if p.strip()]
                _ADMIN_PARAS = ("发票", "报销", "行政流程", "贴票", "团建活动", "工卡补办")
                kept_paras = []
                for p in paragraphs:
                    if any(noise in p for noise in _ADMIN_PARAS) and not any(needle in p for needle in key_needles):
                        continue
                    kept_paras.append(p)
                if kept_paras:
                    out_parts.append(f"{label}（业务进展切片）：\n" + "\n".join(kept_paras))
                    continue
            out_parts.append(f"{label}\n{body}")
        out_parts.extend(extra_blocks)
        return "\n\n".join(out_parts)

    # 3. 概况局势栏：若原文过长，裁剪原文仅保留开篇背景；精简理解与草稿，防止流水账与报菜名
    if is_overview_col:
        out_parts = []
        if head_block:
            out_parts.append(head_block)
        for label, body in sections.items():
            if "会议理解" in label:
                try:
                    und = json.loads(body)
                    compact_und: dict[str, Any] = {}
                    for field in ("meeting_purpose", "meeting_brief"):
                        if field in und and und[field]:
                            compact_und[field] = und[field]
                    if "topics" in und and isinstance(und["topics"], list):
                        compact_und["topics"] = [
                            {"module": t.get("module") or "", "title": t.get("title") or t.get("topic") or ""}
                            for t in und["topics"] if isinstance(t, dict)
                        ]
                    out_parts.append(f"{label}\n{json.dumps(compact_und, ensure_ascii=False)}")
                    continue
                except Exception:
                    pass
            if "已批准" in label and "草稿" in label:
                try:
                    draft_obj = json.loads(body)
                    if isinstance(draft_obj, dict):
                        compact_draft = {
                            "headline": draft_obj.get("headline") or "",
                            "executive_summary": draft_obj.get("executive_summary") or [],
                            "key_decisions": draft_obj.get("key_decisions") or [],
                        }
                        out_parts.append(f"{label}\n{json.dumps(compact_draft, ensure_ascii=False)}")
                        continue
                except Exception:
                    pass
            if "会议原文" in label and len(body) > 3000:
                short_body = body[:1500].rsplit("\n", 1)[0] + "\n...(后文各模块细节讨论略，宏观结论见【会议理解】与【已批准纪要草稿】)"
                out_parts.append(f"{label}（开篇背景摘要）：\n{short_body}")
                continue
            out_parts.append(f"{label}\n{body}")
        out_parts.extend(extra_blocks)
        return "\n\n".join(out_parts)

    return context


def _format_action_items_projection(
    points: list[str],
    *,
    user_name: str = "",
    focus_persons: list[str] | None = None,
    focus_things: list[str] | None = None,
) -> str | None:
    if not isinstance(points, list):
        return None
    if not points:
        return "**本人相关**：\n- 暂无本人直接待办"

    fps = set(focus_persons or [])
    fts = set(focus_things or [])

    lines: list[str] = []
    group_re = re.compile(r"^(?:###\s*|\*\*)[^*:\n]+(?:\*\*|)[：:]?\s*$")
    current_group: str | None = None
    has_self_group = False
    self_items_count = 0
    group_allowed = True

    for raw in points:
        item = str(raw or "").strip()
        if not item:
            continue

        if group_re.match(item):
            clean_g = re.sub(r"^(?:###\s*|\*\*)\s*|\s*(?:\*\*|)[：:]?\s*$", "", item)
            is_self = "与我相关" in clean_g or "本人" in clean_g or (bool(user_name) and user_name in clean_g)
            is_dep = any(k in clean_g for k in ("重点关注", "重点协同", "协同输入", "前置依赖", "外部依赖", "关注人定调"))
            is_focus_p = bool(fps and any(fp in clean_g for fp in fps))
            is_focus_t = bool(fts and any(ft in clean_g for ft in fts))

            # 过滤全员非关注人分工大组及非关注人个人组
            if any(k in clean_g for k in ("协同人员主要分工", "全员分工", "其他人员分工")):
                group_allowed = False
                continue

            if not is_self and not is_dep and not is_focus_p and not is_focus_t:
                group_allowed = False
                continue

            group_allowed = True
            norm_g = "本人相关" if is_self else "重点关注"
            current_group = norm_g
            header = f"**{norm_g}**："
            if header not in lines:
                if lines and lines[-1] != "":
                    lines.append("")
                lines.append(header)
            if is_self:
                has_self_group = True
            continue

        if not group_allowed:
            continue

        if current_group is None:
            current_group = "本人相关"
            has_self_group = True
            lines.append("**本人相关**：")

        if current_group == "本人相关":
            self_items_count += 1

        has_checkbox = bool(re.match(r"^\s*[-*]\s*\[[ xX]\]", item))
        prefix = "- [ ] " if (has_checkbox and current_group == "本人相关") else "- "

        cleaned = re.sub(r"^\s*(?:[-•+]|\*(?!\*)|\d+\.|\([0-9]+\)\.?)\s*(?:\[[ xX]?\]\s*)?", "", item).strip()
        cleaned = re.sub(r"[\[【](?:高风险|中风险|低风险|阻塞|阻碍)[\]】]", "", cleaned).strip()

        if cleaned.startswith("**"):
            task_line = f"{prefix}{cleaned}"
        elif "：" in cleaned:
            parts = cleaned.split("：", 1)
            task_line = f"{prefix}**{parts[0].strip()}**：{parts[1].strip()}"
        elif ":" in cleaned:
            parts = cleaned.split(":", 1)
            task_line = f"{prefix}**{parts[0].strip()}**：{parts[1].strip()}"
        else:
            m_paren = re.match(r"^([^（(]+)[（(](.*)[）)]$", cleaned)
            if m_paren:
                task_name = m_paren.group(1).strip()
                task_args = m_paren.group(2).strip()
                task_line = f"{prefix}**{task_name}**（{task_args}）"
            else:
                task_line = f"{prefix}{cleaned}"

        lines.append(task_line)

    if has_self_group and self_items_count == 0:
        idx = lines.index("**本人相关**：")
        lines.insert(idx + 1, "- 暂无本人直接待办")

    return "\n".join(lines).strip() or None


def _format_risks_projection(
    risks: list[str],
    *,
    user_name: str = "",
    focus_persons: list[str] | None = None,
    focus_things: list[str] | None = None,
) -> str | None:
    if not isinstance(risks, list):
        return None
    if not risks:
        return "**本人相关**：\n- 暂无直接风险\n\n**重点关注**：\n- 暂无重点关注风险"

    fps = set(focus_persons or [])
    fts = set(focus_things or [])

    lines: list[str] = []
    group_re = re.compile(r"^(?:###\s*|\*\*)[^*:\n]+(?:\*\*|)[：:]?\s*$")
    current_group: str | None = None
    group_allowed = True

    for raw in risks:
        item = str(raw or "").strip()
        if not item:
            continue

        if group_re.match(item):
            clean_g = re.sub(r"^(?:###\s*|\*\*)\s*|\s*(?:\*\*|)[：:]?\s*$", "", item)
            # 待确认事项分组彻底去掉，不再渲染
            if "待确认" in clean_g:
                group_allowed = False
                current_group = "待确认"
                continue

            current_group = clean_g

            is_self = "与我相关" in clean_g or "本人" in clean_g or (bool(user_name) and user_name in clean_g)
            is_focus_risk = any(k in clean_g for k in ("重点关注", "关注人", "全局风险与未决", "全局风险", "全局重大风险"))
            is_focus_p = bool(fps and any(fp in clean_g for fp in fps))
            is_focus_t = bool(fts and any(ft in clean_g for ft in fts))

            # 过滤非本人、非重点协同/重点关注人及非关注事项的风险分组
            if not is_self and not is_focus_risk and not is_focus_p and not is_focus_t:
                group_allowed = False
                continue

            group_allowed = True
            norm_g = "本人相关" if is_self else "重点关注"
            current_group = norm_g
            header = f"**{norm_g}**："
            if header not in lines:
                if lines and lines[-1] != "":
                    lines.append("")
                lines.append(header)
            continue

        if not group_allowed or current_group == "待确认":
            continue

        if current_group is None:
            current_group = "本人相关"
            lines.append("**本人相关**：")

        # 如果在全局风险组下，且指定了重点关注，过滤掉与本人及重点关注完全无关的外围噪音
        if current_group and any(k in current_group for k in ("全局", "未决")):
            needles = [user_name] + list(fps) + list(fts) if (user_name or fps or fts) else []
            if needles and not any(n in item for n in needles if len(n) >= 2):
                continue

        has_checkbox = bool(re.match(r"^\s*[-*]\s*\[[ xX]\]", item))
        prefix = "- [ ] " if (has_checkbox and current_group == "本人相关") else "- "

        cleaned = re.sub(r"^\s*(?:[-•+]|\*(?!\*)|\d+\.|\([0-9]+\)\.?)\s*(?:\[[ xX]?\]\s*)?", "", item).strip()
        # 标记的高风险、阻塞等内容都去掉
        cleaned = re.sub(r"[\[【](?:高风险|中风险|低风险|阻塞|阻碍)[\]】]", "", cleaned).strip()

        if cleaned.startswith("**"):
            cleaned = re.sub(r"[\[【](?:高风险|中风险|低风险|阻塞|阻碍)[\]】]", "", cleaned).strip()
            task_line = f"{prefix}{cleaned}"
        elif "：" in cleaned:
            parts = cleaned.split("：", 1)
            title_p = re.sub(r"[\[【](?:高风险|中风险|低风险|阻塞|阻碍)[\]】]", "", parts[0]).strip()
            task_line = f"{prefix}**{title_p}**：{parts[1].strip()}"
        elif ":" in cleaned:
            parts = cleaned.split(":", 1)
            title_p = re.sub(r"[\[【](?:高风险|中风险|低风险|阻塞|阻碍)[\]】]", "", parts[0]).strip()
            task_line = f"{prefix}**{title_p}**：{parts[1].strip()}"
        else:
            task_line = f"{prefix}{cleaned}"

        lines.append(task_line)

    return "\n".join(lines).strip() or None


def project_column_from_draft(
    context: str,
    template: str,
    *,
    title: str,
    hint: str,
    directives: str = "",
) -> str | None:
    """草稿直出快线（Direct Projection）：从上游已批准草稿中直接提取结构化列表回填。

    若模板格式吻合，Python 程序直接按规范回填，完全跳过大模型调用，直接节省一次并发耗时。
    仅在个人视角或显式个人模板中触发；若草稿未对齐或缺失，平滑回退 None 走 LLM 生成。
    """
    if not context or "\n\n" not in context:
        return None

    is_personal = (
        "视角模式：personal" in context
        or "personal_minutes.md" in template
        or "会议概况" in template
        or "相关行动" in template
        or "相关风险" in template
        or "本场概况与承接目标" in template
        or "本场概况与本人定调" in template
        or "【本视角纪律】" in directives
    )
    if not is_personal:
        return None

    is_action_col = any(kw in title for kw in ("相关行动", "行动项", "待办", "分工", "任务")) and not any(kw in title for kw in ("议题", "讨论", "决议", "方案"))
    is_risk_col = any(kw in title for kw in ("相关风险", "风险", "卡点", "待确认", "未决", "阻塞", "障碍")) and not any(kw in title for kw in ("议题", "讨论", "决议", "方案"))

    if not is_action_col and not is_risk_col:
        return None

    m_draft = re.search(r"已批准[^\n]*草稿：\s*\n(\{.*?\})(?=\n\n|\Z)", context, re.DOTALL)
    if not m_draft:
        return None
    try:
        draft = json.loads(m_draft.group(1))
    except Exception:
        return None

    user_data: dict[str, Any] = {}
    m_user = re.search(r"用户画像：\s*\n(\{.*?\})(?=\n\n|\Z)", context, re.DOTALL)
    if m_user:
        try:
            user_data = json.loads(m_user.group(1))
        except Exception:
            pass
    user_name = str(user_data.get("name") or "").strip()
    focus_persons = [str(x).strip() for x in (user_data.get("focus_person") or []) if str(x).strip()]
    focus_things = [str(x).strip() for x in (user_data.get("focus_thing") or []) if str(x).strip()]

    if is_action_col:
        points = draft.get("personally_relevant_points")
        if not isinstance(points, list):
            return None
        return _format_action_items_projection(
            points,
            user_name=user_name,
            focus_persons=focus_persons,
            focus_things=focus_things,
        )

    if is_risk_col:
        risks = draft.get("risks_and_blockers")
        if not isinstance(risks, list):
            return None
        return _format_risks_projection(
            risks,
            user_name=user_name,
            focus_persons=focus_persons,
            focus_things=focus_things,
        )

    return None


def _column_fill_user(
    context: str,
    template: str,
    *,
    index: int,
    total: int,
    hint: str,
    title: str,
    others: list[str],
    revision: str = "",
    target_line: str = "",
    directives: str = "",
) -> str:
    """单栏填充的用户消息：只给这一栏的说明，其余栏目只列栏名（防止越栏）。

    ``directives`` 是本栏写作纪律（领域给的取舍口径），紧跟【本栏说明】之后：说明管"这一栏
    写什么主题"，纪律管"写谁、详到什么程度"，两者的优先级由纪律文本自己写明。
    """
    body, requirement = split_template_meta(template)
    lines = [
        f"本次只写第 {index}/{total} 栏" + (f"（{title}）" if title else "") + "。",
        f"【本栏说明】{hint}",
    ]
    if directives.strip():
        lines.append(directives.strip())
    if others:
        lines.append(
            "其它栏目（" + "、".join(f"[{t}]" for t in others if t) + "）的内容归它们，本栏不复述。"
        )
    if target_line.strip():
        lines.append(target_line.strip())
    lines.extend([
        "只输出这一栏的正文：不要写栏目标题、不要写 JSON、不要解释、不要重复。",
        "有据才写；来源里没有依据时只写该栏约定的缺省词（模板没约定时写「未提及」）。",
        BODY_FORMAT_RULES,
        *_char_budget_lines(template),
    ])
    lines.append(
        "【要点完整与依据充分】按实有事实充分呈现技术参数、指标数据、分工待办与潜在卡点；"
        "业务进展栏按业务模块客观分组分条（独占一行写「**模块名称**：」，坚决禁止添加「背景与问题：」「方案考量：」「落地共识：」等任何机械前缀标签）；"
        "相关行动看板仅收录本人待办与重点关注协同（分为「**本人相关**：」与「**重点关注**：」，彻底过滤全场无关人员杂项分工）；"
        "相关风险栏仅收录本人卡点与重点关注风险（分为「**本人相关**：」与「**重点关注**：」，彻底过滤外围无关风险，严禁出现待确认事项，严禁标注高风险、阻塞等级别标签）。"
    )
    if any(kw in title for kw in ("会议概况", "概况", "大盘")):
        lines.append(
            "【会议概况写作纪律】单段写完（约 100–200 字，严禁拆分成多段），客观交代会议主旨背景、全局核心决议、版本上线窗口与战略总里程碑；"
            "严禁按各业务模块逐一流水账式罗列具体细节（具体模块进展下沉至下一栏承载），严禁在正文中以第一人称「我」或「本人」自称，严禁使用第三人称「某某同志/其」，动作直接以动词开头自然陈述。"
        )
    if any(kw in title for kw in ("业务进展", "进展", "重点关注")):
        lines.append(
            "【业务进展写作纪律】定位为全场客观业务与技术大盘，纯客观呈现，不掺杂个人主观视角与“重点关注”标签：\n"
            "依照会议研讨的核心业务模块或议题，独占一行建立模块大组标题（如「**模块名称**：」）；\n"
            "同一模块下的议题自然聚合，组内使用 `- ` 简洁客观列出核心技术进展、关键量化指标与拍板决策；\n"
            "坚决禁止添加「背景与问题：」「方案考量：」「落地共识：」「现状：」「结论：」等任何机械前缀标签；严禁使用任何 emoji 表情符号；没有内容的组不出现。"
        )
    if any(kw in title for kw in ("相关行动", "行动")):
        lines.append(
            "【相关行动写作纪律】仅聚焦个人行动与重点关注协同，彻底过滤全场无关人员杂项分工；"
            "严禁为除本人及重点关注人（focus_person）之外的任何其他与会人员单独建组（如不得出现武思华、范炳杰、张宇翔等无关人员组名）；"
            "第一组写「**本人相关**：」，列出本人直接负责的事项，以动词开头省略主语，融合时间与交付物；"
            "第二组写「**重点关注**：」，仅列出推进本人工作所必需的外部交付，以及与 focus_person 和 focus_thing 相关的核心交付承诺，标明责任人真名与承诺节点；没有内容的组不出现。"
        )
    if any(kw in title for kw in ("相关风险", "风险")):
        lines.append(
            "【相关风险写作纪律】仅聚焦个人卡点与重点关注风险，彻底过滤外围无关风险；"
            "严禁为除本人及重点关注人（focus_person）之外的任何其他与会人员单独建组；"
            "第一组写「**本人相关**：」，列出直接阻碍本人推进的风险卡点；"
            "第二组写「**重点关注**：」，仅列出 focus_person 关注的重大定调隐患或影响 focus_thing 交付的关键技术卡点；"
            "严禁标注【高风险】、【阻塞】等任何形式的级别标签；严禁出现待确认事项分组或内容；没有内容的组不出现。"
        )
    # 针对清单与重点工作类栏目：前置注入领域结构化锚点与句式多样性纪律，防止自回归死循环
    _LISTING_KEYWORDS = ("工作", "政策", "措施", "要点", "清单", "建议", "议题", "事项", "内容", "实录", "记录")
    if any(kw in title for kw in _LISTING_KEYWORDS):
        lines.append(
            "【要点纪律】各条目须按不同维度/领域分别展开，每条聚焦独立的具体举措与事实；"
            "严禁在不同条目中使用完全相同的主谓宾句式或套话短语；所有要点陈述完毕后立即停笔，严禁循环复述。"
        )
    # 支柱 1 形态 B：正文 + 表格复合栏的职责隔离纪律
    if _section_has_table(body, title):
        lines.append(
            "【表格隔离纪律】本栏下方的 Markdown 表格已由系统独立程序提取填充，"
            "你只需输出本栏的正文说明/条目清单，严禁在正文输出任何 Markdown 表格（严禁输出包含 | 的表格行）。"
        )
    if requirement.strip():
        lines.extend(["", "【模板写作要求】（必须遵守，不要写进正文）", requirement.strip()])
    if revision.strip():
        lines.extend(["", f"【上一版问题，必须修正】\n{revision.strip()}"])
    lines.extend(["", "【内容来源】", context, "", "【模板原文】", body])
    return "\n".join(lines)


def _degenerate_reason(text: str) -> str:
    """退化判据：同一段（≥24 字）在最近 3000 字里重复 ≥3 次 → 返回原因。"""
    paras = [
        p.strip()
        for p in re.split(r"\n+", (text or "")[-3000:])
        if len(p.strip()) >= _DEGEN_REPEAT_MIN_LEN
    ]
    seen: dict[str, int] = {}
    for para in paras:
        seen[para] = seen.get(para, 0) + 1
        if seen[para] >= _DEGEN_REPEAT_TIMES:
            return f"同一段重复 {seen[para]} 次"
    return ""


async def _stream_column(
    client: Any,
    user: str,
    *,
    cap: int,
    ceiling: int,
    label: str,
    timeout: float | None = None,
    presence_penalty: float | None = None,
    frequency_penalty: float | None = None,
    temperature: float | None = None,
) -> str | None:
    """流式写一栏：边收边查（重复/超长），命中即中止并返回 None。

    非流式下"退化"只能等它自己结束（实测 551 秒）；流式下发现重复或超长可以立刻放弃，
    把这一栏交给重试或整篇回退。客户端不支持流式时返回 None（调用方回退整篇路径）。
    """
    stream_text = getattr(client, "stream_text", None)
    if stream_text is None:
        return None
    parts: list[str] = []
    size = 0
    checked = 0
    stream_kwargs: dict[str, Any] = {"max_tokens": cap, "label": label}
    if timeout is not None:
        stream_kwargs["timeout"] = timeout
    if presence_penalty is not None:
        stream_kwargs["presence_penalty"] = presence_penalty
    if frequency_penalty is not None:
        stream_kwargs["frequency_penalty"] = frequency_penalty
    if temperature is not None:
        stream_kwargs["temperature"] = temperature
    stream = stream_text(_COLUMN_FILL_SYSTEM, user, **stream_kwargs)
    try:
        async for chunk in stream:
            if chunk:
                parts.append(chunk)
                size += len(chunk)
            if size > ceiling:
                logger.warning(
                    "column fill degenerate label=%s：输出超 %s 字符（上限 %s）已中止",
                    label,
                    size,
                    ceiling,
                )
                return None
            if size - checked >= _DEGEN_CHECK_EVERY:
                checked = size
                why = _degenerate_reason("".join(parts))
                if why:
                    logger.warning("column fill degenerate label=%s：%s 已中止", label, why)
                    return None
    except Exception:  # 流式失败按"这一栏没写出来"处理，交给重试/回退
        logger.warning("column fill stream failed label=%s", label, exc_info=True)
        return None
    finally:
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception):  # 关流失败不影响已收到内容
                await aclose()
    text = "".join(parts).strip()
    why = _degenerate_reason(text)
    if why:  # 收尾再判一次：节流可能刚好跳过最后一次检查
        logger.warning("column fill degenerate label=%s：%s 已丢弃", label, why)
        return None
    return text or None


async def fill_placeholder_by_columns(
    client: Any,
    context: str,
    template: str,
    plan: dict[str, Any],
    *,
    source_han: int | None = None,
    directives: str = "",
    overlong_han: int | None = None,
    overlong_min_count: int | None = None,
) -> str | None:
    """逐栏填充（无表格模板）：每栏一次调用、并发、失败只重试该栏。

    返回 None 表示"逐栏不可用 / 一栏都没写出来"，调用方回退整篇 JSON 路径。
    门禁不过时只重写被点名的栏（最多两栏）——整篇重渲染的代价是它的十倍。
    另外**单条超长（`- ` 条目 >200 汉字）在逐栏填充里算硬问题**：它是最常见、用户一眼
    看得出的形态缺陷（十几件事被「；」压成一条），命中就只重写那一栏（一次单栏调用）。

    ``directives`` 是调用方（领域）给的**本栏写作纪律**（如真人模式的取舍口径）：逐栏填充的
    system 里没有领域渲染提示词，取舍只能从这里进；为空则过去的行为一字不变。
    """
    scalars = list(plan.get("scalars") or [])
    row_templates = list(plan.get("row_templates") or [])
    if not scalars:
        return None
    if getattr(client, "stream_text", None) is None:
        return None
    from core.execution.hard_execution import (
        _ITEM_CHECK_HAN,
        gate_render_output,
        overlong_items,
    )
    from core.templates.length_budget import output_token_cap

    cap = output_token_cap(source_han, template)
    ceiling = int(cap * _CHARS_PER_TOKEN)
    target = _target_line(source_han, template)
    titles = _scalar_titles(template)
    if len(titles) != len(scalars):  # 结构对不上就不冒进，回退整篇
        return None

    target_han = overlong_han if overlong_han is not None else _ITEM_CHECK_HAN
    min_cnt = overlong_min_count if overlong_min_count is not None else 1

    def _is_column_overlong(col_text: str, col_idx: int = -1) -> bool:
        """策略 A、策略 B 与高信息密度栏豁免综合判据：判定单栏是否需触发超长重写。"""
        # 判断当前栏是否为高密度/不宜拆分的重点事实栏（如新闻发布会核心信息、法庭举证、政策要点等）
        is_high_density = False
        if 0 <= col_idx < len(titles) and col_idx < len(scalars):
            t = titles[col_idx]
            h = str(scalars[col_idx].get("hint") or "")
            has_short_limit = bool(_SHORT_ITEM_LIMIT_RE.search(h))
            if not has_short_limit:
                if any(kw in t for kw in _HIGH_DENSITY_KEYWORDS) or any(
                    kw in h for kw in _EXEMPT_INTENT_KEYWORDS
                ):
                    is_high_density = True

        if is_high_density:
            col_target_han = max(target_han, 380)
            col_min_cnt = max(min_cnt, 3)
            col_extreme_han = 450
        else:
            col_target_han = target_han
            col_min_cnt = min_cnt
            col_extreme_han = 350

        items = overlong_items(col_text, long_han=col_target_han)
        if not items:
            return False
        # 策略 B: 频次门槛（超长条数达到 col_min_cnt 才触发，容忍个别正常展开的专业事实）
        if len(items) >= col_min_cnt:
            return True
        # 极端超长兜底保护：即使未达频次门槛，若单条超过 col_extreme_han 字（极严重大段挤压）依然触发重写
        extreme_items = overlong_items(col_text, long_han=col_extreme_han)
        return bool(extreme_items)

    async def extract_tables() -> list[list[list[str]]]:
        if not row_templates:
            return []
        lines = [
            "你只从【内容来源】中提取指定表格的数据行，只输出 JSON 对象：`{\"tables\": [[[列1, 列2, ...], ...]]}`。",
            "严禁输出任何多余解释，表格按如下模板结构提取：",
        ]
        for ti, rt in enumerate(row_templates):
            limit = _row_limit_for_template(rt)
            suffix = f"（最多 {limit} 行）" if limit else ""
            lines.append(f"- tables[{ti}] 行样例{suffix}：{rt['line'].rstrip()}")
            for col_i, seg in enumerate(rt["fields"], start=1):
                lines.append(f"  - 列{col_i}（{seg['hint']}）")
        lines.extend([
            "",
            "遵守模板要求，各当事方/立场方各占一行，原文明示的人名/机构/诉求照原文写全。",
            "【内容来源】",
            context,
        ])
        user_msg = "\n".join(lines)
        try:
            raw = await _client_text(
                client,
                "你只输出 JSON 格式的表格数据，严格满足 JSON 语法，不要任何多余字符。",
                user_msg,
                json_mode=True,
                temperature=0.0,
                max_tokens=2000,
                label="template/fill_tables",
            )
            tbls = _parse_tables_json_response(raw)
            while len(tbls) < len(row_templates):
                tbls.append([])
            return normalize_fill_tables(tbls, row_templates)
        except Exception:
            logger.warning("column fill extract_tables failed", exc_info=True)
            return []

    async def write(index: int, revision: str = "") -> str:
        """写第 index 栏（0 基）：一次正常 + 一次整改重试。

        ``revision`` 是首轮的整改意见（超长条重写时下发具体修法），空则就是「正常写一栏」。
        """
        hint = str(scalars[index].get("hint") or "")
        title = titles[index]
        others = [t for i, t in enumerate(titles) if i != index and t]

        # 草稿直出快线（Direct Projection）：
        # 个人视角或个人模板直出：直接提取经过严格过滤的本人待办与重点协同（focus_person/focus_thing），跳过大模型调用；
        # 既保障 100% 过滤外围无关杂项人员，又避免大模型幻觉与并发耗时
        if not revision:
            projected = project_column_from_draft(
                context, template, title=title, hint=hint, directives=directives
            )
            if projected and not _is_column_overlong(projected, index):
                projected = _strip_redundant_column_heading(projected, title)
                if _section_has_table(template, title):
                    projected = _strip_markdown_tables(projected)
                if projected.strip():
                    logger.info("column fill direct projection hit for column [%s]", title)
                    return projected

        # 自适应单栏超时：基础超时以 client.timeout 为底（至少 60s），对超重长栏目适度放宽
        raw_to = getattr(client, "timeout", None)
        base_to = float(raw_to) if raw_to else 60.0
        base_to = max(base_to, 60.0)
        _HEAVY_KEYWORDS = ("政策", "工作", "内容", "实录", "记录", "交锋", "要点", "报告", "经过", "清单", "意见", "事项")
        is_heavy = any(kw in title for kw in _HEAVY_KEYWORDS) or len(hint) > 80
        col_to = base_to + (30.0 if is_heavy else 0.0)

        for attempt in range(2):
            cur_to = col_to + (10.0 if attempt > 0 else 0.0)
            # 采样参数动态干预：
            # 1. 尝试重写 (attempt > 0) 或带 revision（如超长重写）时，提升 presence_penalty 至 0.3 并略微抬高温度至 0.35，打破自回归重复循环
            # 2. 首轮针对重点清单或超重大栏目，施加轻微 presence_penalty 0.15，前置规避自回归退化死循环
            cur_pen = 0.3 if (attempt > 0 or revision) else (0.15 if is_heavy else None)
            cur_temp = 0.35 if (attempt > 0 or revision) else None

            pruned_context = _prune_context_for_column(
                context,
                template,
                title=title,
                hint=hint,
                directives=directives,
            )
            user = _column_fill_user(
                pruned_context,
                template,
                index=index + 1,
                total=len(scalars),
                hint=hint,
                title=title,
                others=others,
                revision=revision,
                target_line=target,
                directives=directives,
            )
            text = await _stream_column(
                client,
                user,
                cap=cap,
                ceiling=ceiling,
                label=f"template/fill:{title or index + 1}",
                timeout=cur_to,
                presence_penalty=cur_pen,
                temperature=cur_temp,
            )
            if text:
                text = _strip_redundant_column_heading(text, title)
                if _section_has_table(template, title):
                    text = _strip_markdown_tables(text)
                if text.strip():
                    return text
            revision = (
                "上一版没有产出可用正文（输出为空、超长或出现重复段落）。"
                "只写这一栏最关键的要点，写完立刻停，不要重复任何句子。"
            )
        return ""

    table_task = extract_tables() if row_templates else None
    scalar_tasks = [write(i) for i in range(len(scalars))]
    if table_task is not None:
        all_results = await asyncio.gather(*scalar_tasks, table_task)
        values = list(all_results[:len(scalars)])
        tables = list(all_results[len(scalars)])
    else:
        values = list(await asyncio.gather(*scalar_tasks))
        tables = []

    assembled = assemble_placeholder_output(
        template, {str(i + 1): v for i, v in enumerate(values)}, tables=tables
    )
    assembled = strip_char_budget_meta(strip_outer_markdown_fence(assembled))
    gate = gate_render_output(template, assembled)
    # ① 单条超长：逐栏填充当**硬问题**（能定位到栏）——只重写中招那一栏，一次单栏调用，
    # 比整篇返工便宜一个量级。渲染层的门禁仍把它当 advisory 记账（见 hard_execution）。
    overlong = [i for i, v in enumerate(values) if _is_column_overlong(v, i)]
    hard = list(gate.get("hard_issues") or [])
    blamed = overlong[:2]
    # ② 门禁硬问题：仍按栏名定位（原逻辑）
    for i, t in enumerate(titles):
        if t and t in "；".join(hard) and i not in blamed:
            blamed.append(i)
    blamed = blamed[:2]
    if not blamed:
        if hard:
            logger.info("column fill hard issues（无栏名可定位）：%s", "；".join(hard)[:160])
            return None
        if gate.get("gate_ok"):
            return gate["text"]
        logger.info(
            "column fill advisory-only：%s", "；".join(gate.get("issues") or [])[:160]
        )
        return gate["text"]
    logger.info(
        "column fill 只重写：%s（其中超长条 %d 栏）",
        [titles[i] or i for i in blamed],
        len(overlong),
    )
    for i in blamed:
        values[i] = await write(i, revision=_OVERLONG_ITEM_REVISION if i in overlong else "")
    still = [i for i, v in enumerate(values) if _is_column_overlong(v, i)]
    if still:  # 只重写一轮：再差也保留（同一栏连重两次的收益与代价不成比例）
        logger.warning(
            "column fill 重写后仍有超长条目（保留）：%s", [titles[i] or i for i in still]
        )
    assembled = assemble_placeholder_output(
        template, {str(i + 1): v for i, v in enumerate(values)}, tables=tables
    )
    gate = gate_render_output(template, assembled)
    if gate.get("gate_ok") or not gate.get("hard_issues"):
        return gate["text"]
    return None


async def fill_placeholder_template(
    client: Any,
    context: str,
    template: str,
    *,
    source_han: int | None = None,
    directives: str = "",
    overlong_han: int | None = None,
    overlong_min_count: int | None = None,
) -> str | None:
    """类型一稳定填充：LLM 出字段值，程序拼装正文。

    约束（行数/字数/栏目分工等）全部由 prompt + 模板正文表达；
    代码只做通用结构拼装与校验（残留占位符、固定文字、去空行）。
    若模板有字数提示且明显偏短，会再给一轮「扩写」修订（不写进用户正文）。

    两条路径：**优先走逐栏并发填充**（每栏一次调用、可并发、流式早停，带表格模板由 extract_tables 并发抽取表格，爆炸半径一栏）；
    若逐栏失败才走"整篇一个 JSON"。两者都带 ``max_tokens`` 硬上限（见 length_budget）。
    ``directives``（领域给的本栏写作纪律）两条路径都带，保证回退也不会退回"没纪律"的写法。
    """
    if not template or not template.strip():
        return None
    if detect_template_kind(template) != "placeholder":
        return None
    plan = plan_placeholder_fill(template)
    if not plan["scalars"] and not plan["row_templates"]:
        return None

    return await fill_placeholder_by_columns(
        client,
        context,
        template,
        plan,
        source_han=source_han,
        directives=directives,
        overlong_han=overlong_han,
        overlong_min_count=overlong_min_count,
    )



