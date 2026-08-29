"""tools.template_router.detect —— 模板路由·判型层：模板类型识别与规格/占位符输入构建。"""
from __future__ import annotations
import logging
import re
from typing import Any

from tools.template_prompt import PLACEHOLDER_RULES, SPEC_RULES

from ._base import _CHAR_META_LINE_RE, _CHAR_META_TAIL_RE, _CN_RE, _CUE_PATTERNS, _EMOJI_RE, _ENUM_SEP_RE, _HINT_WORD_RE, _MISSING_HINT_RE, _PLACEHOLDER_RE, _SPEC_EXAMPLE_MARKERS, _SPEC_KEYWORDS, _SPEC_SPLIT_MARKERS, _char_budget_lines, _describe_field, _parse_count_token, is_router_enabled

logger = logging.getLogger(__name__)


def _looks_like_placeholder(content: str, next_char: str = "") -> bool:
    """判断 ``[...]`` 括号内容是否真是"占位符说明"（而非 JSON/代码/链接等）。

    占位符的特征：含中文说明词、含 emoji 状态枚举、多选一短选项；
    JSON 对象（``{...}``）、字符串字面量（``"..."``）不算占位符；
    Markdown 链接（``[文字](url)``，后随 ``(``）也不算。
    """
    content = content.strip()
    if not content:
        return False
    # Markdown 链接形态：[xxx](url)
    if next_char == "(":
        return False
    # JSON / 字面量形态：不是占位符
    if content.startswith("{") or content.startswith('"') or content.startswith("["):
        return False
    if _CN_RE.search(content):
        return True
    if _EMOJI_RE.search(content):
        return True
    parts = [p.strip() for p in _ENUM_SEP_RE.split(content) if p.strip()]
    if len(parts) >= 2 and all(len(p) <= 12 for p in parts):
        return True
    if _HINT_WORD_RE.search(content):
        return True
    return False


def detect_template_kind(text: str) -> str:
    """确定性判型（不调 LLM）：

    - 含 ``[xxx]`` 占位符 → ``placeholder``
    - 含格式指令关键词 + 示例信号 → ``spec``
    - 其余 → ``natural``（自然语言描述）
    """
    if not text or not text.strip():
        return "natural"
    if any(
        _looks_like_placeholder(
            m.group(1), next_char=text[m.end() : m.end() + 1]
        )
        for m in _PLACEHOLDER_RE.finditer(text)
    ):
        return "placeholder"
    # 整段偏散文、仅有 0-1 个疑似括号时，优先 natural，避免口语里的「例如」误判 spec
    prose_like = (
        len(text.strip()) < 400
        and "\n# " not in text
        and not text.strip().startswith("#")
        and text.count("```") == 0
    )
    if any(kw in text for kw in _SPEC_KEYWORDS) and any(
        marker in text for marker in _SPEC_EXAMPLE_MARKERS
    ):
        if prose_like and "输入：" not in text and "输出：" not in text:
            return "natural"
        return "spec"
    return "natural"


def parse_placeholder_template(template: str) -> list[dict]:
    """把占位符模板拆成段序列（交替：固定文字 / 字段）。

    返回示例：:

        [
            {"kind": "text", "text": "# "},
            {"kind": "field", "raw": "会议主题", "hint": "会议主题",
             "enum": None, "missing": False},
            {"kind": "text", "text": "\\n\\n- **时间**："},
            ...
        ]

    字段段额外字段：``enum``（多选一列表，非空即枚举）、
    ``missing``（占位符内是否声明"未明确/未提及"默认写法）。

    两类特殊段在拆分后标注：

    - ``kind="title"``：``# [栏目标题]`` 式标题占位（heading 行内的方括号），
      带 ``level``（# 层级）。填充 = 输出该标题行（只放标题文字），不是填正文
    - ``kind="table_rows"``：表格中整行 ``| … | … |`` 的占位数据行，
      带 ``row``（占位行原文）与 ``header``（所属表头行）。
      填充 = 删除占位行、按表头列序生成真实数据行
    """
    segments: list[dict] = []
    pos = 0
    for m in _PLACEHOLDER_RE.finditer(template):
        content = m.group(1)
        is_link = template[m.end() : m.end() + 1] == "("
        if not _looks_like_placeholder(content) or is_link:
            continue  # 非占位符括号（JSON/链接等）→ 保留在后续固定文字段中
        if m.start() > pos:
            segments.append({"kind": "text", "text": template[pos : m.start()]})
        segments.append(_parse_field(content))
        pos = m.end()
    if pos < len(template):
        segments.append({"kind": "text", "text": template[pos:]})
    return _mark_title_fields(_split_table_placeholder_rows(segments))


