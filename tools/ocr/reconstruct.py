"""LLM 重构：OCR 碎片 → 结构化 Markdown（标题层级 / **重点** / 表格 / 去噪）。

- 输入：OCR 行列表（text + 可选 formula）
- 输出：结构化 Markdown 文本
- LLM 不可用或失败：返回按行拼的原始文本（不阻塞）
"""
from __future__ import annotations

import json
import logging
import os
import re

from .mathmd import normalize_markdown_math

logger = logging.getLogger(__name__)

RECONSTRUCT_SYSTEM_PROMPT = """你是「笔记整理器」。把 OCR 识别出的笔记碎片整理成结构化 Markdown，供知识库检索。

铁律：不漏任何识别到的文字/数字/公式，明显错字可顺手纠正但不臆造；去除噪声（孤立标点/乱码），合并被断行的完整句子。

标题（双轨）：
- title_decision=locked_heading 的行必须输出为标题，只许轻微修错字，不许降为正文；locked_body 与长句/句读结尾的解释行不许升标题（即使含关键词）；ambiguous 的行才结合上下文判断
- 结合 heading_level_hint 与上下文推断层级（# 章、## 节、### 知识点）；标题剥掉编号前缀（「一、」「3、」「第X章」「1.2」只是序号，层级用 # 数量表达，同类编号同层级）；正文与列表里的序号原样保留

格式：
- 「重点/必考/注意/易错」类内容用 **加粗** 标出（克制）；成列的数据整理为 Markdown 表格
- 公式：行内用一对 $...$，独立成行才用 $$...$$；禁止 $...$$ / $$...$ 混用，公式内不写美元符号，已有 $$...$$ 位置原样保留但定界必须成对
- conf < 0.8 的行可信度低，结合上下文谨慎纠错，不确定就原样保留

直接输出 Markdown 正文：不要前言后语、不要代码围栏。"""

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


def _payload_compact() -> bool:
    """payload 字段瘦身开关（默认开；OCR_PAYLOAD_COMPACT=0 回退全字段集，A/B 用）。

    规则只消费 title_decision / heading_level_hint / conf；role_hint 与
    heading_score 不被引用，layout 几何明细只对标题候选行（role_hint=heading
    或 title_decision=ambiguous）有判断价值——locked_body 行发全字段是纯浪费。
    """
    return os.getenv("OCR_PAYLOAD_COMPACT", "1").strip().lower() in {"1", "true", "yes", "on"}


def _lines_to_structured_payload(lines: list[dict]) -> str:
    """压缩版 OCR 行 JSON。locked_body 正文行只发 text/conf；版面明细只随
    标题候选行发送（compact 模式），页眉页脚/机构信息行（boilerplate）剔除。"""
    compact = _payload_compact()
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
            level_hint = item.get("heading_level_hint")
            if compact:
                # 瘦身：只保留规则消费的字段；几何明细仅在需要判层级的行上发送
                if item.get("role_hint") == "heading" or decision == "ambiguous":
                    row["layout"] = {
                        "top": layout.get("top"),
                        "height_ratio": layout.get("height_ratio"),
                        "gap_before": layout.get("gap_before"),
                        "gap_after": layout.get("gap_after"),
                        "centered": layout.get("centered"),
                        "near_left": layout.get("near_left"),
                    }
                if level_hint:
                    row["heading_level_hint"] = level_hint
            else:
                row["role_hint"] = item.get("role_hint") or "body"
                row["heading_score"] = item.get("heading_score") or 0
                if level_hint:
                    row["heading_level_hint"] = level_hint
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


