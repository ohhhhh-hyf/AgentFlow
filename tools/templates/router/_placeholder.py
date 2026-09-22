"""tools.templates.router.placeholder —— 模板路由·占位符层：占位符模板解析、填充计划与组装。"""
from __future__ import annotations
import asyncio
import contextlib
import logging
import re
from typing import Any

from tools.templates.body_rules import BODY_FORMAT_RULES

from ._base import (
    _PLACEHOLDER_FILL_SYSTEM,
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
            row_templates.append({"line": line, "fields": fields, "indices": [idx]})
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
    """通用清洗：对齐列数、去掉整行空白；若模板写了行数约束则截断。"""
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
    out_lines: list[str] = []
    # 行模板按**行号**定位（同表多行样例会重复出现同样文本，不能按文本匹配）；
    # 每个模板只在它的首行展开一次，其余样例行跳过
    head_idx_to_row: dict[int, int] = {
        int(rt["indices"][0]): i for i, rt in enumerate(row_templates)
    }
    skip_lines: set[int] = {
        int(idx) for rt in row_templates for idx in rt["indices"][1:]
    }

    for line_idx, line in enumerate(template.splitlines(keepends=True)):
        if line_idx in skip_lines or line_idx in caption_lines:
            # 表格栏说明行：不打印正文位、不消耗标量值（否则后续字段全部错位）
            continue
        title_m = _section_title_match(line)
        if title_m:
            hashes, title = title_m.group(1), title_m.group(2).strip()
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
        from tools.templates.template_eval import parse_document_char_budget
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


def build_placeholder_fill_user(
    context: str,
    template: str,
    *,
    revision_notes: str = "",
    target_line: str = "",
    directives: str = "",
) -> str:
    """构造字段 JSON 填充的用户消息（``directives`` = 领域给的本栏写作纪律）。"""
    template, requirement = split_template_meta(template)
    plan = plan_placeholder_fill(template)
    lines = [
        "根据内容来源填充模板，只输出 JSON。",
        "形如 `# [栏名]` 的标题行由程序生成，不要填进 fields；你只填标题下方正文占位。",
    ]
    if directives.strip():
        lines.append(directives.strip())
    if target_line.strip():
        lines.append(target_line.strip())
    lines.extend([
        "固定表头由模板保留；`| … |` 样例行必须换成原文事实，禁止整行照抄省略号。",
        "字段值里不要写 #/## 标题，不要重复栏目标题作前缀。",
        "有据才写；缺内容写该栏约定的缺省词（模板没约定时写「未提及」）；**键必须齐全**：fields 要给出清单里全部编号，缺键＝漏填。",
        "字段值与表格里不得复述、解释或引用模板要求（如「以上均未明确…填写『无』」）；缺内容只写约定的缺省词。",
        "勿照抄「如：」示例；勿张冠李戴；勿改数字；勿用百科补履历；勿虚构原文没有的内容。",
        "各栏按主题分别写清；「与/和/及」并列主题勿揉成一句糊涂话。",
        BODY_FORMAT_RULES,
        "**来源优先级：内容来源（原文/材料）> 已批准要点（草稿）> 索引类摘要**；引话、专名、过程、评价类细节回内容来源取，结论、数字口径与归属以已批准要点为准。",
        "简洁/粗略≠空洞：每栏写清该栏主要事实与要点，可多句。",
        "「一段话概括」不是一句空话：**最多 3 段、每段不超过 400 字；总述栏（首栏）只写一段、不超过 400 字**；只写该栏主题的概括（背景、目的、结论口径），原文有关键数字时可带 1–2 个作锚点，没有则不强求；明细归各自栏目，本栏不复述。",
        "**一栏只写自己的事**：概括/背景栏只交代背景、目的、结论口径，不复述明细栏的内容；明细归各自栏目；**结论栏、速览栏按各自用途可再次呈现同一事实（不算重复）**。",
        "未声明栏位字数上限时，服从上下文【篇幅预算】；没有动态预算时按事实量自然展开，不按原文比例机械扩写；压缩只删套话、铺垫和重复表达，不丢原文事实。",
        *_char_budget_lines(template),
        "语句完整通顺，无半截句；严禁输出「约N字」等字数元说明。",
    ])
    if requirement.strip():
        lines.extend(["", "【模板写作要求】（必须遵守，不要写进 JSON）", requirement.strip()])
    lines.extend([
        "",
        "【内容来源】",
        context,
        "",
        "【模板原文】",
        template,
        "",
        "【标量字段清单】（不含表格行内字段；fields 必须给出下列**全部**编号）",
    ])
    if not plan["scalars"]:
        lines.append("（无标量字段）")
    for i, seg in enumerate(plan["scalars"], start=1):
        lines.append(f"- {_describe_field(i, seg)}")
    lines.append("")
    lines.append("【表格行模板】→ tables[0], tables[1], ...")
    if plan["row_templates"]:
        for ti, rt in enumerate(plan["row_templates"]):
            limit = _row_limit_for_template(rt)
            suffix = f"（最多 {limit} 行；候选多时按置信度/重要性取舍）" if limit else ""
            lines.append(f"- tables[{ti}] 行样例{suffix}：{rt['line'].rstrip()}")
            for i, seg in enumerate(rt["fields"], start=1):
                lines.append(f"  - 列{i}（{seg['hint']}）")
        lines.append(
            "各表独立填充；遵守模板原文对体量/条数的要求；"
            "候选多时优先保留证据明确、信息完整、对结论/执行影响更大的行；"
            "候选少时不要编造凑数；节与表之间不要串内容。"
            "有「等级」列须填 高/中/低 或模板给出的评级符号；有「责任人」列须填原文明示的人，无则写该栏约定的缺省词（模板没约定时写「未提及」）。"
        )
    else:
        lines.append("（无表格行模板，tables 必须为 []）")
    if revision_notes.strip():
        lines.append("")
        lines.append("【上次输出未通过校验，请修正】")
        lines.append(revision_notes.strip())
    return "\n".join(lines)


def parse_fill_response(
    raw: str,
) -> tuple[dict[str, str], list[list[str]], list[list[list[str]]]]:
    """解析填充 JSON → (fields, rows兼容, tables)。"""
    data = _extract_json_object(raw) or {}
    fields_raw = data.get("fields") or data.get("values") or {}
    fields: dict[str, str] = {}
    if isinstance(fields_raw, dict):
        for k, v in fields_raw.items():
            fields[str(k)] = "" if v is None else str(v)
    elif isinstance(fields_raw, list):
        for i, v in enumerate(fields_raw, start=1):
            fields[str(i)] = "" if v is None else str(v)

    tables: list[list[list[str]]] = []
    tables_raw = data.get("tables")
    if isinstance(tables_raw, list) and tables_raw:
        for t in tables_raw:
            tables.append(_parse_row_list(t))
    rows = _parse_row_list(data.get("rows") or [])
    if not tables and rows:
        tables = [rows]
    return fields, rows, tables


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
    "上一版这一栏有超过两百字的长条目：一条里塞了多个事项。"
    "必须拆成多条 `- `：一条一个事项、标签嵌在行首（`- **标签**：内容`）；"
    "同一类目下多条用缩进子条 `  - ` 拆开；条数宁多不漏，不要为了短而丢事实。"
)


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
        from tools.templates.length_budget import effective_doc_budget
    except Exception:  # noqa: BLE001
        return ""
    span = effective_doc_budget(source_han, template)
    if not span:
        return ""
    return (
        f"【本篇目标】正文总量约 {int(span[0])}–{int(span[1])} 汉字（含条目与表格）；"
        "超过上限会被截断，低于下限＝漏了原文事实。"
    )


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
    client: Any, user: str, *, cap: int, ceiling: int, label: str
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
    stream = stream_text(_COLUMN_FILL_SYSTEM, user, max_tokens=cap, label=label)
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
    if not scalars or plan.get("row_templates"):
        return None
    if getattr(client, "stream_text", None) is None:
        return None
    from tools.execution.hard_execution import gate_render_output, overlong_items
    from tools.templates.length_budget import output_token_cap

    cap = output_token_cap(source_han, template)
    ceiling = int(cap * _CHARS_PER_TOKEN)
    target = _target_line(source_han, template)
    titles = _scalar_titles(template)
    if len(titles) != len(scalars):  # 结构对不上就不冒进，回退整篇
        return None

    async def write(index: int, revision: str = "") -> str:
        """写第 index 栏（0 基）：一次正常 + 一次整改重试。

        ``revision`` 是首轮的整改意见（超长条重写时下发具体修法），空则就是「正常写一栏」。
        """
        hint = str(scalars[index].get("hint") or "")
        title = titles[index]
        others = [t for i, t in enumerate(titles) if i != index and t]
        for attempt in range(2):
            user = _column_fill_user(
                context,
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
            )
            if text:
                return text
            revision = (
                "上一版没有产出可用正文（输出为空、超长或出现重复段落）。"
                "只写这一栏最关键的要点，写完立刻停，不要重复任何句子。"
            )
        return ""

    values = list(await asyncio.gather(*(write(i) for i in range(len(scalars)))))
    assembled = assemble_placeholder_output(
        template, {str(i + 1): v for i, v in enumerate(values)}, tables=[]
    )
    assembled = strip_char_budget_meta(strip_outer_markdown_fence(assembled))
    gate = gate_render_output(template, assembled)
    # ① 单条超长：逐栏填充当**硬问题**（能定位到栏）——只重写中招那一栏，一次单栏调用，
    # 比整篇返工便宜一个量级。渲染层的门禁仍把它当 advisory 记账（见 hard_execution）。
    overlong = [i for i, v in enumerate(values) if overlong_items(v)]
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
    still = [i for i, v in enumerate(values) if overlong_items(v)]
    if still:  # 只重写一轮：再差也保留（同一栏连重两次的收益与代价不成比例）
        logger.warning(
            "column fill 重写后仍有超长条目（保留）：%s", [titles[i] or i for i in still]
        )
    assembled = assemble_placeholder_output(
        template, {str(i + 1): v for i, v in enumerate(values)}, tables=[]
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
) -> str | None:
    """类型一稳定填充：LLM 出字段值，程序拼装正文。

    约束（行数/字数/栏目分工等）全部由 prompt + 模板正文表达；
    代码只做通用结构拼装与校验（残留占位符、固定文字、去空行）。
    若模板有字数提示且明显偏短，会再给一轮「扩写」修订（不写进用户正文）。

    两条路径：**无表格模板先走逐栏填充**（每栏一次调用、可并发、流式早停，爆炸半径一栏）；
    有表格或逐栏失败才走"整篇一个 JSON"。两者都带 ``max_tokens`` 硬上限（见 length_budget）。
    ``directives``（领域给的本栏写作纪律）两条路径都带，保证回退也不会退回"没纪律"的写法。
    """
    if not template or not template.strip():
        return None
    if detect_template_kind(template) != "placeholder":
        return None
    plan = plan_placeholder_fill(template)
    if not plan["scalars"] and not plan["row_templates"]:
        return None

    try:
        from tools.templates.length_budget import output_token_cap
        from tools.templates.template_eval import parse_document_char_budget
    except Exception:  # noqa: BLE001
        parse_document_char_budget = None  # type: ignore[assignment]
        output_token_cap = None  # type: ignore[assignment]
    budget = (
        parse_document_char_budget(template) if parse_document_char_budget else {}
    )
    cap = output_token_cap(source_han, template) if output_token_cap else None

    if not plan["row_templates"]:
        by_column = await fill_placeholder_by_columns(
            client, context, template, plan, source_han=source_han, directives=directives
        )
        if by_column:
            return by_column

    revision = ""
    try:
        for attempt in range(3):
            raw = await _client_text(
                client,
                _PLACEHOLDER_FILL_SYSTEM,
                build_placeholder_fill_user(
                    context,
                    template,
                    revision_notes=revision,
                    target_line=_target_line(source_han, template),
                    directives=directives,
                ),
                json_mode=True,
                temperature=0.0 if attempt == 0 else 0.2,
                max_tokens=cap,
                label="template/fill",
            )
            fields, rows, tables = parse_fill_response(raw)
            if not tables and rows:
                tables = [rows]
            while len(tables) < len(plan["row_templates"]):
                tables.append([])
            tables = normalize_fill_tables(tables, plan["row_templates"])
            # 字段值内若误写字数元说明 / 代码围栏，先剥掉再拼装
            fields = {
                k: strip_char_budget_meta(strip_outer_markdown_fence(v)).strip()
                if isinstance(v, str)
                else v
                for k, v in fields.items()
            }
            assembled = assemble_placeholder_output(
                template,
                fields,
                tables=tables,
            )
            assembled = strip_outer_markdown_fence(assembled)
            assembled = strip_char_budget_meta(assembled)
            # 漏填兜底（只拦「缺 / 空 / 解析失败」，不拦「偏短」）：
            # 拼装按位置填充、栏目标题由程序打印，所以字段缺失或空白时产出的是
            # 「只有栏目标题、正文空着」的半截文档（观感像被截断）。
            # 旧判定只在「所有字段 + 所有表都空」时才拦，缺一两栏会静默通过。
            blank = [
                i
                for i, _seg in enumerate(plan["scalars"], start=1)
                if not str(fields.get(str(i), "")).strip()
            ]
            no_rows = not any(tables[i] for i in range(len(plan["row_templates"])))
            all_empty = no_rows and not any(str(v).strip() for v in fields.values())
            if blank or all_empty:
                logger.warning(
                    "placeholder fill incomplete (attempt=%s)：blank=%s all_empty=%s raw[:160]=%r",
                    attempt + 1,
                    blank,
                    all_empty,
                    (raw or "")[:160].replace("\n", " "),
                )
                if attempt < 2:
                    named = "、".join(f"字段{i}" for i in blank) or "全部标量字段"
                    revision = (
                        f"上次输出漏填或留空了这些栏目：{named}。"
                        "fields 必须给出清单里的全部编号（缺键＝漏填），"
                        "每一栏都要有内容；内容来源里确实没有依据的按该栏约定缺省词填写（模板没约定时写「未提及」）。"
                        "请只输出 JSON：{\"fields\": {\"1\": \"…\"}, \"tables\": []}，"
                        "每个字段按占位说明写原文要点，不得留空、不得只留标题。"
                    )
                    continue
                # 三轮仍缺栏：不再 return None（整篇退回 freeform 会丢模板结构），
                # 改为给仍空的字段补缺省词继续走完校验——漏填已有三轮机会，
                # 最终宁可让该栏显式写「未提及」，也不放半截文档或丢结构。
                for i in blank:
                    fields[str(i)] = "未提及"
                assembled = assemble_placeholder_output(template, fields, tables=tables)
                logger.warning(
                    "placeholder blanks filled with default word (attempt=%s)：%s",
                    attempt + 1,
                    blank,
                )
            # 篇幅自检：只在模板声明了字数约束时才修订（偏短扩写、偏长压缩，不写进用户正文）。
            # 未声明约束时不因「偏短」打回——篇幅以原文为上限，信息少就写少，避免逼出注水。
            logger.debug("placeholder fill attempt=%s han=%s", attempt + 1, _body_han_count(assembled))
            lo = budget.get("lo") if isinstance(budget, dict) else None
            hi = budget.get("hi") if isinstance(budget, dict) else None
            if (lo or hi) and attempt < 2:
                han = _body_han_count(assembled)
                lo_i = int(lo or 0)
                hi_i = int(hi or 0)
                if lo_i and han < int(lo_i * 0.85):
                    revision = (
                        f"当前各字段合计约 {han} 字，少于模板约 {lo_i}–{hi_i or lo_i} 字。"
                        "请在保持结构与忠实原文的前提下整体扩写："
                        "只扩充原文已经出现或能由上下文直接支持的事实、推进、原因、影响与结论，"
                        "把过短的句子解释清楚、合并相关上下文；"
                        "绝对不要新增原文没有的人名、数字、期限、评价或因果。"
                        "使合计接近区间中位；勿空话注水、勿截断半句、勿写字数说明。"
                    )
                    logger.info(
                        "placeholder too short (%s<%s), attempt=%s expand",
                        han,
                        lo_i,
                        attempt + 1,
                    )
                    continue
                if hi_i and han > hi_i:
                    target = (lo_i + hi_i) // 2 if lo_i else max(hi_i - 40, hi_i * 4 // 5)
                    revision = (
                        f"当前各字段合计约 {han} 字，超过模板上界 {hi_i} 字。"
                        f"请整体压缩改写到约 {target}–{hi_i} 字（不是截断半句）："
                        "每节改短句，删除寒暄、重复、背景铺垫、低确定性猜测和不影响结论的枝节，"
                        "优先保留关键结论、数字、责任人、期限、风险影响与应对；"
                        "压缩后语句仍须完整通顺；勿改结构、勿虚构。"
                    )
                    logger.info(
                        "placeholder too long (%s>%s), attempt=%s compress",
                        han,
                        hi_i,
                        attempt + 1,
                    )
                    continue
            # 强执行：截断/去粘连/空表占位后再验收
            from tools.execution.hard_execution import gate_render_output

            gate = gate_render_output(template, assembled)
            assembled = gate["text"]
            issues = list(gate.get("issues") or [])
            if gate.get("gate_ok"):
                return assembled
            revision = "\n".join(f"- {x}" for x in issues)
            logger.info(
                "placeholder gate failed (attempt=%s): %s",
                attempt + 1,
                "；".join(issues),
            )
            if attempt >= 1:
                # 多轮后仍无硬伤则接受当前拼装，交给上层 freeform/repair 的情况仅在硬伤时
                hard = list(gate.get("hard_issues") or [])
                if not hard:
                    return assembled
        return None
    except Exception:  # noqa: BLE001
        logger.warning("placeholder json fill failed, fallback to free render", exc_info=True)
        return None