_TABLE_PLACEHOLDER_ROW_RE = re.compile(r"^\|(?:\s*[…\.]+\s*\|)+\s*$")
_TABLE_SEP_LINE_RE = re.compile(r"^\|[\s:\-|]+\|\s*$")
# 占位单元格：省略号 / 状态 emoji 示例 / 空格子——出现即为"待填数据行"
_TABLE_PLACEHOLDER_CELLS = {"…", "...", ".", "—", "-", "", "🟢正常", "🟡低风险", "🔴高风险", "无"}


def _is_placeholder_table_row(ln: str) -> bool:
    """整行都是占位单元格（如 ``| … | 🟢正常 | … |``）→ 待填数据行。"""
    if not ln.lstrip().startswith("|") or not ln.rstrip().endswith("|"):
        return False
    cells = [c.strip() for c in ln.strip().strip("|").split("|")]
    if len(cells) < 2:
        return False
    return all(c in _TABLE_PLACEHOLDER_CELLS for c in cells)


def _split_table_placeholder_rows(segments: list[dict]) -> list[dict]:
    """把固定文字段里的「整行 … 占位表格数据行」单独拆成 table_rows 段。

    这类行是模板留的待填数据行（不是固定文案）：
    拆出来后填充规则才能要求"删除占位行、按表头生成真实数据行"，
    门禁的固定文字完整性校验也不再强制要求占位行原样出现。
    """
    out: list[dict] = []
    for seg in segments:
        if seg.get("kind") != "text" or ("…" not in seg["text"] and "..." not in seg["text"]):
            out.append(seg)
            continue
        lines = seg["text"].split("\n")
        parts: list[dict] = []
        buf: list[str] = []
        header = ""
        prev_sep = False

        def _flush(buf: list[str], parts: list[dict]) -> None:
            if buf:
                parts.append({"kind": "text", "text": "\n".join(buf)})
                buf.clear()

        for ln in lines:
            if prev_sep and _is_placeholder_table_row(ln):
                _flush(buf, parts)
                parts.append({"kind": "table_rows", "row": ln, "header": header})
                prev_sep = False
                continue
            buf.append(ln)
            if _TABLE_SEP_LINE_RE.match(ln):
                header = buf[-2] if len(buf) >= 2 else header
                prev_sep = True
            else:
                prev_sep = False
        _flush(buf, parts)
        if len(parts) == 1 and parts[0].get("kind") == "text":
            out.append(seg)  # 没拆出占位行 → 保持原段
        else:
            out.extend(parts)
    return out


def _mark_title_fields(segments: list[dict]) -> list[dict]:
    """heading 行内的方括号占位（``# [栏目标题]``）标记为 title 段。

    判定：前一个固定段以 heading 前缀行结尾 + 字段文字较短无句读 +
    后一个固定段以换行开头（标题行内除占位无其他内容）。
    """
    for i, seg in enumerate(segments):
        if seg.get("kind") != "field":
            continue
        prev = segments[i - 1] if i > 0 else None
        nxt = segments[i + 1] if i + 1 < len(segments) else None
        if not prev or prev.get("kind") != "text":
            continue
        tail_lines = prev["text"].split("\n")
        last_line = tail_lines[-1] if tail_lines else ""
        m = re.match(r"^(#{1,6})\s*$", last_line)
        if not m:
            continue
        hint = str(seg.get("hint") or "").strip()
        if not hint or len(hint) > 30 or "。" in hint or "，" in hint:
            continue
        if nxt and nxt.get("kind") == "text" and not nxt["text"].startswith("\n"):
            continue
        seg["kind"] = "title"
        seg["level"] = len(m.group(1))
    return segments


