"""LLM 重构：OCR 碎片 → 结构化 Markdown（标题层级 / **重点** / 表格 / 去噪）。

- 输入：OCR 行列表（text + 可选 formula）
- 输出：结构化 Markdown 文本
- LLM 不可用或失败：返回按行拼的原始文本（不阻塞）
"""
from __future__ import annotations

import json
import logging
import re

from .mathmd import normalize_markdown_math

logger = logging.getLogger(__name__)

RECONSTRUCT_SYSTEM_PROMPT = """你是「笔记整理器」。把 OCR 识别出的笔记碎片整理成一份结构化 Markdown，供知识库检索。

要求：
1. **保留全部内容**：不要漏掉任何识别到的文字、数字、公式；OCR 明显错字可顺手纠正，但不要臆造
2. **双轨标题规则**：输入中 title_decision=locked_heading 的行是高置信标题，必须输出为 Markdown 标题；只能轻微修 OCR 错字，不要降为正文。title_decision=locked_body 的行默认保持正文/公式，不要升标题。title_decision=ambiguous 的行才结合上下文判断是否为标题
3. **推断结构**：对 locked_heading 和 ambiguous 标题，结合 heading_level_hint / heading_score / 上下文，推断章节/知识点层级（# 标题、## 小节、### 知识点）
4. **标题不带编号前缀**：OCR 行里的编号（如「一、」「3、」「（1）」「第X章」「1.2」）只是序号，输出标题时一律去掉，层级用 # 的数量表达，同类编号保持同一层级；正文和列表里的序号原样保留，不要动
5. **正文不要误升标题**：locked_body、长句、以句号/逗号结尾的解释性内容，即使包含关键词，也不要强行改成标题
6. **重点标注**：对像"重点/必考/关键/注意/易错"的内容用 **加粗** 标出（不要过度标注）
7. **公式定界**：行内公式只用一对 ``$...$``；独立成行的公式才用 ``$$...$$``。禁止 ``$...$$`` / ``$$...$`` 混用，公式内部不要再写美元符号。已有 ``$$...$$`` 的公式原样保留位置，但定界必须成对
8. **表格**：如果内容是成列的数据（行结构明显），整理成 Markdown 表格
9. 去除 OCR 噪声（孤立标点、乱码），合并被断行的完整句子
10. **低置信行**：conf < 0.8 的行 OCR 可信度低，结合上下文谨慎纠错；不确定就原样保留，禁止臆造
11. 直接输出 Markdown 正文，不要前言后语、不要 Markdown 代码围栏"""

REVIEW_SYSTEM_PROMPT = """你是「OCR Markdown 保守审校器」。你会拿到少量可疑 OCR 原文窗口，以及与之相关的带行号 Markdown 行。

任务：只指出需要改的行，不要重写全文，不要输出 Markdown 正文。

允许修正：
1. 明显 OCR 误识别：如 sin/sln、lim/1im、上下标/符号孤立错字、重复乱码、断行造成的错拼
2. Markdown 结构问题：标题层级明显错乱、列表/表格破损、重复标题、代码围栏误包裹
3. 公式排版问题：明显被拆断的公式可合并；把 $...$$ / $$...$ / $$$ 改成合法的 $...$ 或 $$...$$；不确定的公式保持原样
4. 断句与空白：合并不该断开的句子，移除孤立噪声字符
5. 页眉页脚/机构信息剔除：页码、页眉页脚、机构地址、电话、传真、邮箱、网址、邮编、版权行等与正文无关的行，用补丁整行删除

禁止：
1. 不要根据常识重写定义、定理、公式或结论
2. 不要补充稿中没有的知识
3. 不要把不确定内容改成你认为正确的内容
4. 不要删除稿中能辨认出的有效信息
5. 不要做全文短词替换；每条补丁必须对准指定行
6. 不要把 L00N: 行号写进 from / to
7. 没有 OCR 原文窗口支持的修改不要输出补丁

只输出一个 JSON 对象。第一个字符是 {，最后一个字符是 }。
不要 Markdown 围栏、不要解释、不要输出整理稿正文。
from/to 里的换行必须写成 \\n，不要直接换行。

合法示例：
{"patches":[{"line":42,"from":"其中 sln x","to":"其中 sin x"}]}
无需修改：
{"patches":[]}

字段：
- line：稿子里 L00N 的编号数字，从 1 起
- end：可选，跨行合并时的最后一行（含）；单行不要写
- from：该行原文，不要带 L00N: 前缀
- to：替换后的文本

最多 30 条补丁。"""

