"""tools.template_router.preview —— 模板路由·可读化层：预览/可读文本/编辑模型的转换。"""
from __future__ import annotations
import logging
import re
from typing import Any

from ._base import _BANNER_RE, _OLD_FILL_RE, _PLACEHOLDER_RE, _field_slot_line, _format_budget_banner, _is_slot_body, _split_aspect_connectors, _split_by_heading, _strip_heading_number
from ._detect import detect_template_kind
from ._placeholder import preview_to_template, template_to_preview

logger = logging.getLogger(__name__)


def extract_listed_aspects(description: str) -> list[str]:
    """从自然语言里抽出并列要点名（顿号 / 与 / 和 / 及），用于编译保真。

    例：
    - 「概括背景、对象、核心目的」→ 三项
    - 「整体梳理流程与核心脉络」→ [流程, 核心脉络]
    """
    text = description or ""
    aspects: list[str] = []

    def _strip_lead(chunk: str) -> str:
        # 可叠剥引导语：整体梳理…、概括…、只要三部分：…、只要…
        prev = None
        while prev != chunk:
            prev = chunk
            chunk = re.sub(
                r"^(?:请)?(?:约?\d+\s*[-–—~～]?\s*\d*\s*字)",
                "",
                chunk,
            ).strip(" ，,：:")
            chunk = re.sub(
                r"^(?:只要|仅需|只需|需要)(?:约)?"
                r"(?:[一二三四五六七八九十两\d]+\s*(?:部分|段|块|节|点))?"
                r"[：:，,\s]*",
                "",
                chunk,
            ).strip(" ，,：:")
            chunk = re.sub(
                r"^(?:约)?"
                r"[一二三四五六七八九十两\d]+\s*(?:部分|段|块|节|点)"
                r"[：:，,\s]*",
                "",
                chunk,
            ).strip(" ，,：:")
            chunk = re.sub(
                r"^(?:整体|分别|依次|逐一|并|再|并请)",
                "",
                chunk,
            ).strip(" ，,：:")
            chunk = re.sub(
                r"^(?:用[^，,]{0,12})?(?:概括|梳理|说明|写清|写明|覆盖|包含|包括|"
                r"总结|提炼|描述|介绍|回顾)",
                "",
                chunk,
            ).strip(" ，,：:")
            # 尾部数量壳：「…两段」「…三部分」
            chunk = re.sub(
                r"(?:约)?[一二三四五六七八九十两\d]+\s*(?:部分|段|块|节|点)$",
                "",
                chunk,
            ).strip(" ，,：:")
        return chunk

    def _clean_piece(p: str) -> str:
        p = (p or "").strip()
        p = re.sub(r"^(?:以及|和|与|及)", "", p).strip()
        p = _strip_lead(p)
        return p.strip()

    # 按句号/分号/逗号切开，再在片段内处理顿号与「与/和/及」
    for chunk in re.split(r"[。；;\n，,]", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        # 纯字数约束片段跳过
        if re.fullmatch(r"(?:约?\d+\s*[-–—~～]?\s*\d*\s*字)", chunk):
            continue
        if "、" not in chunk and not re.search(r"[与和及]", chunk):
            continue
        chunk = _strip_lead(chunk)
        if not chunk:
            continue
        pieces = (
            [p.strip() for p in chunk.split("、") if p.strip()]
            if "、" in chunk
            else [chunk]
        )
        for p in pieces:
            p = _clean_piece(p)
            if not p:
                continue
            for sub in _split_aspect_connectors(p):
                sub = _clean_piece(sub)
                # 过滤纯数字/字数
                if re.fullmatch(r"[\d\s\-–—~～字约]+", sub):
                    continue
                if 2 <= len(sub) <= 16 and re.search(r"[\u4e00-\u9fff]", sub):
                    aspects.append(sub)

    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for a in aspects:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def _heading_covers_aspect_alone(
    title: str, aspect: str, all_aspects: list[str]
) -> bool:
    """标题是否单独承载某一并列要点（拒绝「A与B」合并标题冒充两侧都覆盖）。"""
    clean = _strip_heading_number(title)
    if not clean or aspect not in clean:
        return False
    others = [a for a in all_aspects if a != aspect and a in clean]
    if others and re.search(r"[与和及、]", clean):
        return False
    return True


def _heading_line_is_placeholder_only(heading_inner: str) -> bool:
    """标题行内容是否几乎只是一个占位（如 ``[写背景]``），没有固定栏目名。"""
    inner = (heading_inner or "").strip()
    # 去掉编号后再看
    inner = _strip_heading_number(inner)
    if not inner:
        return True
    # 整段就是一个 [占位]
    if re.fullmatch(r"\[[^\[\]]+\]", inner):
        return True
    # 去掉所有占位后几乎没有中文固定字
    fixed = re.sub(r"\[[^\[\]]+\]", "", inner).strip()
    return not re.search(r"[\u4e00-\u9fffA-Za-z]{2,}", fixed)


def _aspect_has_fixed_heading(
    aspect: str, compiled: str, all_aspects: list[str]
) -> bool:
    """并列要点是否有**固定文字**小节标题（栏目名可见，非「标题即占位」）。"""
    for m in re.finditer(r"(?m)^(#{1,3})\s+(.+)$", compiled or ""):
        raw_title = m.group(2).strip()
        if _heading_line_is_placeholder_only(raw_title):
            continue
        if _heading_covers_aspect_alone(raw_title, aspect, all_aspects):
            return True
    for m in re.finditer(
        r"(?m)^\s*(?:[0-9]+[\.、]|[一二三四五六七八九十]+[、.])\s*(\S.+)$",
        compiled or "",
    ):
        raw_title = m.group(1).strip()
        if _heading_line_is_placeholder_only(raw_title):
            continue
        if _heading_covers_aspect_alone(raw_title, aspect, all_aspects):
            return True
    return False


def _aspect_has_own_slot(
    aspect: str, compiled: str, all_aspects: list[str]
) -> bool:
    """并列要点是否拥有独立小节标题或独立占位说明。"""
    if _aspect_has_fixed_heading(aspect, compiled, all_aspects):
        return True
    # 占位说明单独点名该要点，且同占位未同时塞进另一并列要点
    for m in _PLACEHOLDER_RE.finditer(compiled or ""):
        hint = m.group(1)
        if aspect not in hint:
            continue
        others = [a for a in all_aspects if a != aspect and a in hint]
        if others and re.search(r"[与和及、]", hint):
            continue
        return True
    return False


def preview_to_readable(preview: dict[str, Any]) -> str:
    """把预览模型渲染成用户能看懂、能改的版式稿（不是占位符）。

    开头一行【版式】写清全文/本段/表格行数；下面是普通 Markdown：
    标题、空段用「（本段约N字，生成时填写）」，表格是真表头+空行。
    """
    template = str((preview or {}).get("template_raw") or "")
    sections = (preview or {}).get("sections") or []
    out: list[str] = [_format_budget_banner(template), ""]
    for sec in sections:
        stype = sec.get("type")
        if stype == "title":
            level = int(sec.get("level") or 1)
            text = str(sec.get("text") or "").strip()
            if sec.get("raw_field"):
                out.append(f"{'#' * min(level, 6)} （标题，生成时填写）")
            else:
                out.append(f"{'#' * min(level, 6)} {text}")
        elif stype == "label":
            out.append(str(sec.get("text") or ""))
        elif stype == "field":
            hint = str(sec.get("hint") or "").strip()
            value = str(sec.get("value") or "").strip()
            out.append(value or _field_slot_line(hint))
            out.append("")
        elif stype == "table":
            title = str(sec.get("title") or "").strip()
            title_norm = re.sub(r"^#+\s*", "", title)
            if title and not any(
                re.sub(r"^#+\s*", "", s.strip()) == title_norm for s in out
            ):
                out.append(f"## {title}")
            headers = [str(h) for h in (sec.get("headers") or [])]
            out.append("| " + " | ".join(headers) + " |")
            out.append("| " + " | ".join("---" for _ in headers) + " |")
            row_hints = [str(h) for h in (sec.get("row_hint") or [])]
            row_n = None
            for hint in row_hints:
                m = re.search(r"约\s*(\d+)\s*行", hint)
                if m:
                    row_n = m.group(1)
                    break
            first = f"（约{row_n}行，生成时填写）" if row_n else "（生成时填写）"
            cells = [first] + [""] * max(0, len(headers) - 1)
            if headers:
                out.append("| " + " | ".join(cells[: len(headers)]) + " |")
            out.append("")
        else:
            out.append(str(sec.get("text") or ""))
    return "\n".join(out).strip()


def _orig_placeholder_for_heading(template_raw: str, title: str) -> str | None:
    if not template_raw or not title:
        return None
    title_norm = re.sub(r"^#+\s*", "", title).strip()
    chunks = _split_by_heading(template_raw)
    for _prefix, raw_title, body in chunks:
        raw_norm = re.sub(r"\[[^\[\]]*\]", "", raw_title).strip()
        if title_norm and (title_norm == raw_norm or title_norm in raw_norm or raw_norm in title_norm):
            found = re.search(r"\[[^\[\]]+\]", body)
            if found:
                return found.group(0)
            if "|" in body:
                return None
    return None


def readable_to_template(readable: str, template_raw: str) -> str:
    """把用户改过的版式稿还原成占位模板（供渲染）。

    - 空着或仍是「（生成时填写）」→ 用原模板该节的占位（含本段约 N 字）
    - 用户写成正文 → 当作该节已定内容
    - 旧版「【填这里：…】」仍兼容
    """
    text = (readable or "").strip()
    if not text:
        return template_raw
    if _OLD_FILL_RE.search(text) and "【版式】" not in text:
        text = re.sub(
            r"【填这里：([^】]*)】",
            lambda m: f"[{m.group(1).strip() or '内容'}]",
            text,
        )
        text = re.sub(r"【([^】]+)】", lambda m: f"[{m.group(1).strip()}]", text)
        return text

    banner = ""
    m_banner = _BANNER_RE.search(text)
    if m_banner:
        banner = m_banner.group(0)
        text = _BANNER_RE.sub("", text).strip()

    orig_chunks = _split_by_heading(template_raw or "")
    new_chunks = _split_by_heading(text)
    if not new_chunks:
        return template_raw

    out: list[str] = []
    for prefix, title, body in new_chunks:
        if prefix.startswith("#") and _is_slot_body(title):
            restored = next(
                (p for p, _t, _b in orig_chunks if p.startswith("#") and "[" in p),
                "",
            )
            out.append(restored or prefix)
        elif prefix.startswith("#"):
            out.append(prefix)
        elif title:
            out.append(f"## {title}")
        if "|" in body:
            rebuilt = []
            for line in body.splitlines():
                if line.count("|") >= 2 and "---" not in line:
                    cells = [c.strip() for c in line.strip().strip("|").split("|")]
                    if cells and _is_slot_body(cells[0]) and all(
                        _is_slot_body(c) for c in cells[1:]
                    ):
                        # 保留原表的占位数据行
                        orig_body = ""
                        for _p, ot, ob in orig_chunks:
                            on = re.sub(r"\[[^\[\]]*\]", "", ot).strip()
                            if title and (title == on or title in on or on in title):
                                orig_body = ob
                                break
                        row = next(
                            (
                                ln
                                for ln in orig_body.splitlines()
                                if ln.count("|") >= 2
                                and "---" not in ln
                                and "[" in ln
                            ),
                            "",
                        )
                        rebuilt.append(row or line)
                        continue
                rebuilt.append(line)
            out.append("\n".join(rebuilt).strip())
            continue
        if _is_slot_body(body):
            ph = _orig_placeholder_for_heading(template_raw, title)
            if ph:
                out.append(ph)
            elif body:
                out.append("[该节正文；无则写「未提及」]")
        else:
            out.append(body)
    result = "\n\n".join(x for x in out if x).strip()

    # 用户改了版式行里的数字时，写回对应占位
    if banner and result:
        result = _apply_banner_overrides(banner, result)
    return result or (template_raw or "")


def _apply_banner_overrides(banner: str, template: str) -> str:
    """把【版式】里用户改过的全文/本段数字写回占位说明。"""
    body = template
    full = re.search(r"全文约\s*(\d+)(?:\s*[-–—~～至到]\s*(\d+))?\s*字", banner)
    if full:
        lo, hi = full.group(1), full.group(2)
        hint = f"全文合计约{lo}-{hi}字" if hi else f"全文合计约{lo}字"
        if re.search(r"全文合计约\s*\d+", body):
            body = re.sub(
                r"全文合计约\s*\d+(?:\s*[-–—~～至到]\s*\d+)?\s*字",
                hint,
                body,
                count=1,
            )
        else:
            m = re.search(r"\[[^\[\]]+\]", body)
            if m:
                inner = m.group(0)[1:-1].strip()
                body = body[: m.start()] + f"[{inner}；{hint}]" + body[m.end() :]
    for title, num in re.findall(r"([^：:。；;]+?)：本段约\s*(\d+)\s*字", banner):
        title = title.strip()
        chunks = _split_by_heading(body)
        rebuilt: list[str] = []
        for prefix, raw_title, sec in chunks:
            raw_norm = re.sub(r"\[[^\[\]]*\]", "", raw_title).strip()
            block = (prefix + ("\n" + sec if sec else "")).strip()
            if title and (title == raw_norm or title in raw_norm or raw_norm in title):
                if re.search(r"本段约\s*\d+", block):
                    block = re.sub(r"本段约\s*\d+\s*字", f"本段约{num}字", block, count=1)
                elif re.search(r"\[[^\[\]]+\]", block):
                    def _inject(match: re.Match[str], n: str = num) -> str:
                        inner = match.group(1).strip()
                        if "本段约" in inner:
                            inner = re.sub(r"本段约\s*\d+\s*字", f"本段约{n}字", inner)
                            return f"[{inner}]"
                        return f"[{inner}；本段约{n}字]"

                    block = re.sub(r"\[([^\[\]]+)\]", _inject, block, count=1)
            rebuilt.append(block)
        body = "\n\n".join(x for x in rebuilt if x)
    return body


def preview_to_edit_model(preview: dict[str, Any]) -> dict[str, Any]:
    """把预览模型转成**结构化编辑组件**的数据（Gradio 渲染所见即所得编辑器用）。

    返回：
    - ``title``: 文档标题（第一个 # 标题，若存在）
    - ``paragraphs``: [{label, hint, value}] —— 每个字段段落一个输入框
      （label = 相邻标题/标签；hint = 灰字提示；value = 用户已填内容）
    - ``tables``: [{title, headers, rows, row_hint}] —— 每张表一个可编辑表格
    - ``labels``: [{text}] —— 固定标签行（如「- 时间：」）
    - ``char_budget``: 字数约束（内部用）
    - ``template_raw``: 原始占位模板（回填用，不展示）
    """
    sections = (preview or {}).get("sections") or []
    paragraphs: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    title = ""
    pending_label = ""  # 段标签与相邻字段的配对

    for sec in sections:
        stype = sec.get("type")
        if stype == "title":
            text = str(sec.get("text") or "").strip()
            if not title and text:
                title = text
            else:
                labels.append({"text": text})
        elif stype == "label":
            text = str(sec.get("text") or "").strip()
            if text:
                pending_label = text
        elif stype == "field":
            hint = str(sec.get("hint") or "").strip() or "内容"
            paragraphs.append(
                {
                    "label": pending_label or hint[:12],
                    "hint": hint,
                    "value": str(sec.get("value") or ""),
                }
            )
            pending_label = ""
        elif stype == "table":
            tables.append(
                {
                    "title": str(sec.get("title") or "").strip(),
                    "headers": [str(h) for h in (sec.get("headers") or [])],
                    "rows": [
                        [str(c) for c in (row or [])]
                        for row in (sec.get("rows") or [])
                    ],
                    "row_hint": [str(h) for h in (sec.get("row_hint") or [])],
                }
            )
        else:
            text = str(sec.get("text") or "").strip()
            if text:
                labels.append({"text": text})

    return {
        "title": title,
        "paragraphs": paragraphs,
        "tables": tables,
        "labels": labels,
        "char_budget": (preview or {}).get("char_budget") or {},
        "template_raw": (preview or {}).get("template_raw") or "",
    }


def edit_model_to_template(edit_model: dict[str, Any], template_raw: str) -> str:
    """把用户编辑后的**结构化编辑数据**组装回占位模板（供渲染/回填）。

    - 段落 value 非空 → 作为该段内容（生成时优先）
    - 表格 rows 有内容 → 作为表格数据行
    - 空段落/空表格行 → 保留占位（让渲染 agent 填）
    返回占位模板：已填部分为实际内容，未填部分为 [提示]。
    """
    paragraphs = (edit_model or {}).get("paragraphs") or []
    tables = (edit_model or {}).get("tables") or []
    title = str((edit_model or {}).get("title") or "").strip()
    labels = (edit_model or {}).get("labels") or []

    # 用 template_raw 作为骨架，把用户填的段落/表格写回
    if template_raw and detect_template_kind(template_raw) == "placeholder":
        preview = template_to_preview(template_raw)
        sections = preview.get("sections") or []
        field_i = 0
        table_i = 0
        for sec in sections:
            stype = sec.get("type")
            if stype == "field" and field_i < len(paragraphs):
                sec["value"] = paragraphs[field_i].get("value") or ""
                field_i += 1
            elif stype == "table" and table_i < len(tables):
                t = tables[table_i]
                headers = [str(h) for h in (t.get("headers") or [])]
                n = len(headers)
                rows = [
                    [str(c) for c in (row or [])] for row in (t.get("rows") or [])
                ]
                rows = [r[:n] + [""] * (n - len(r)) if len(r) < n else r[:n] for r in rows]
                sec["rows"] = rows
                table_i += 1
        # 标题/标签文字更新
        title_done = False
        for sec in sections:
            if sec.get("type") == "title" and not title_done and title:
                sec["text"] = title
                title_done = True
        return preview_to_template(preview)

    # 无原始模板：从编辑模型直接组装（标题 + 段落 + 表格）
    out: list[str] = []
    if title:
        out.append(f"# [{title or '标题'}]")
    for label in labels:
        text = str(label.get("text") or "").strip()
        if text:
            out.append(text)
    for para in paragraphs:
        hint = str(para.get("hint") or "").strip() or "内容"
        value = str(para.get("value") or "").strip()
        out.append(value if value else f"[{hint}]")
    for t in tables:
        t_title = str(t.get("title") or "").strip()
        headers = [str(h) for h in (t.get("headers") or [])]
        if t_title:
            out.append(f"## {t_title}")
        out.append("| " + " | ".join(headers) + " |")
        out.append("| " + " | ".join("---" for _ in headers) + " |")
        rows = t.get("rows") or []
        if rows:
            for row in rows:
                cells = [str(c) for c in (row or [])]
                while len(cells) < len(headers):
                    cells.append("")
                out.append("| " + " | ".join(cells[: len(headers)]) + " |")
    return "\n".join(out).strip()