def _parse_field(raw: str) -> dict:
    hint = raw.strip()
    missing = bool(_MISSING_HINT_RE.search(raw))
    enum: list[str] | None = None
    candidates = [p.strip() for p in _ENUM_SEP_RE.split(raw)]
    # 多选一判定：以 / 切出 ≥2 项且每项较短（emoji 枚举 / 短选项）
    if len(candidates) >= 2 and all(1 <= len(c) <= 12 for c in candidates):
        enum = candidates
    return {
        "kind": "field",
        "raw": raw,
        "hint": hint,
        "enum": enum,
        "missing": missing,
    }


def _table_row_limit_from_text(text: str) -> int | None:
    """从占位说明/自然语言片段中解析表格行数上限，如「三行左右」「约3条」。"""
    if not text:
        return None
    patterns = (
        r"(?:约|大约|左右|控制在|限制在|最多|不超过|不多于)?\s*([一二两三四五六七八九十\d]+)\s*(?:行|条|项)",
        r"(?:行数|条数)\s*(?:约|大约|为|控制在|限制在|最多|不超过|不多于)?\s*([一二两三四五六七八九十\d]+)",
    )
    for pattern in patterns:
        m = re.search(pattern, text)
        if not m:
            continue
        n = _parse_count_token(m.group(1))
        if n and n > 0:
            return n
    return None


def _row_limit_for_template(rt: dict[str, Any]) -> int | None:
    fields = rt.get("fields") or []
    text = "；".join(str(f.get("hint") or f.get("raw") or "") for f in fields)
    return _table_row_limit_from_text(text)


def strip_char_budget_meta(text: str) -> str:
    """从渲染正文中剔除字数元说明（如「约250字」「全文合计约200-300字」）。"""
    if not text:
        return text or ""
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        ended = line.endswith("\n")
        body = line[:-1] if ended else line
        if _CHAR_META_LINE_RE.match(body.strip()):
            continue
        cleaned = _CHAR_META_TAIL_RE.sub("", body).rstrip()
        if cleaned.strip() == "" and body.strip() != "":
            # 整行被剥成空 → 丢弃
            continue
        out.append(cleaned + ("\n" if ended else ""))
    # 去掉文末多余空行
    result = "".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.rstrip() + ("\n" if text.endswith("\n") else "")


def _build_placeholder_user(context: str, template: str, segments: list[dict]) -> str:
    lines = [
        "类型：占位符模板。保留固定文字与表结构，只替换 [占位]。",
        "有据才写；无依据「未提及」；禁止照抄「如：」示范；禁止编造原文没有的环节/数字/履历。",
        "谁做了什么、数值日期以原文为准；预计/可能不要写成已定事实。",
        "模板点名的栏目都要覆盖：从原文提炼与该栏主题相关的信息，勿因「无同名小标题」就空写。",
        "顿号或「与/和/及」连接的主题分别写清；流程只按原文真实顺序。",
        "语句完整通顺，无缺字、无半截句。",
        *_char_budget_lines(template),
        "模板结构解析：",
    ]
    field_no = 0
    for seg in segments:
        if seg["kind"] == "text":
            text = seg["text"]
            preview = text if len(text) <= 60 else text[:57] + "..."
            lines.append(f"- 固定文字（原样保留）：{preview!r}")
        elif seg["kind"] == "title":
            lines.append(
                f"- 栏目标题占位：输出标题行（{'#' * seg['level']} {seg['hint']}），"
                "标题行只放标题文字；本栏正文写在标题下方的正文占位处"
            )
        elif seg["kind"] == "table_rows":
            lines.append(
                f"- 表格占位数据行（原样照抄将判不合格）：{seg['row']!r}"
                f" —— 表头 {seg['header']!r}；输出时删除该占位行，"
                "按表头列序与本栏占位说明生成真实数据行（1..N 行，各占一行）"
            )
        else:
            field_no += 1
            lines.append(f"- {_describe_field(field_no, seg)}")
    return f"{context}\n\n模板原文：\n{template}\n\n【模板结构解析】\n" + "\n".join(lines)


