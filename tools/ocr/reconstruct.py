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
4. **标题层级一致**：同类编号（如 一、二、三 或 1.1/1.2）尽量保持同级；页首大标题通常高于普通小节标题
5. **正文不要误升标题**：locked_body、长句、以句号/逗号结尾的解释性内容，即使包含关键词，也不要强行改成标题
6. **重点标注**：对像"重点/必考/关键/注意/易错"的内容用 **加粗** 标出（不要过度标注）
7. **公式定界**：行内公式只用一对 ``$...$``；独立成行的公式才用 ``$$...$$``。禁止 ``$...$$`` / ``$$...$`` 混用，公式内部不要再写美元符号。已有 ``$$...$$`` 的公式原样保留位置，但定界必须成对
8. **表格**：如果内容是成列的数据（行结构明显），整理成 Markdown 表格
9. 去除 OCR 噪声（孤立标点、乱码），合并被断行的完整句子
10. 直接输出 Markdown 正文，不要前言后语、不要 Markdown 代码围栏"""

REVIEW_SYSTEM_PROMPT = """你是「OCR Markdown 保守审校器」。你会拿到一份带行号的整理稿。

任务：只指出需要改的行，不要重写全文，不要输出 Markdown 正文。

允许修正：
1. 明显 OCR 误识别：如 sin/sln、lim/1im、上下标/符号孤立错字、重复乱码、断行造成的错拼
2. Markdown 结构问题：标题层级明显错乱、列表/表格破损、重复标题、代码围栏误包裹
3. 公式排版问题：明显被拆断的公式可合并；把 $...$$ / $$...$ / $$$ 改成合法的 $...$ 或 $$...$$；不确定的公式保持原样
4. 断句与空白：合并不该断开的句子，移除孤立噪声字符

禁止：
1. 不要根据常识重写定义、定理、公式或结论
2. 不要补充稿中没有的知识
3. 不要把不确定内容改成你认为正确的内容
4. 不要删除稿中能辨认出的有效信息
5. 不要做全文短词替换；每条补丁必须对准指定行
6. 不要把 L00N: 行号写进 from / to

输出严格 JSON 对象，不要 Markdown 代码围栏：
{"patches":[{"line":42,"from":"该行原文","to":"该行新文"}]}

字段：
- line：稿子里 L00N 的编号，从 1 起
- end：可选，跨行合并时的最后一行（含）；单行不要写
- from：必须从指定行原文原样抄录（不要抄 L00N: 前缀）
- to：替换后的文本；跨行时 from / to 用换行连接

没有需要修正的地方：{"patches":[]}
最多 30 条补丁。"""

_LINE_PREFIX_RE = re.compile(r"^L\d+:\s*")
_REVIEW_MAX_PATCHES = 30


def _fragments_to_text(lines: list[dict]) -> str:
    """行列表 → 拼接文本；无 LLM 时也尽量保留标题层级。"""
    parts: list[str] = []
    for item in lines:
        formula = item.get("formula")
        text = item.get("text") or ""
        role = item.get("role_hint")
        decision = item.get("title_decision")
        level = int(item.get("heading_level_hint") or 0)
        if formula:
            parts.append(formula)
        elif text and (decision == "locked_heading" or role == "heading"):
            marks = "#" * min(max(level or 2, 1), 6)
            parts.append(f"{marks} {text}")
        elif text:
            parts.append(text)
    return "\n".join(parts)


def _lines_to_structured_payload(lines: list[dict]) -> str:
    """压缩版 OCR 行 JSON，给 LLM 保留标题/版面提示。"""
    payload = []
    for idx, item in enumerate(lines, start=1):
        formula = str(item.get("formula") or "").strip()
        text = str(item.get("text") or "").strip()
        if not text and not formula:
            continue
        layout = item.get("layout") or {}
        row = {
            "i": idx,
            "text": text,
            "formula": formula,
            "role_hint": item.get("role_hint") or "body",
            "title_decision": item.get("title_decision") or "ambiguous",
            "heading_score": item.get("heading_score") or 0,
            "heading_level_hint": item.get("heading_level_hint"),
            "layout": {
                "top": layout.get("top"),
                "height_ratio": layout.get("height_ratio"),
                "gap_before": layout.get("gap_before"),
                "gap_after": layout.get("gap_after"),
                "centered": layout.get("centered"),
                "near_left": layout.get("near_left"),
            },
        }
        if item.get("conf") is not None:
            row["conf"] = round(float(item["conf"]), 3)
        payload.append(row)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def reconstruct_markdown(lines: list[dict], *, max_tokens: int = 8000) -> str:
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
        return normalize_markdown_math(raw)
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
        return normalize_markdown_math(str(text).strip())
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 重构失败，返回原始文本：%s", exc)
        return normalize_markdown_math(raw)


def review_markdown(
    markdown: str,
    lines: list[dict],
    *,
    max_tokens: int = 2000,
) -> tuple[str, str]:
    """LLM 只出补丁；程序按行号+原文核对后本地改稿。失败时返回原稿。"""
    del lines
    draft = str(markdown or "").strip()
    if not draft:
        return draft, "未生成可审校的 Markdown。"
    draft = normalize_markdown_math(draft)
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
                "待审校 Markdown（L00N 是行号，不要写进 from/to）：\n"
                f"{_number_draft_lines(draft)}\n",
                temperature=0.0,
                max_tokens=max_tokens,
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


def _strip_line_prefixes(text: str) -> str:
    return "\n".join(_LINE_PREFIX_RE.sub("", row) for row in (text or "").splitlines())


def _strip_md_fences(text: str) -> str:
    raw = (text or "").strip()
    if not raw.startswith("```"):
        return raw
    raw = re.sub(r"^```(?:markdown|md|json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _json_from_review(text: str):
    raw = _strip_md_fences(text)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start_obj, start_arr = raw.find("{"), raw.find("[")
    starts = [pos for pos in (start_obj, start_arr) if pos >= 0]
    if not starts:
        return None
    start = min(starts)
    end_token = "}" if raw[start] == "{" else "]"
    end = raw.rfind(end_token)
    if end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
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
            start = int(item.get("line") or item.get("start") or 0)
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
        src = _strip_line_prefixes(str(item.get("from") if item.get("from") is not None else item.get("original") or item.get("old") or ""))
        if "to" in item:
            dst_raw = item.get("to")
        elif "text" in item:
            dst_raw = item.get("text")
        else:
            dst_raw = item.get("new")
        if dst_raw is None:
            notes.append(f"- L{start} 缺少 to，已跳过")
            continue
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
    return apply_review_patches(draft, patches)


__all__ = [
    "RECONSTRUCT_SYSTEM_PROMPT",
    "REVIEW_SYSTEM_PROMPT",
    "apply_review_patches",
    "reconstruct_markdown",
    "review_markdown",
]
