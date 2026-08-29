"""tools.template_router.placeholder —— 模板路由·占位符层：占位符模板解析、填充计划与组装。"""
from __future__ import annotations
import logging
import re
from typing import Any

from ._base import _PLACEHOLDER_FILL_SYSTEM, _PLACEHOLDER_RE, _TABLE_SEP_RE, _body_han_count, _char_budget_lines, _client_text, _describe_field, _extract_json_object, _hint_clean, _hint_short, _parse_row_list, _table_row_confidence_score, strip_outer_markdown_fence
from ._detect import _looks_like_placeholder, _parse_field, _row_limit_for_template, detect_template_kind, strip_char_budget_meta

logger = logging.getLogger(__name__)


def _line_placeholders(line: str) -> list[re.Match[str]]:
    out: list[re.Match[str]] = []
    for m in _PLACEHOLDER_RE.finditer(line):
        nxt = line[m.end() : m.end() + 1]
        if _looks_like_placeholder(m.group(1), next_char=nxt):
            out.append(m)
    return out


def _is_table_data_row(line: str) -> bool:
    if line.count("|") < 2:
        return False
    if _TABLE_SEP_RE.match(line):
        return False
    return bool(_line_placeholders(line))


def plan_placeholder_fill(template: str) -> dict[str, Any]:
    """分析模板结构（通用）：标量占位符顺序 + 表格行模板。

    不做任何业务语义判断（行数/栏目含义等约束由 prompt + 模板正文表达）。
    """
    scalars: list[dict] = []
    row_templates: list[dict[str, Any]] = []
    for line in template.splitlines(keepends=True):
        phs = _line_placeholders(line)
        if not phs:
            continue
        if _is_table_data_row(line):
            row_templates.append(
                {
                    "line": line,
                    "fields": [_parse_field(m.group(1)) for m in phs],
                }
            )
            continue
        for m in phs:
            scalars.append(_parse_field(m.group(1)))
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
    # 同一行模板只展开一次（模板里每张表只有一行样例）
    expanded_row_ids: set[int] = set()

    for line in template.splitlines(keepends=True):
        phs = _line_placeholders(line)
        if not phs:
            out_lines.append(line)
            continue

        row_idx = next(
            (
                i
                for i, rt in enumerate(row_templates)
                if rt["line"] == line and i not in expanded_row_ids
            ),
            None,
        )
        if row_idx is not None:
            expanded_row_ids.add(row_idx)
            rt = row_templates[row_idx]
            n_cols = max(len(rt["fields"]), 1)
            use_rows = list(tables[row_idx]) if tables[row_idx] else []
            # 无数据时一行占位，避免多行空白表（通用，无业务语义）
            if not use_rows:
                use_rows = [["未提及"] + ["—"] * (n_cols - 1)]
            for row in use_rows:
                rendered = _replace_placeholders_in_line(
                    line, list(row), rt["fields"]
                )
                # 多行展开时每行必须独立成行；模板末行常无尾换行，
                # 若只在 line.endswith("\n") 时补换行，会把多行糊成一行（|| 粘连）
                if not rendered.endswith("\n"):
                    rendered += "\n"
                out_lines.append(rendered)
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
    lines = (template or "").splitlines()
    for idx, line in enumerate(lines):
        if line.rstrip() != row_line:
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
            elif len(phs) == 1 and re.search(r"\[[^\[\]]+\]\s*$", body) and not re.search(r"[:：]\s*\[", body):
                # 单占位在行尾且无冒号 → 段落输入区（如「## 纪要\n[内容]」展开成 field）
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
        from tools.template_eval import parse_document_char_budget
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
) -> str:
    """构造字段 JSON 填充的用户消息。"""
    plan = plan_placeholder_fill(template)
    lines = [
        "根据内容来源填充模板，只输出 JSON。",
        "固定标题/表头由模板保留，你只填 [占位] 正文；字段值里不要写 #/## 标题，不要重复栏目标题前缀。",
        "有据才写；某栏主题在来源中完全无信息时才「未提及」。",
        "勿照抄「如：」示例；勿张冠李戴；勿改数字；勿用百科补履历；勿虚构原文没有的内容。",
        "各栏按主题分别写清；「与/和/及」并列主题勿揉成一句糊涂话。",
        "简洁/粗略≠空洞：每栏写清该栏主要事实与要点，可多句。",
        *_char_budget_lines(template),
        "语句完整通顺，无半截句；严禁输出「约N字」等字数元说明。",
        "",
        "【内容来源】",
        context,
        "",
        "【模板原文】",
        template,
        "",
        "【标量字段清单】（不含表格行内字段）",
    ]
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


async def fill_placeholder_template(
    client: Any,
    context: str,
    template: str,
) -> str | None:
    """类型一稳定填充：LLM 只出字段 JSON，程序拼装正文。

    约束（行数/字数/栏目分工等）全部由 prompt + 模板正文表达；
    代码只做通用结构拼装与校验（残留占位符、固定文字、去空行）。
    若模板有字数提示且明显偏短，会再给一轮「扩写」修订（不写进用户正文）。
    """
    if not template or not template.strip():
        return None
    if detect_template_kind(template) != "placeholder":
        return None
    plan = plan_placeholder_fill(template)
    if not plan["scalars"] and not plan["row_templates"]:
        return None

    try:
        from tools.template_eval import parse_document_char_budget
    except Exception:  # noqa: BLE001
        parse_document_char_budget = None  # type: ignore[assignment]
    budget = (
        parse_document_char_budget(template) if parse_document_char_budget else {}
    )

    revision = ""
    try:
        for attempt in range(3):
            raw = await _client_text(
                client,
                _PLACEHOLDER_FILL_SYSTEM,
                build_placeholder_fill_user(
                    context, template, revision_notes=revision
                ),
                json_mode=True,
                temperature=0.0 if attempt == 0 else 0.2,
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
            # 篇幅自检：偏短扩写、偏长压缩（不改结构、不写进用户正文）
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
                        "占位符填充偏短（%s<%s），attempt=%s 请求扩写",
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
                        "占位符填充偏长（%s>%s），attempt=%s 请求压缩",
                        han,
                        hi_i,
                        attempt + 1,
                    )
                    continue
            # 强执行：截断/去粘连/空表占位后再验收
            from tools.hard_execution import gate_render_output

            gate = gate_render_output(template, assembled)
            assembled = gate["text"]
            issues = list(gate.get("issues") or [])
            if gate.get("gate_ok"):
                return assembled
            revision = "\n".join(f"- {x}" for x in issues)
            logger.info(
                "占位符填充未过门禁（attempt=%s）：%s",
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
        logger.warning("占位符 JSON 填充失败，回退自由渲染", exc_info=True)
        return None


