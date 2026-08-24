"""LLM 重构：OCR 碎片 → 结构化 Markdown（标题层级 / **重点** / 表格 / 去噪）。

- 输入：OCR 行列表（text + 可选 formula）
- 输出：结构化 Markdown 文本
- LLM 不可用或失败：返回按行拼的原始文本（不阻塞）
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

RECONSTRUCT_SYSTEM_PROMPT = """你是「笔记整理器」。把 OCR 识别出的笔记碎片整理成一份结构化 Markdown，供知识库检索。

要求：
1. **保留全部内容**：不要漏掉任何识别到的文字、数字、公式；OCR 明显错字可顺手纠正，但不要臆造
2. **双轨标题规则**：输入中 title_decision=locked_heading 的行是高置信标题，必须输出为 Markdown 标题；只能轻微修 OCR 错字，不要降为正文。title_decision=locked_body 的行默认保持正文/公式，不要升标题。title_decision=ambiguous 的行才结合上下文判断是否为标题
3. **推断结构**：对 locked_heading 和 ambiguous 标题，结合 heading_level_hint / heading_score / 上下文，推断章节/知识点层级（# 标题、## 小节、### 知识点）
4. **标题层级一致**：同类编号（如 一、二、三 或 1.1/1.2）尽量保持同级；页首大标题通常高于普通小节标题
5. **正文不要误升标题**：locked_body、长句、以句号/逗号结尾的解释性内容，即使包含关键词，也不要强行改成标题
6. **重点标注**：对像"重点/必考/关键/注意/易错"的内容用 **加粗** 标出（不要过度标注）
7. **公式**：已有 ``$$...$$`` 的公式原样保留在对应位置
8. **表格**：如果内容是成列的数据（行结构明显），整理成 Markdown 表格
9. 去除 OCR 噪声（孤立标点、乱码），合并被断行的完整句子
10. 直接输出 Markdown 正文，不要前言后语、不要 Markdown 代码围栏"""

REVIEW_SYSTEM_PROMPT = """你是「OCR Markdown 保守审校器」。你会拿到一份已经整理过的 Markdown。

任务：只修正稿子里明显由 OCR 或整理造成的问题，不做自由发挥，不新增稿中没有的信息。

允许修正：
1. 明显 OCR 误识别：如 sin/sln、lim/1im、上下标/符号孤立错字、重复乱码、断行造成的错拼
2. Markdown 结构问题：标题层级明显错乱、列表/表格破损、重复标题、代码围栏误包裹
3. 公式排版问题：明显被拆断的公式可合并；不确定的公式保持原样
4. 断句与空白：合并不该断开的句子，移除孤立噪声字符

禁止：
1. 不要根据常识重写定义、定理、公式或结论
2. 不要补充稿中没有的知识
3. 不要把不确定内容改成你认为正确的内容
4. 不要删除稿中能辨认出的有效信息

直接输出审校后的 Markdown 全文，不要前言后语，不要 JSON，不要 Markdown 代码围栏。
如果没有需要修正的地方，原样返回输入稿。"""


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
        return raw
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
        return str(text).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 重构失败，返回原始文本：%s", exc)
        return raw


def review_markdown(
    markdown: str,
    lines: list[dict],
    *,
    max_tokens: int = 9000,
) -> tuple[str, str]:
    """LLM 保守审校；失败时返回原稿和说明。"""
    draft = str(markdown or "").strip()
    if not draft:
        return draft, "未生成可审校的 Markdown。"
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
                "待审校 Markdown：\n"
                f"{draft}",
                temperature=0.0,
                max_tokens=max_tokens,
                label="ocr/review",
            )
        )
        return _as_reviewed_markdown(str(text), draft)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 审校失败，返回重构稿：%s", exc)
        return draft, f"LLM 审校失败，已保留重构稿：{exc}"


def _strip_md_fences(text: str) -> str:
    raw = (text or "").strip()
    if not raw.startswith("```"):
        return raw
    raw = re.sub(r"^```(?:markdown|md|json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _as_reviewed_markdown(text: str, draft: str) -> tuple[str, str]:
    """把审校模型输出收成 Markdown。残缺 JSON 信封则退回完整重构稿。"""
    raw = _strip_md_fences(text)
    if not raw:
        return draft, "审校结果为空，已保留重构稿。"
    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("审校 JSON 不完整，已保留重构稿")
            return draft, "审校 JSON 不完整，已保留重构稿。"
        if isinstance(payload, dict):
            reviewed = str(payload.get("markdown") or "").strip()
            notes = payload.get("notes") or []
            if isinstance(notes, list):
                notes_text = "\n".join(
                    f"- {str(item).strip()}" for item in notes if str(item).strip()
                )
            else:
                notes_text = str(notes).strip()
            return reviewed or draft, notes_text or "已完成 Markdown 审校。"
    return raw, "已完成 Markdown 审校。"


__all__ = ["RECONSTRUCT_SYSTEM_PROMPT", "REVIEW_SYSTEM_PROMPT", "reconstruct_markdown", "review_markdown"]