_LINE_PREFIX_RE = re.compile(r"^L\d+:\s*")
_REVIEW_MAX_PATCHES = 30

# ── 标题归一化：剥编号前缀 + 同类编号归同一层级（确定性后处理，零 token）──

_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

# 单个编号前缀（按序尝试，可叠两层，如「第一章 三、」）
_NUM_PREFIX_RES = [
    re.compile(r"^第[0-9一二三四五六七八九十百]+[章节篇讲][、.．]?\s*"),
    re.compile(r"^[（(][0-9一二三四五六七八九十百]+[)）]\s*"),
    re.compile(r"^[0-9]+(?:\.[0-9]+)+\s+"),  # 多级编号 1.2 / 2.3.4（后随空白）
    re.compile(r"^[0-9]+[、.．]\s*"),
    re.compile(r"^[一二三四五六七八九十百]+[、.．]\s*"),
]

# 编号家族：同类编号归同一层级
_FAMILY_RES = [
    ("zh", re.compile(r"^[一二三四五六七八九十百]+[、.．]")),
    ("paren_zh", re.compile(r"^[（(][一二三四五六七八九十百]+[)）]")),
    ("paren_num", re.compile(r"^[（(][0-9]+[)）]")),
    ("multi", re.compile(r"^[0-9]+(?:\.[0-9]+)+")),
    ("arabic", re.compile(r"^[0-9]+[、.．]")),
    ("di", re.compile(r"^第[0-9一二三四五六七八九十百]+[章节篇讲]")),
]


def _strip_numbering_prefix(text: str) -> str:
    """剥标题开头的编号前缀（最多两层）；剥完为空则保留原文。"""
    out = text.strip()
    for _ in range(2):
        for pattern in _NUM_PREFIX_RES:
            matched = pattern.match(out)
            if matched:
                out = out[matched.end():].lstrip()
                break
        else:
            break
    return out.strip() or text


def _numbering_family(text: str) -> str | None:
    for name, pattern in _FAMILY_RES:
        matched = pattern.match(text)
        if matched:
            if name == "multi":
                # 多级编号按段数分家族：1.2（两段）与 2.3.4（三段）层级不同，不互归
                depth = len(re.findall(r"[0-9]+", matched.group(0)))
                return f"multi{depth}"
            return name
    return None


def normalize_heading_numbering(markdown: str) -> str:
    """确定性归一化 Markdown 标题：

    1. 剥离标题行的编号前缀（一、 / 3、 / （1） / 第X章 / 1.2 等），
       编号只是序号，不进标题文本；有序列表/正文不受影响（只处理 # 行）。
    2. 同类编号归同一层级：同家族标题（如 一、二、…）横跨 H1/H2 时，
       取多数层级校正，消除 LLM 输出的层级漂移。

    幂等：重复执行结果不变。代码围栏内的行不处理。
    """
    rows = (markdown or "").splitlines()
    headings: list[tuple[int, int, str]] = []  # (行号, 级别, 编号家族)
    in_fence = False
    for idx, row in enumerate(rows):
        if _FENCE_RE.match(row):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        matched = _HEADING_LINE_RE.match(row)
        if not matched:
            continue
        level, title = len(matched.group(1)), matched.group(2).strip()
        family = _numbering_family(title)
        stripped = _strip_numbering_prefix(title)
        rows[idx] = f"{'#' * level} {stripped}"
        if family is not None:
            headings.append((idx, level, family))

    # 同家族取多数层级（平票取文档中首个该家族标题的层级）
    families: dict[str, list[tuple[int, int]]] = {}
    for idx, level, family in headings:
        families.setdefault(family, []).append((idx, level))
    for members in families.values():
        if len(members) < 2:
            continue
        counts: dict[int, int] = {}
        for _idx, level in members:
            counts[level] = counts.get(level, 0) + 1
        # max 平票时返回按文档顺序先插入的层级
        target = max(counts.items(), key=lambda kv: kv[1])[0]
        if all(level == target for _idx, level in members):
            continue
        for idx, _level in members:
            matched = _HEADING_LINE_RE.match(rows[idx])
            if matched:
                rows[idx] = f"{'#' * target} {matched.group(2).strip()}"
    return "\n".join(rows)


