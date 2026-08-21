"""LLM 重构：OCR 碎片 → 结构化 Markdown（标题层级 / **重点** / 表格 / 去噪）。

- 输入：OCR 行列表（text + 可选 formula）
- 输出：结构化 Markdown 文本
- LLM 不可用或失败：返回按行拼的原始文本（不阻塞）
"""
from __future__ import annotations

import json
import logging

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
8. **图示区域**：role_hint=visual 的条目不是识别出的图内容，只表示页面中存在图示/草图/坐标图/模型图区域。必须在相应位置保留一行 HTML 注释，格式为 ``<!-- 图示: label; type=...; bbox=... -->``；不要臆造图中含义
9. **表格**：如果内容是成列的数据（行结构明显），整理成 Markdown 表格
10. 去除 OCR 噪声（孤立标点、乱码），合并被断行的完整句子
11. 直接输出 Markdown 正文，不要前言后语、不要 Markdown 代码围栏"""


def _fragments_to_text(lines: list[dict]) -> str:
    """行列表 → 拼接文本；无 LLM 时也尽量保留标题层级。"""
    parts: list[str] = []
    for item in lines:
        visual = item.get("visual_region")
        formula = item.get("formula")
        text = item.get("text") or ""
        role = item.get("role_hint")
        decision = item.get("title_decision")
        level = int(item.get("heading_level_hint") or 0)
        if visual:
            label = visual.get("label") or "疑似图示"
            kind = visual.get("type") or "diagram"
            bbox = item.get("bbox") or []
            parts.append(f"<!-- 图示: {label}; type={kind}; bbox={bbox} -->")
        elif formula:
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
        visual = item.get("visual_region") or {}
        if not text and not formula and not visual:
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
            "conf": round(float(item.get("conf") or 0), 3),
            "visual_region": {
                "id": visual.get("id"),
                "type": visual.get("type"),
                "label": visual.get("label"),
                "ink_density": visual.get("ink_density"),
                "bbox": item.get("bbox") if visual else None,
            } if visual else None,
            "layout": {
                "top": layout.get("top"),
                "height_ratio": layout.get("height_ratio"),
                "gap_before": layout.get("gap_before"),
                "gap_after": layout.get("gap_after"),
                "centered": layout.get("centered"),
                "near_left": layout.get("near_left"),
            },
        }
        payload.append(row)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def reconstruct_markdown(lines: list[dict]) -> str:
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
                max_tokens=8000,
                label="ocr/reconstruct",
            )
        )
        return str(text).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 重构失败，返回原始文本：%s", exc)
        return raw


__all__ = ["RECONSTRUCT_SYSTEM_PROMPT", "reconstruct_markdown"]
