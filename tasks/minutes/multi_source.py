"""多源材料装配器：处理用户传入的 keypoints、notes、vision 等辅助材料，
动态装配为标准化的 User Message 上下文块与 Prompt 规约块。
"""
from __future__ import annotations

from typing import Any

from tasks.minutes.prompts import (
    KEYPOINTS_PROMPT_BLOCK,
    NOTES_PROMPT_BLOCK,
    VISION_PROMPT_BLOCK,
)


def _format_item_list(data: Any) -> str:
    """将字符串或列表归一化为 Markdown 列表文本。"""
    if not data:
        return ""
    if isinstance(data, str):
        lines = [line.strip() for line in data.strip().splitlines() if line.strip()]
        return "\n".join(lines)
    if isinstance(data, list):
        formatted: list[str] = []
        for item in data:
            if isinstance(item, str):
                s = item.strip()
                if s:
                    formatted.append(f"- {s}" if not s.startswith(("-", "*", "•")) else s)
            elif isinstance(item, dict):
                # 支持 {"quote": "...", "note": "..."} 结构
                quote = str(item.get("quote") or item.get("text") or "").strip()
                note = str(item.get("note") or item.get("comment") or "").strip()
                if quote and note:
                    formatted.append(f"- 原话：\"{quote}\" （笔记：{note}）")
                elif quote:
                    formatted.append(f"- 原话：\"{quote}\"")
                elif note:
                    formatted.append(f"- 笔记：{note}")
        return "\n".join(formatted)
    return str(data).strip()


def build_multi_source_context(texts: dict[str, Any] | None) -> tuple[str, list[str]]:
    """从 texts 字典提取 keypoints、notes、vision 材料，生成上下文块。

    Args:
        texts: 请求中包含的 texts 字典

    Returns:
        (aux_context, active_labels):
        - aux_context: 格式化后的【辅助参考材料】Markdown 字符串（若无有效辅助材料则返回空字符串）
        - active_labels: 包含有效材料的标签列表，如 ["keypoints", "notes"]
    """
    if not texts or not isinstance(texts, dict):
        return "", []

    active_labels: list[str] = []
    blocks: list[str] = []

    # 1. 用户核心关键点
    kp_raw = texts.get("keypoints") or texts.get("core_points")
    kp_str = _format_item_list(kp_raw)
    if kp_str:
        active_labels.append("keypoints")
        blocks.append(f"### 【用户核心关键点】\n{kp_str}")

    # 2. 用户划线原话与笔记
    notes_raw = texts.get("notes") or texts.get("user_notes")
    notes_str = _format_item_list(notes_raw)
    if notes_str:
        active_labels.append("notes")
        blocks.append(f"### 【用户划线原话与笔记】\n{notes_str}")

    # 3. 视觉信息参考
    vision_raw = texts.get("vision") or texts.get("vision_info") or texts.get("ocr")
    vision_str = _format_item_list(vision_raw)
    if vision_str:
        active_labels.append("vision")
        blocks.append(f"### 【视觉信息参考 (OCR)】\n{vision_str}")

    if not blocks:
        return "", []

    aux_context = "【辅助参考材料】\n" + "\n\n".join(blocks)
    return aux_context, active_labels


def build_aux_rules_for_prompt(active_labels: list[str]) -> str:
    """根据实际存在的辅助材料标签，拼接对应的 System Prompt 规约约束。

    Args:
        active_labels: 包含有效材料的标签列表

    Returns:
        追加到 System Prompt 的规约字符串（若无有效标签则返回空字符串）
    """
    if not active_labels:
        return ""

    rules: list[str] = []
    if "keypoints" in active_labels:
        rules.append(KEYPOINTS_PROMPT_BLOCK)
    if "notes" in active_labels:
        rules.append(NOTES_PROMPT_BLOCK)
    if "vision" in active_labels:
        rules.append(VISION_PROMPT_BLOCK)

    if not rules:
        return ""

    return "## 多源辅助参考使用规约（仅针对输入中出现的辅助标签生效）\n\n" + "\n\n".join(rules)