def _fragments_to_text(lines: list[dict]) -> str:
    """行列表 → 拼接文本；无 LLM 时也尽量保留标题层级。页眉页脚行剔除。"""
    parts: list[str] = []
    for item in lines:
        formula = item.get("formula")
        text = item.get("text") or ""
        role = item.get("role_hint")
        decision = item.get("title_decision")
        level = int(item.get("heading_level_hint") or 0)
        if role == "boilerplate":
            continue  # 页眉页脚/地址电话/版权行不进拼接
        if formula:
            parts.append(formula)
        elif text and (decision == "locked_heading" or role == "heading"):
            marks = "#" * min(max(level or 2, 1), 6)
            parts.append(f"{marks} {text}")
        elif text:
            parts.append(text)
    return "\n".join(parts)


def _lines_to_structured_payload(lines: list[dict]) -> str:
    """压缩版 OCR 行 JSON。locked_body 正文行只发 text/conf，版面明细只随标题候选行发送，
    大幅压缩输入 token。页眉页脚/机构信息行（role_hint=boilerplate）直接剔除。"""
    payload = []
    for idx, item in enumerate(lines, start=1):
        formula = str(item.get("formula") or "").strip()
        text = str(item.get("text") or "").strip()
        if not text and not formula:
            continue
        if str(item.get("role_hint") or "") == "boilerplate":
            continue  # 页眉页脚/地址电话/版权行不进 LLM 输入
        decision = item.get("title_decision") or "ambiguous"
        conf = item.get("conf")
        row: dict = {
            "i": idx,
            "text": text,
            "title_decision": decision,
        }
        if formula:
            row["formula"] = formula
        if conf is not None and float(conf) < 0.8:
            row["conf"] = round(float(conf), 3)  # 只标低置信行，供 LLM 谨慎纠错
        if decision != "locked_body":
            layout = item.get("layout") or {}
            row["role_hint"] = item.get("role_hint") or "body"
            row["heading_score"] = item.get("heading_score") or 0
            if item.get("heading_level_hint"):
                row["heading_level_hint"] = item.get("heading_level_hint")
            row["layout"] = {
                "top": layout.get("top"),
                "height_ratio": layout.get("height_ratio"),
                "gap_before": layout.get("gap_before"),
                "gap_after": layout.get("gap_after"),
                "centered": layout.get("centered"),
                "near_left": layout.get("near_left"),
            }
        payload.append(row)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def reconstruct_markdown(lines: list[dict], *, max_tokens: int = 5000) -> str:
    """LLM 重构；失败/无 LLM 时返回原始拼接文本。"""
    raw = _fragments_to_text(lines)
    if not raw.strip():
        return "（OCR 未识别到文字）"
    client = None
    try:
        from .engines import get_llm_client

        client = get_llm_client()
    except Exception:  # noqa: BLE001
        client = None
    if client is None:
        return normalize_heading_numbering(normalize_markdown_math(raw))
    try:
        import asyncio

        text = asyncio.run(
            client.text(
                RECONSTRUCT_SYSTEM_PROMPT,
                "OCR 行列表 JSON（按阅读顺序排列，含版面标题提示）：\n"
                f"{_lines_to_structured_payload(lines)}\n\n"
                "请输出整理后的 Markdown 正文。",
                temperature=0.1,
                max_tokens=max_tokens,
                label="ocr/reconstruct",
            )
        )
        return normalize_heading_numbering(normalize_markdown_math(str(text).strip()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 重构失败，返回原始文本：%s", exc)
        return normalize_heading_numbering(normalize_markdown_math(raw))


def deterministic_reconstruct_markdown(lines: list[dict]) -> str:
    """Program-only OCR reconstruction for high-confidence plain text batches."""
    raw = _fragments_to_text(lines)
    if not raw.strip():
        return "（OCR 未识别到文字）"
    return normalize_heading_numbering(normalize_markdown_math(raw))


def review_markdown(
    markdown: str,
    lines: list[dict],
) -> tuple[str, str]:
    """LLM 只出补丁；程序按行号+原文核对后本地改稿。失败时返回原稿。"""
    draft = str(markdown or "").strip()
    if not draft:
        return draft, "未生成可审校的 Markdown。"
    draft = normalize_heading_numbering(normalize_markdown_math(draft))
    evidence = _suspect_ocr_windows(lines)
    selected = _select_review_draft_lines(draft, evidence)
    if not evidence or not selected:
        return draft, "未发现可定位的局部审校窗口。"
    review_max_tokens = max(800, min(3000, len(evidence) * 120))
    client = None
    try:
        from .engines import get_llm_client

        client = get_llm_client()
    except Exception:  # noqa: BLE001
        client = None
    if client is None:
        return draft, "LLM 客户端不可用，未执行审校。"
    try:
        import asyncio

        text = asyncio.run(
            client.text(
                REVIEW_SYSTEM_PROMPT,
                "可疑 OCR 原文窗口（只能依据这些证据修正）：\n"
                f"{json.dumps(evidence, ensure_ascii=False, separators=(',', ':'))}\n\n"
                "相关 Markdown 行（L00N 是全文行号，不要写进 from/to）：\n"
                f"{_number_selected_draft_lines(draft, selected)}\n",
                temperature=0.0,
                max_tokens=review_max_tokens,
                json_mode=True,
                label="ocr/review",
            )
        )
        return _as_reviewed_markdown(str(text), draft)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 审校失败，返回重构稿：%s", exc)
        return draft, f"LLM 审校失败，已保留重构稿：{exc}"


def _number_draft_lines(draft: str) -> str:
    rows = draft.splitlines()
    width = max(3, len(str(max(len(rows), 1))))
    return "\n".join(f"L{idx:0{width}d}: {row}" for idx, row in enumerate(rows, start=1))


def _number_selected_draft_lines(draft: str, line_numbers: list[int]) -> str:
    rows = draft.splitlines()
    if not rows:
        return ""
    width = max(3, len(str(len(rows))))
    output: list[str] = []
    last = 0
    for line_no in sorted(set(line_numbers)):
        if line_no < 1 or line_no > len(rows):
            continue
        if last and line_no > last + 1:
            output.append("...")
        output.append(f"L{line_no:0{width}d}: {rows[line_no - 1]}")
        last = line_no
    return "\n".join(output)


def _plain_for_match(text: str) -> str:
    cleaned = re.sub(r"^[#>\-\s*\d.、()（）]+", "", text or "")
    cleaned = re.sub(r"[*_`$\\\s]+", "", cleaned)
    return cleaned.strip()


def _line_conf(item: dict) -> float | None:
    if item.get("conf") is None:
        return None
    try:
        return float(item.get("conf"))
    except (TypeError, ValueError):
        return None


def _is_formula_like(item: dict) -> bool:
    text = str(item.get("formula") or item.get("text") or "")
    return bool(item.get("formula")) or str(item.get("role_hint") or "") == "formula" or bool(
        re.search(r"[=＋×÷−√∫∑≥≤≠≈∞]|\\frac|\\sum|\\int|\\lim|\\sqrt", text)
    )


def _formula_suspicious(text: str, conf: float | None) -> bool:
    if conf is not None and conf < 0.78:
        return True
    pairs = (("(", ")"), ("（", "）"), ("[", "]"), ("{", "}"))
    return any(text.count(left) != text.count(right) for left, right in pairs)


def _is_suspect_ocr_line(item: dict) -> bool:
    text = str(item.get("formula") or item.get("text") or "").strip()
    if not text:
        return False
    conf = _line_conf(item)
    role = str(item.get("role_hint") or "")
    decision = str(item.get("title_decision") or "")
    if conf is not None and conf < (0.80 if role == "heading" or decision == "ambiguous" else 0.75):
        return True
    if _is_formula_like(item) and _formula_suspicious(text, conf):
        return True
    if decision == "ambiguous" and len(_plain_for_match(text)) <= 24 and re.search(r"[章节定义定理性质例题重点难点]", text):
        return True
    return False


def _compact_ocr_line(item: dict) -> dict:
    text = str(item.get("formula") or item.get("text") or "").strip()
    row: dict = {"text": text}
    conf = _line_conf(item)
    if conf is not None:
        row["conf"] = round(conf, 3)
    role = str(item.get("role_hint") or "")
    decision = str(item.get("title_decision") or "")
    if role:
        row["role"] = role
    if decision:
        row["title"] = decision
    return row


def _suspect_ocr_windows(lines: list[dict]) -> list[dict]:
    """Build tiny source-evidence windows instead of sending all OCR lines to review."""
    evidence: list[dict] = []
    clean_lines = [item for item in lines if str(item.get("role_hint") or "") != "boilerplate"]
    for idx, item in enumerate(clean_lines):
        if not _is_suspect_ocr_line(item):
            continue
        lo = max(0, idx - 1)
        hi = min(len(clean_lines), idx + 2)
        evidence.append(
            {
                "ocr_line": idx + 1,
                "prev": [_compact_ocr_line(line) for line in clean_lines[lo:idx]],
                "target": _compact_ocr_line(item),
                "next": [_compact_ocr_line(line) for line in clean_lines[idx + 1:hi]],
            }
        )
        if len(evidence) >= 16:
            break
    return evidence


def _select_review_draft_lines(draft: str, evidence: list[dict]) -> list[int]:
    rows = draft.splitlines()
    selected: set[int] = set()
    for window in evidence:
        target = _plain_for_match(str((window.get("target") or {}).get("text") or ""))
        if len(target) < 2:
            continue
        for idx, row in enumerate(rows, start=1):
            plain = _plain_for_match(row)
            if plain and (target in plain or plain in target):
                selected.add(idx)
                for line_no in _nearest_nonblank_lines(rows, idx, limit=1, direction=-1):
                    selected.add(line_no)
                for line_no in _nearest_nonblank_lines(rows, idx, limit=1, direction=1):
                    selected.add(line_no)
                break
    return sorted(selected)


def _nearest_nonblank_lines(rows: list[str], start: int, *, limit: int, direction: int) -> list[int]:
    found: list[int] = []
    idx = start + direction
    while 1 <= idx <= len(rows) and len(found) < limit:
        if _plain_for_match(rows[idx - 1]):
            found.append(idx)
        idx += direction
    return found


def _strip_line_prefixes(text: str) -> str:
    return "\n".join(_LINE_PREFIX_RE.sub("", row) for row in (text or "").splitlines())


def _strip_md_fences(text: str) -> str:
    raw = (text or "").strip()
    if not raw.startswith("```"):
        return raw
    raw = re.sub(r"^```(?:markdown|md|json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _escape_raw_newlines_in_strings(text: str) -> str:
    """把 JSON 字符串里的真实换行收成 \\n，避免 from/to 抄原文时把 JSON 写坏。"""
    out: list[str] = []
    in_str = False
    escaped = False
    for char in text:
        if in_str:
            if escaped:
                out.append(char)
                escaped = False
                continue
            if char == "\\":
                out.append(char)
                escaped = True
                continue
            if char == '"':
                in_str = False
                out.append(char)
                continue
            if char == "\n":
                out.append("\\n")
                continue
            if char == "\r":
                continue
            if char == "\t":
                out.append("\\t")
                continue
            out.append(char)
            continue
        if char == '"':
            in_str = True
        out.append(char)
    return "".join(out)


def _repair_review_json(raw: str) -> str:
    text = _strip_md_fences(raw)
    start_obj, start_arr = text.find("{"), text.find("[")
    starts = [pos for pos in (start_obj, start_arr) if pos >= 0]
    if starts:
        start = min(starts)
        end_token = "}" if text[start] == "{" else "]"
        end = text.rfind(end_token)
        if end > start:
            text = text[start : end + 1]
    text = (
        text.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
    )
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)
    text = re.sub(r"\bNone\b", "null", text)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    text = re.sub(r"(\{|,)\s*(patches|edits|line|end|from|to|original|old|text|new)\s*:", r'\1"\2":', text)
    return _escape_raw_newlines_in_strings(text)


def _salvage_patches(raw: str) -> dict | None:
    """截断 JSON 时尽量收下已经完整的补丁对象。"""
    key = raw.find('"patches"')
    if key < 0:
        key = raw.find("[")
        if key < 0:
            return None
        bracket = key
    else:
        bracket = raw.find("[", key)
    if bracket < 0:
        if '"patches"' in raw:
            return {"patches": []}
        return None
    decoder = json.JSONDecoder()
    items: list[dict] = []
    idx = bracket + 1
    length = len(raw)
    while idx < length:
        while idx < length and raw[idx] in " \t\r\n,":
            idx += 1
        if idx >= length or raw[idx] == "]":
            break
        if raw[idx] != "{":
            break
        try:
            obj, end = decoder.raw_decode(raw, idx)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            items.append(obj)
        idx = end
    if items:
        return {"patches": items}
    rest = raw[bracket:]
    if re.match(r"\[\s*\]", rest):
        return {"patches": []}
    return None


def _json_from_review(text: str):
    raw = (text or "").strip()
    if not raw:
        return None
    candidates = [raw, _strip_md_fences(raw), _repair_review_json(raw)]
    seen: set[str] = set()
    for candidate in candidates:
        blob = (candidate or "").strip()
        if not blob or blob in seen:
            continue
        seen.add(blob)
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            salvaged = _salvage_patches(blob)
            if salvaged is not None:
                return salvaged
    logger.warning("审校 JSON 无法解析，head=%s", raw[:240].replace("\n", "\\n"))
    return None


def _patch_items(payload) -> list[dict]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("patches")
        if items is None:
            items = payload.get("edits") or []
    else:
        return []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def apply_review_patches(draft: str, patches: list[dict]) -> tuple[str, str]:
    """按行号+原文核对后打补丁；对不上的跳过。从后往前改，避免行号错位。"""
    rows = draft.splitlines()
    accepted: list[tuple[int, int, list[str], str]] = []
    notes: list[str] = []
    occupied: list[tuple[int, int]] = []

    for item in patches[:_REVIEW_MAX_PATCHES]:
        try:
            raw_line = item.get("line") if item.get("line") is not None else item.get("start")
            if isinstance(raw_line, str):
                matched = re.search(r"(\d+)", raw_line)
                start = int(matched.group(1)) if matched else 0
            else:
                start = int(raw_line or 0)
        except (TypeError, ValueError):
            notes.append("- 补丁行号无效，已跳过")
            continue
        end_raw = item.get("end") if item.get("end") is not None else item.get("line_end")
        try:
            end = int(end_raw) if end_raw is not None else start
        except (TypeError, ValueError):
            notes.append(f"- L{start} 结束行号无效，已跳过")
            continue
        if start < 1 or end < start or end > len(rows):
            notes.append(f"- L{start} 行号超出稿件，已跳过")
            continue
        src_raw = item.get("from") if item.get("from") is not None else item.get("original") or item.get("old") or ""
        if isinstance(src_raw, list):
            src_raw = "\n".join(str(part) for part in src_raw)
        src = _strip_line_prefixes(str(src_raw))
        if "to" in item:
            dst_raw = item.get("to")
        elif "text" in item:
            dst_raw = item.get("text")
        else:
            dst_raw = item.get("new")
        if dst_raw is None:
            notes.append(f"- L{start} 缺少 to，已跳过")
            continue
        if isinstance(dst_raw, list):
            dst_raw = "\n".join(str(part) for part in dst_raw)
        dst = _strip_line_prefixes(str(dst_raw))
        lo, hi = start - 1, end
        current = "\n".join(rows[lo:hi])
        new_rows: list[str] | None = None
        if src == current or src.strip() == current.strip():
            new_rows = dst.splitlines()
        elif start == end and src and current.count(src) == 1:
            new_rows = [current.replace(src, dst, 1)]
        else:
            notes.append(f"- L{start} 原文不匹配，已跳过")
            continue
        if any(not (hi <= a or lo >= b) for a, b in occupied):
            notes.append(f"- L{start} 与其他补丁重叠，已跳过")
            continue
        occupied.append((lo, hi))
        label = f"L{start}" if start == end else f"L{start}-{end}"
        accepted.append((lo, hi, new_rows, f"- {label} 已替换"))

    accepted.sort(key=lambda item: item[0], reverse=True)
    for lo, hi, new_rows, note in accepted:
        rows[lo:hi] = new_rows
        notes.append(note)
    if not accepted:
        return draft, "\n".join(notes) if notes else "未发现需要审校修正的问题。"
    reviewed = "\n".join(rows)
    if draft.endswith("\n"):
        reviewed += "\n"
    return normalize_markdown_math(reviewed), "\n".join(notes)


def _as_reviewed_markdown(text: str, draft: str) -> tuple[str, str]:
    """审校模型输出 → 补丁 JSON → 本地改稿。不是补丁则保留重构稿。"""
    payload = _json_from_review(text)
    if payload is None:
        if not str(text or "").strip():
            return draft, "审校结果为空，已保留重构稿。"
        logger.warning("审校未返回可解析补丁，已保留重构稿")
        return draft, "审校未返回补丁，已保留重构稿。"
    patches = _patch_items(payload)
    reviewed, notes = apply_review_patches(draft, patches)
    return normalize_heading_numbering(reviewed), notes


__all__ = [
    "RECONSTRUCT_SYSTEM_PROMPT",
    "REVIEW_SYSTEM_PROMPT",
    "apply_review_patches",
    "normalize_heading_numbering",
    "reconstruct_markdown",
    "review_markdown",
]