def reconstruct_markdown(lines: list[dict], *, max_tokens: int = 5000, context: str = "") -> str:
    """LLM 重构；失败/无 LLM 时返回原始拼接文本。

    context：可选的跨页上下文（上一页末尾标题/小节），提示模型保持跨页标题层级
    连续；为空时行为与原来完全一致。
    """
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
    user_prompt = "OCR 行列表 JSON（按阅读顺序排列，含版面标题提示）：\n" f"{_lines_to_structured_payload(lines)}\n\n请输出整理后的 Markdown 正文。"
    if context:
        user_prompt = (
            "【跨页上下文】上一页末尾的标题/小节：\n" + context.strip()[:120]
            + "\n本页开头可能是它的延续：请保持标题层级连续；"
            "只有本页内容确为新的章节时才另起同级标题。\n\n" + user_prompt
        )
    try:
        import asyncio

        text = asyncio.run(
            client.text(
                RECONSTRUCT_SYSTEM_PROMPT,
                user_prompt,
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


# ════════════════════ 完整性自检 + 截断/漏行闭环补写 ════════════════════
# Step 1 收敛版（P0~P4）。触发语义 = 显式缺失，不做覆盖率模糊调参：
#   · 行的"存在"判定：与 md 共享任一 8 连字符即视为存在（正文被改写/断行合并
#     仍保留长串；整行丢失则没有任何 8 连字符落进稿子）。该判据对"同章常用字
#     重叠"不敏感，无语料调参。
#   · "缺失"只认三类：正文行不存在的近整行丢失；词元级可判且高置信缺失的
#     公式行（OCR_FORMULA_MISS_CHECK=0 关闭公式判据）；稿尾截断
#     （缺失延伸到批次最后一行，或稿尾结构残片信号 _tail_looks_cut）。
#   · 公式行不再无条件豁免"缺失"：LaTeX 化/纠错是"内容词元守恒"改写，
#     正常重写不误报；仅"字形可判（无汉字段/括号配对/≥2 个内容词元）且内容
#     词元一个都不在稿中"的整行丢失才触发补写。OCR 字形含混/含汉字段的
#     公式行保持豁免（LLM 有权纠错重写，塞回原文是噪声再注入）。
#   · 编号短标题行不参与缺失判定（剥号是既定转换，质量由 review/结构后处理
#     负责）——避免把重写噪声当缺失触发补写。
# 开销纪律：
#   · 无缺失 → 零 LLM 调用；补写调用独立 label（ocr/reconstruct/fix）便于成本归因；
#   · 每批调用数 ≤ OCR_CONTINUE_MAX_CALLS（默认 2）；超预算缺失段一律原文兜底，内容不丢；
#   · 片段自身 $ 定界不平衡 → 判定失败，回退原文追加，不留半截公式残片。
# 噪声纪律（1→2→3 修正）：LLM 在整理规则下有权删除 OCR 噪声（乱码/页码/页眉页脚
#   残留/纯数字符号串）。恢复机制不得把它已删的噪声再塞回稿子：
#   1) 行必须先过"可恢复资格"过滤（与管线噪声口径一致：页码/机构信息/纯数字符号残渣/
#      乱码指纹）才允许被判"缺失"；2) 恢复两侧（补写片段与原文兜底）同用该过滤；
#   3) 缺失段先按小间隔合并，减少零散段与兜底。
# 开关 OCR_COMPLETENESS_FIX=0 关闭（A/B 用）。
_CONTINUE_MAX_CALLS = 2        # 每批最多补写调用次数（OCR_CONTINUE_MAX_CALLS 可覆盖）
_CONTINUE_MAX_TOKENS = 3000    # 单次补写输出上限（OCR_CONTINUE_MAX_TOKENS 可覆盖）
_NGRAM_WINDOW = 8              # 行"存在"判定窗口：与 md 共享任一 8 连字符即视为存在
_ABSENT_MIN_CHARS = 24         # 缺失段总字符量低于此且无 ≥10 字单行 → 视为噪声不触发
_ABSENT_SINGLE_MIN_LEN = 10
_TAIL_ROWS_CAP = 40            # 续尾最多携带的原始行数（含公式行）
_TAIL_SEGMENT_MAX = 1200       # 稿尾结构信号扫描的尾部窗口
_TAIL_MODE_GARBAGE_MAX = 900   # 续尾前最多可裁掉的尾部残片长度
_MID_COALESCE_GAP = 2          # 缺失段之间间隔 ≤2 个存在行 → 合并为一段补写
_FIX_LABEL = "ocr/reconstruct/fix"

# ── 可恢复资格过滤（与管线噪声口径一致，通用类别，无语料调参）──
_PAGEISH_RE = re.compile(
    r"^(?:第\s*[0-9一二三四五六七八九十百]+\s*页|page\s*\d+|p\.?\s*\d+|no\.?\s*\d*)$",
    re.I,
)
_CHROME_RE = re.compile(
    r"tel[:：]?\s*[+\d]|电话[:：]|传真[:：]|@[\w-]+\.[\w.]+|https?://|www\.\w"
    r"|©|版权所有|copyright|all\s+rights\s+reserved",
    re.I,
)
_DIGIT_PUNCT_RE = re.compile(
    r"^[\d\s\-–—:：.．,，;；/\\|()（）\[\]{}<>+=*^$%&@#~`'\"_]+$"
)
_ASCII_PUNCT_OK = set(" .,;:!?'\"()-–—/&%")

_ROW_NOISE_RE = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]")
_NUM_HEAD_ISH_RE = re.compile(
    r"^(?:第[0-9一二三四五六七八九十百]+[章节篇讲课单元]"
    r"|[（(]?[0-9一二三四五六七八九十百]+[)）]"
    r"|[0-9一二三四五六七八九十百]+[、.．])"
)

_CONTINUE_TAIL_INSTRUCT = (
    "这组 OCR 行属于稿件末尾，上一轮整理被截断了。把它们整理成 Markdown 续在稿尾：\n"
    "1. 若断点处的句子/公式/表格被切断或残留乱码，先忽略残片、按断点后的原文行重新补完整\n"
    "2. 不要重复稿尾已有内容，不要重写全文，不要输出 Markdown 围栏\n"
    "3. 公式用 $/$$ 定界、标题用 #，风格与主稿一致；不确定的 OCR 原样保留，禁止臆造\n"
    "4. 输出必须以完整句子或闭合公式结束，禁止以半截句子/公式/列表项收尾\n"
    "5. 缺失行清单里若混有明显 OCR 噪声/乱码/页码页眉残留，不要输出它们"
)
_CONTINUE_MID_INSTRUCT = (
    "这组 OCR 行在稿件中被遗漏了。把它们整理成 Markdown 片段补回原稿合适位置：\n"
    "1. 片段可用标题/段落/公式/列表，风格与主稿一致\n"
    "2. 不要重复已有内容，不要重写全文，不要输出 Markdown 围栏\n"
    "3. 不确定的 OCR 原样保留，禁止臆造\n"
    "4. 输出必须以完整句子或闭合公式结束，禁止以半截句子/公式/列表项收尾\n"
    "5. 缺失行清单里若混有明显 OCR 噪声/乱码/页码页眉残留，不要输出它们"
)


def _check_compact(text: str) -> str:
    """行侧紧凑化：只去空白（md 侧另有排版符剥离）。"""
    return "".join((text or "").split())


def _md_compact(markdown: str) -> str:
    """md 侧紧凑文本：剥空白与排版符（#*/`|>~_$）。$ 是公式包裹符、非内容。"""
    return re.sub(r"[#*`|>~_$\s]", "", markdown or "")


def _row_ngrams_present(line: str, md_compact_blob: str, md_grams: set[str]) -> bool:
    """行是否"存在于"稿中：≥8 字行看是否与 md 共享任一 8 连字符；
    短行要求整行作为子串出现。"""
    if not line:
        return False
    if len(line) < _NGRAM_WINDOW:
        return line in md_compact_blob
    for i in range(len(line) - _NGRAM_WINDOW + 1):
        if line[i:i + _NGRAM_WINDOW] in md_grams:
            return True
    return False


# ── 公式行缺失判据（词元级，OCR_FORMULA_MISS_CHECK 控制，默认开）──
# LaTeX 化/纠错改写是"内容词元守恒"的：标识符、数字、函数名原样保留，变化的是
# \frac、^{}、定界这类呈现层。因此"公式行内容词元是否落在稿中"可作整行是否
# 入库的判据，正常改写不误报。噪声纪律：OCR 字形含混/括号不配对/含汉字段的
# 行是 LLM 有权纠错重写的类别，保持原豁免——只在高置信整行缺失（可判且词元
# 一个都不在稿中）时才进入既有补写闭环；检测本身零 token。
_SUP_SUB_MAP = str.maketrans(
    "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"  # 上标 ⁰¹²³⁴⁵⁶⁷⁸⁹
    "\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089",  # 下标 ₀₁₂₃₄₅₆₇₈₉
    "01234567890123456789",
)


def _math_content_tokens(text: str) -> list[str]:
    """内容词元：字母/数字串中长度 ≥2 且含字母的字母段或字母数字段，
    统一小写。两个归一化保证 OCR 行与 md 可等价比较：
    - 上下标字符先转 ASCII 数字（OCR 常把 x² 直接输出为上标字符）；
    - 字母与数字粘连处拆开（OCR "x2" 与 LaTeX "x^{2}" 是同一内容，
      词元必须对等；拆出的单字符段不具判别力，剔除）。
    纯数字段不保留：正文常见、无判别力。"""
    t = str(text or "").translate(_SUP_SUB_MAP)
    out: list[str] = []
    for m in re.finditer(r"[0-9A-Za-z]+", t):
        for seg in re.findall(r"[0-9]+|[A-Za-z]+", m.group(0).lower()):
            if len(seg) >= 2 and re.search(r"[a-z]", seg):
                out.append(seg)
    return out


def _formula_high_conf_missing(text: str, md_tokens: set[str]) -> bool | None:
    """公式行是否"高置信缺失"（None = 不可判，维持原豁免，与旧行为一致）。

    可判条件（任一不满足 → None）：
    - 纯公式行：不含汉字段（含汉字段的行 LLM 按文本口径改写/合并，不可判）；
    - 括号配对（不成对说明 OCR 缺符错读，属需纠错类，豁免）；
    - 有 ≥2 个内容词元（词元判据才有信号；短小公式如 E=mc² 无从判断）。
    缺失判定：内容词元一个都不在 md 词元集中 → 整行未入库（改写只换呈现层、
    不换内容词元；一个都不在只可能是整行被丢弃）。"""
    if not text or re.search(r"[\u4e00-\u9fff]", text):
        return None
    for left, right in (("(", ")"), ("[", "]"), ("（", "）")):
        if text.count(left) != text.count(right):
            return None
    toks = _math_content_tokens(text)
    if len(toks) < 2:
        return None
    return not any(tok in md_tokens for tok in toks)


def _formula_miss_enabled() -> bool:
    return os.getenv("OCR_FORMULA_MISS_CHECK", "1").strip().lower() in {"1", "true", "yes", "on"}


def _recoverable_row(text: str) -> bool:
    """行是否"有资格被恢复"：按管线自身噪声口径过滤（页码/机构信息/纯数字符号
    残渣/乱码指纹）。公式行由调用方另行放行，不走此过滤。

    判定基于通用内容形态（中文成句 / 英文成词 / 符号占比），不是对任何语料的拟合：
    - 页眉页脚/机构/页码/纯数字符号残渣 → 不可恢复（LLM 删除它们是对的）；
    - 无中文且无 ≥2 字母词的符号串、数字占多数的单片段行 → 不可恢复（乱码指纹）。
    """
    t = str(text or "").strip()
    if not t or len(t) < 2:
        return False
    if _PAGEISH_RE.match(t) or _CHROME_RE.search(t):
        return False
    if _DIGIT_PUNCT_RE.fullmatch(t):
        return False
    cjk = sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff")
    letters = sum(1 for ch in t if "a" <= ch <= "z" or "A" <= ch <= "Z")
    digits = sum(1 for ch in t if "0" <= ch <= "9")
    words = re.findall(r"[A-Za-z]{2,}", t)
    other = len(t) - cjk - letters - digits - sum(
        1 for ch in t
        if ch in _ASCII_PUNCT_OK or "\u3000" <= ch <= "\u303f" or "\uff00" <= ch <= "\uffef"
    )
    other_ratio = other / max(len(t), 1)
    if cjk:
        return other_ratio <= 0.5
    if not words:
        return False
    if other_ratio > 0.25:
        return False
    if len(words) == 1:
        if digits > letters:
            return False
        if letters + digits < 12:
            return False
    return True


def _coalesce_runs(runs: list[dict], gap: int = _MID_COALESCE_GAP) -> list[dict]:
    """把间隔 ≤gap 个存在行的缺失段合并成一段（同一段被零散丢掉的文本）。"""
    merged: list[dict] = []
    for run in runs:
        if (
            merged
            and run["rows"][0]["index"] - merged[-1]["rows"][-1]["index"] - 1 <= gap
        ):
            merged[-1]["rows"].extend(run["rows"])
        else:
            merged.append({"rows": list(run["rows"])})
    for item in merged:
        item["chars"] = sum(len(r["line"]) for r in item["rows"])
    return merged


def _keep_for_append(rows: list[dict]) -> list[dict]:
    """兜底追加前过滤：公式行放行（引擎认定的公式内容），其余必须有恢复资格。"""
    return [r for r in rows if r.get("formula") or r.get("recoverable")]


def _still_missing_rows(rows: list[dict], markdown: str) -> list[dict]:
    """片段合入后的确定性复检：该段行中仍不在稿里的行（防模型只补了一部分）。
    正文行按 8 连字符查；公式行只在原判可判时按词元级复检（LaTeX 化后原文串
    不可比，不可判的公式行信任片段）；编号短标题行不做复检。"""
    md_blob = _md_compact(markdown)
    md_grams = {md_blob[i:i + _NGRAM_WINDOW] for i in range(max(0, len(md_blob) - _NGRAM_WINDOW + 1))}
    md_tokens = set(_math_content_tokens(markdown)) if _formula_miss_enabled() else set()
    missing: list[dict] = []
    for r in rows:
        if r.get("num_head") or not r.get("recoverable"):
            continue
        if r.get("formula"):
            if r.get("formula_miss") is not None and _formula_high_conf_missing(r["text"], md_tokens) is True:
                missing.append(r)
            continue
        if not _row_ngrams_present(r["line"], md_blob, md_grams):
            missing.append(r)
    return missing


def _draft_completeness(lines: list[dict], markdown: str) -> dict:
    """行级完整性报告（零 LLM）。rows_all 每行带类别/"是否存在于稿"/"恢复资格"标记；
    absent = 有恢复资格的正文行中不存在于稿的近整行丢失，加上词元级可判且
    高置信缺失的公式行（显式缺失，触发候选）。"""
    md_blob = _md_compact(markdown)
    md_grams = {md_blob[i:i + _NGRAM_WINDOW] for i in range(max(0, len(md_blob) - _NGRAM_WINDOW + 1))}
    md_tokens = set(_math_content_tokens(markdown))
    formula_miss_gate = _formula_miss_enabled()
    rows_all: list[dict] = []
    for item in lines:
        if str(item.get("role_hint") or "") == "boilerplate":
            continue
        text = str(item.get("formula") or item.get("text") or "").strip()
        line = _check_compact(text)
        if not line or len(line) < 4 or not _ROW_NOISE_RE.search(line):
            continue
        formula = _is_formula_like(item)
        num_head = len(line) <= 30 and bool(_NUM_HEAD_ISH_RE.match(line))
        rows_all.append({
            "index": len(rows_all), "text": text, "line": line,
            "formula": formula, "num_head": num_head,
            "recoverable": formula or _recoverable_row(text),
            "present": _row_ngrams_present(line, md_blob, md_grams),
            "formula_miss": (_formula_high_conf_missing(text, md_tokens)
                             if formula and formula_miss_gate else None),
        })
    present = {r["index"] for r in rows_all if r["present"]}
    absent = [
        r for r in rows_all
        if not r["num_head"] and r["recoverable"]
        and (
            (not r["formula"] and not r["present"])
            or (r["formula"] and r["formula_miss"] is True)
        )
    ]
    return {
        "rows_all": rows_all,
        "present": present,
        "absent_rows": absent,
        "absent_chars": sum(len(r["line"]) for r in absent),
        "total_chars": sum(len(r["line"]) for r in rows_all),
    }


def _group_runs(rows: list[dict]) -> list[dict]:
    """把行按原顺序聚成连续段。"""
    runs: list[dict] = []
    for row in sorted(rows, key=lambda r: r["index"]):
        if runs and row["index"] == runs[-1]["rows"][-1]["index"] + 1:
            runs[-1]["rows"].append(row)
        else:
            runs.append({"rows": [row]})
    for run in runs:
        run["chars"] = sum(len(r["line"]) for r in run["rows"])
    return runs


def _tail_segment(markdown: str) -> str:
    """稿尾最后一个空行段之后的文本（无空行则取整段尾部窗口）。"""
    tail = markdown[-_TAIL_SEGMENT_MAX:]
    gaps = list(re.finditer(r"\n\s*\n", tail))
    return tail[gaps[-1].end():] if gaps else tail


def _tail_looks_cut(markdown: str) -> bool:
    """稿尾结构截断信号（零 token）：最后一个段落呈残片形态
    （未闭合定界/转义残片/半截 LaTeX 收尾）→ 判定为截断。"""
    segment = _tail_segment(markdown or "").strip()
    if not segment:
        return False
    return _looks_like_cut_fragment(segment)


def _looks_like_cut_fragment(segment: str) -> bool:
    if len(segment) < 6:
        return False
    if "\\$" in segment:  # mathmd 对未闭合定界的转义残片
        return True
    if _count_unescaped_dollars(segment) % 2 == 1:
        return True
    stripped = segment.rstrip()
    if not stripped:
        return False
    if re.search(r"\\[A-Za-z]+$", stripped):   # 半截 LaTeX 命令收尾，如 \frac{
        return True
    if re.search(r"[$\\]$", stripped):         # 孤立的 $ 或反斜杠收尾
        return True
    if re.search(r"^[{$(\\]", stripped):       # 以开括号/$/反斜杠开头的残片段
        return True
    return False


def _count_unescaped_dollars(text: str) -> int:
    """数未转义的 $（跳过代码围栏与 \$ 转义），用于定界平衡判断。"""
    count = 0
    i = 0
    n = len(text or "")
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "`":
            if text.startswith("```", i):
                end = text.find("```", i + 3)
                i = n if end < 0 else end + 3
                continue
            end = text.find("`", i + 1)
            i = n if end < 0 else end + 1
            continue
        if ch == "$":
            count += 1
        i += 1
    return count


def _dollars_balanced(text: str) -> bool:
    return _count_unescaped_dollars(text) % 2 == 0


def _fragment_has_content(text: str) -> bool:
    """补写片段内容门：至少含一个可读字符，防止纯符号/空壳片段入库。"""
    t = (text or "").strip()
    if len(t) < 2:
        return False
    return bool(re.search(r"[0-9A-Za-z\u4e00-\u9fff]", t))


def _cut_incomplete_tail(draft: str) -> str:
    """裁掉稿尾被截断产生的残片（mathmd 归一化会把未闭合 $ 及其后文转义成
    \$ 开头的一串垃圾）。从后往前找最后一个"看起来完整"的段落边界。

    只裁最近一段空行之后的内容，且残片长度有上限；找不到安全边界就保持原稿。
    """
    tail_zone = draft[-_TAIL_MODE_GARBAGE_MAX:]
    boundaries = [m.start() for m in re.finditer(r"\n\s*\n", tail_zone)]
    if not boundaries:
        return draft
    for b in reversed(boundaries):
        segment = tail_zone[b:]
        if _looks_like_cut_fragment(segment):
            cut_at = len(draft) - len(tail_zone) + b
            return draft[:cut_at].rstrip()
    return draft


def _trim_duplicate_head(fragment: str, draft: str) -> str:
    """续写片段常把断点前一句也带出：按空白折叠找"稿尾后缀 == 片段前缀"的最长重叠并裁掉。"""
    dn = _check_compact(draft)
    fn = _check_compact(fragment)
    best = 0
    for k in range(min(len(dn), len(fn), 200), 5, -1):
        if dn.endswith(fn[:k]):
            best = k
            break
    if not best:
        return fragment
    cut = 0
    seen = 0
    for idx, ch in enumerate(fragment):
        if not ch.isspace():
            seen += 1
            if seen >= best:
                cut = idx + 1
                break
    return fragment[cut:].lstrip() if cut else fragment


def _dedupe_adjacent_heading_lines(markdown: str) -> str:
    """合并补写后可能出现的相邻重复标题（仅相邻、同文本的标题行）。"""
    out: list[str] = []
    last_heading = ""
    for line in (markdown or "").splitlines():
        if _HEADING_LINE_RE.match(line):
            if line == last_heading:
                continue
            last_heading = line
        else:
            last_heading = ""
        out.append(line)
    return "\n".join(out)


def _normalize_final(markdown: str) -> str:
    return _dedupe_adjacent_heading_lines(
        normalize_heading_numbering(normalize_markdown_math(markdown))
    )


def _nearest_present_rows(rows_all: list[dict], present: set, run: dict, *, before: int = 2, after: int = 2) -> tuple[list[str], list[str]]:
    """缺失段前/后的"已在稿中存在"行原文（补写用的位置上下文）。"""
    first, last = run["rows"][0]["index"], run["rows"][-1]["index"]
    prev_rows: list[str] = []
    for row in reversed(rows_all[:first]):
        if row["index"] not in present:
            continue
        prev_rows.append(row["text"])
        if len(prev_rows) >= before:
            break
    prev_rows.reverse()
    next_rows: list[str] = []
    for row in rows_all[last + 1:]:
        if row["index"] not in present:
            continue
        next_rows.append(row["text"])
        if len(next_rows) >= after:
            break
    return prev_rows, next_rows


def _find_line_with(draft_lines: list[str], anchor_compact: str) -> int | None:
    """在稿里定位能容纳 anchor 的行（双向子串，容忍合并/截断），返回行号。"""
    if len(anchor_compact) < 6:
        return None
    for idx, line in enumerate(draft_lines):
        c = _check_compact(line)
        if c and (anchor_compact in c or c in anchor_compact):
            return idx
    return None


def _insert_fragment(draft: str, fragment: str, rows_all: list[dict], present: set, run: dict) -> str:
    """把补写片段插到稿中合适位置：优先"缺失段前最近可定位存在行"之后，
    其次"后文存在行"之前，最后稿尾追加。"""
    lines = draft.splitlines()
    first, last = run["rows"][0]["index"], run["rows"][-1]["index"]
    for row in reversed(rows_all[:first]):
        if row["index"] not in present or len(row["line"]) < 6:
            continue
        hit = _find_line_with(lines, row["line"])
        if hit is not None:
            lines.insert(hit + 1, "")
            lines.insert(hit + 2, fragment)
            return "\n".join(lines)
    for row in rows_all[last + 1:]:
        if row["index"] not in present or len(row["line"]) < 6:
            continue
        hit = _find_line_with(lines, row["line"])
        if hit is not None:
            lines.insert(hit, "")
            lines.insert(hit, fragment)
            return "\n".join(lines)
    return (draft.rstrip() + "\n\n" + fragment) if draft.strip() else fragment


def _build_continue_prompt(rows_all: list[dict], present: set, rows: list[dict], draft: str, *, tail_mode: bool) -> str:
    run = {"rows": rows}
    prev_rows, next_rows = _nearest_present_rows(rows_all, present, run)
    parts: list[str] = []
    if tail_mode:
        tail = draft.strip()[-240:]
        parts.append("【当前稿尾(断点附近, 可能有残片, 忽略残片)】\n…" + tail)
    context = ["【缺失段前后的 OCR 原文行(按页序)】"]
    if prev_rows:
        context.append("缺失段前文：\n" + "\n".join(f"- {t[:200]}" for t in prev_rows))
    context.append("缺失行：\n" + "\n".join(f"- {r['text'][:300]}" for r in rows))
    if next_rows:
        context.append("缺失段后文：\n" + "\n".join(f"- {t[:200]}" for t in next_rows))
    parts.append("\n".join(context))
    parts.append("请直接输出整理后的 Markdown 内容。")
    return "\n\n".join(parts)


def _continue_call(client, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    """一次补写调用（独立 label，便于与主整理做成本归因）。"""
    import asyncio

    text = asyncio.run(
        client.text(
            system_prompt,
            user_prompt,
            temperature=0.1,
            max_tokens=max_tokens,
            label=_FIX_LABEL,
        )
    )
    return str(text or "").strip()


def ensure_markdown_complete(markdown: str, lines: list[dict]) -> str:
    """整理稿完整性闭环（显式缺失才触发；无缺失零调用）。

    流程：行级自检 → 缺失分类（近整行丢失 / 稿尾截断）→ 按段小补写
    （尾段 1 次 + 中段若干，≤ 预算）→ 超预算/失败一律原文兜底。"""
    import os

    raw = str(markdown or "").strip()
    gate = os.getenv("OCR_COMPLETENESS_FIX", "1").strip().lower()
    if gate not in {"1", "true", "yes", "on"}:
        return raw
    if not raw:
        return raw

    check = _draft_completeness(lines, raw)
    rows_all = check["rows_all"]
    present = check["present"]
    absent = check["absent_rows"]
    n = len(rows_all)
    last_present = max(present) if present else -1
    absent_runs = _coalesce_runs(_group_runs(absent))

    tail_cut_signal = _tail_looks_cut(raw)
    # 尾部区域：最后一个"可确认存在"的行之后、且有恢复资格的行（公式行放行）
    tail_rows = [
        r for r in rows_all
        if r["index"] > last_present and (r["formula"] or r["recoverable"])
    ][:_TAIL_ROWS_CAP]
    tail_absent = any(run["rows"][-1]["index"] >= n - 1 for run in absent_runs)
    needs_tail = bool(tail_rows) and (tail_cut_signal or tail_absent)
    # 中段：缺失段未延伸到尾部区域，且有实质内容量
    mid_candidates = [
        run for run in absent_runs
        if run["rows"][-1]["index"] <= last_present
        and (
            run["chars"] >= _ABSENT_MIN_CHARS
            or max(len(r["line"]) for r in run["rows"]) >= _ABSENT_SINGLE_MIN_LEN
        )
    ]
    if not needs_tail and not mid_candidates:
        return raw

    try:
        from .engines import get_llm_client

        client = get_llm_client()
    except Exception:  # noqa: BLE001
        client = None

    if client is None:
        appended_rows: list[dict] = []
        if needs_tail:
            appended_rows.extend(_keep_for_append(tail_rows))
        for run in sorted(mid_candidates, key=lambda r: -r["chars"]):
            appended_rows.extend(_keep_for_append(run["rows"]))
        logger.warning("完整性补写不可用(无 LLM 客户端)，缺失 %d 行原文兜底追加", len(appended_rows))
        final = raw + "\n\n" + "\n".join(r["text"] for r in appended_rows)
        return _normalize_final(final)

    budget_calls = _CONTINUE_MAX_CALLS
    try:
        budget_calls = max(1, int(os.getenv("OCR_CONTINUE_MAX_CALLS", str(_CONTINUE_MAX_CALLS))))
    except ValueError:
        pass
    max_tokens_cap = _CONTINUE_MAX_TOKENS
    try:
        max_tokens_cap = max(256, int(os.getenv("OCR_CONTINUE_MAX_TOKENS", str(_CONTINUE_MAX_TOKENS))))
    except ValueError:
        pass

    draft = raw
    fired = 0
    modes: list[str] = []
    fallback_rows = 0

    def _sanitize_fragment(fragment: str) -> str:
        frag = _strip_md_fences(_trim_duplicate_head(fragment, draft)).strip()
        if not frag or not _dollars_balanced(frag) or not _fragment_has_content(frag):
            return ""
        return frag

    def _fallback_append(rows: list[dict]) -> None:
        nonlocal draft, fallback_rows
        kept = _keep_for_append(rows)
        if not kept:
            return
        draft = (draft.rstrip() + "\n\n" + "\n".join(r["text"] for r in kept))
        fallback_rows += len(kept)

    # 1) 稿尾截断（优先，最多 1 次）
    if needs_tail and fired < budget_calls:
        base = _cut_incomplete_tail(draft)
        if base != draft:
            draft = base
        system = _CONTINUE_TAIL_INSTRUCT
        user_prompt = _build_continue_prompt(rows_all, present, tail_rows, draft, tail_mode=True)
        tail_chars = sum(len(r["line"]) for r in tail_rows)
        budget = max(512, min(max_tokens_cap, int(tail_chars * 1.3)))
        logger.warning(
            "OCR 完整性补写：稿尾疑似截断（信号=%s 尾行=%d），续尾调用",
            tail_cut_signal, len(tail_rows),
        )
        try:
            fragment = _continue_call(client, system, user_prompt, budget)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCR 完整性补写调用失败（%s），缺失行原文兜底", exc)
            fragment = ""
        fragment = _sanitize_fragment(fragment) if fragment else ""
        if fragment:
            draft = (draft.rstrip() + "\n\n" + fragment) if draft.strip() else fragment
            fired += 1
            modes.append("tail")
            # 复检：片段未覆盖的尾行转入兜底（公式行除外）
            still = _still_missing_rows(tail_rows, draft)
            if still:
                _fallback_append(still)
        else:
            _fallback_append(tail_rows)

    # 2) 中段缺失（按缺失量从大到小，剩余预算内；超预算直接兜底）
    for run in sorted(mid_candidates, key=lambda r: -r["chars"]):
        if fired >= budget_calls:
            _fallback_append(run["rows"])
            continue
        system = _CONTINUE_MID_INSTRUCT
        user_prompt = _build_continue_prompt(rows_all, present, run["rows"], draft, tail_mode=False)
        budget = max(512, min(max_tokens_cap, int(run["chars"] * 1.3)))
        logger.warning(
            "OCR 完整性补写：中段缺失 %d 行/%d 字符，补中调用",
            len(run["rows"]), run["chars"],
        )
        try:
            fragment = _continue_call(client, system, user_prompt, budget)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCR 完整性补写调用失败（%s），缺失行原文兜底", exc)
            fragment = ""
        fragment = _sanitize_fragment(fragment) if fragment else ""
        if fragment:
            draft = _insert_fragment(draft, fragment, rows_all, present, run)
            fired += 1
            modes.append("mid")
            # 复检：片段未覆盖的行转入兜底，防"补了一段但段内仍有遗漏"静默丢失
            still = _still_missing_rows(run["rows"], draft)
            if still:
                _fallback_append(still)
        else:
            _fallback_append(run["rows"])

    if fired or fallback_rows:
        draft = _normalize_final(draft)
        cleaned = _cut_incomplete_tail(draft)
        if cleaned != draft:
            logger.warning("OCR 完整性补写：稿尾仍残留截断残片（%d 字符），已裁除", len(draft) - len(cleaned))
            draft = cleaned
        logger.warning(
            "OCR 完整性补写完成：%d 次调用（%s），兜底 %d 行",
            fired, ",".join(modes), fallback_rows,
        )
    return draft


__all__ = [
    "RECONSTRUCT_SYSTEM_PROMPT",
    "REVIEW_SYSTEM_PROMPT",
    "apply_review_patches",
    "ensure_markdown_complete",
    "normalize_heading_numbering",
    "reconstruct_markdown",
    "review_markdown",
]