def split_spec_template(template: str) -> tuple[str, str]:
    """把格式规范模板切成 (指令段, 示例段)。

    优先按示例标题切（``# 示例`` 等）；其次取最后一个代码块作为示例。
    切不出示例段时返回 ``(template, "")``。
    """
    for marker in _SPEC_SPLIT_MARKERS:
        idx = template.find(marker)
        if idx > 0:
            return template[:idx].strip(), template[idx:].strip()
    blocks = re.findall(r"```.*?```", template, flags=re.S)
    if blocks:
        example = blocks[-1]
        return template.replace(example, "").strip(), example.strip()
    return template, ""


def _build_spec_user(
    context: str,
    template: str,
    instruction: str,
    example: str,
) -> str:
    return (
        f"{context}\n\n"
        "本模板已判定为【类型二：格式规范模板】：示例仅演示格式，"
        "禁止照抄示例中的输入内容；严格按下方【格式指令】规定的字段结构与格式输出。\n\n"
        "【格式指令】\n"
        f"{instruction}\n\n"
        "【示例（仅演示格式）】\n"
        f"{example}"
    )


def route_template(
    context: str,
    template: str,
    render_prompt: str,
    template_prompt: str,
) -> tuple[str, str] | None:
    """自动判型分派，返回 ``(prompt, user)``；无法处理返回 ``None``。

    - 类型一 → 结构解析 + 精确填充指令；prompt 为基础规则 + PLACEHOLDER_RULES
      （LLM 只执行占位符填充规则，不再自行判型）
    - 类型二 → 指令/示例分离；prompt 为基础规则 + SPEC_RULES
      （LLM 只执行格式规范规则）
    - 类型三 → 编译由 bootstrap 侧 ``maybe_compile_natural_template`` 先行完成，
      此处一律回退旧路径（``None``），由调用方拼 FALLBACK_TEMPLATE_RULES
    - 开关关闭 / 解析异常 / 解析不到结构 → 回退旧路径（``None``），
      由调用方按旧行为处理（此时才需要 LLM 自行判断模板类型）
    """
    if not is_router_enabled():
        return None
    kind = detect_template_kind(template)
    try:
        if kind == "placeholder":
            segments = parse_placeholder_template(template)
            if not any(s["kind"] == "field" for s in segments):
                return None
            return template_prompt + PLACEHOLDER_RULES, _build_placeholder_user(
                context, template, segments
            )
        if kind == "spec":
            instruction, example = split_spec_template(template)
            if not example:
                return None
            return template_prompt + SPEC_RULES, _build_spec_user(
                context, template, instruction, example
            )
    except Exception:  # noqa: BLE001 - 路由失败一律回退旧路径，绝不影响现有逻辑
        logger.warning("模板路由处理异常，已回退旧路径", exc_info=True)
    return None


def extract_description_cues(description: str) -> dict[str, Any]:
    """从自然语言描述抽取意图线索（规则，不调 LLM）。"""
    text = description or ""
    cues: dict[str, Any] = {"flags": set(), "section_count": None}
    for name, pat in _CUE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        if name == "section_count":
            raw = next((g for g in m.groups() if g), None)
            cues["section_count"] = _parse_count_token(raw) if raw else None
        else:
            cues["flags"].add(name)
    # 「只要/仅要/不要」语气
    cues["minimal"] = bool(re.search(r"只要|仅要|只需|不要太多|简洁|简短", text))
    cues["no_extra"] = bool(re.search(r"不要|别加|无需|不用.*表|不要.*表", text))
    return cues


