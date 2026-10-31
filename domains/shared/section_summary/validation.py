"""模型输出校验与规范化。

LLM 负责切分，代码负责：
1. 从围栏/废话中提取 JSON 数组
2. 校验字段并清洗长度
3. 把 time_start 映射回原文真实行，保证时间不伪造
4. 修正首段、去重、排序、记录 warning
"""
from __future__ import annotations

import json
import re
from typing import Any, List, Optional, Tuple

from .config import (
    MAX_KEYWORDS,
    MAX_KEYWORD_CHARS,
    MAX_SUMMARY_CHARS,
    MAX_TITLE_CHARS,
)
from .errors import SectionSummaryFormatError
from .models import SectionSummary, TranscriptLine
from .parser import timestamp_to_seconds

_TIME_IN_TEXT_RE = re.compile(r"\d{1,3}:\d{1,2}(?::\d{1,2})?")
_SENTENCE_END = "。！？；.!?;"


def _strip_code_fence(text: str) -> str:
    value = (text or "").strip()
    if not value.startswith("```"):
        return value
    value = value.split("\n", 1)[-1]
    fence = value.rfind("```")
    if fence >= 0:
        value = value[:fence]
    value = value.strip()
    if value[:4].lower() == "json":
        value = value[4:].lstrip()
    return value


def extract_json_array(raw: str) -> List[Any]:
    """从模型输出中提取顶层 JSON 数组；兼容被对象包装的情况。"""
    text = _strip_code_fence(raw)
    if not text:
        raise SectionSummaryFormatError("模型返回空内容")

    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(text)
    except json.JSONDecodeError:
        start = text.find("[")
        if start < 0:
            raise SectionSummaryFormatError("模型输出不是合法 JSON 数组")
        try:
            data, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError as exc:
            raise SectionSummaryFormatError(
                f"模型输出不是合法 JSON 数组：{exc}"
            ) from exc

    if isinstance(data, dict):
        for key in ("sections", "segments", "data", "items"):
            value = data.get(key)
            if isinstance(value, list):
                data = value
                break
        else:
            raise SectionSummaryFormatError("模型输出不是 JSON 数组")

    if not isinstance(data, list):
        raise SectionSummaryFormatError("模型输出不是 JSON 数组")
    return data


def fallback_title(value: str) -> str:
    """从正文首句生成一个兜底标题。"""
    text = re.split(r"[。！？；.!?;]", (value or "").strip(), maxsplit=1)[0]
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_TITLE_CHARS].rstrip() or "会议片段"


def clean_title(value: str, summary: str = "") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().strip("“”\"'")
    if not text:
        text = fallback_title(summary)
    if len(text) > MAX_TITLE_CHARS:
        text = text[:MAX_TITLE_CHARS].rstrip()
    return text


def clean_summary(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    if len(text) <= MAX_SUMMARY_CHARS:
        return text

    head = text[:MAX_SUMMARY_CHARS]
    cut = max(head.rfind(punct) for punct in _SENTENCE_END)
    if cut >= 100:
        return head[: cut + 1]
    return head[: MAX_SUMMARY_CHARS - 1].rstrip() + "…"


def clean_keywords(values: Any) -> List[str]:
    if not isinstance(values, (list, tuple)):
        return []
    cleaned: List[str] = []
    for raw in values:
        value = re.sub(r"\s+", " ", str(raw or "")).strip()
        value = value.strip("“”\"'，,。.；;、 ")
        if not value:
            continue
        # 超长关键词直接丢弃：截断容易截出半个词（如 result_code -> result_cod）
        if len(value) > MAX_KEYWORD_CHARS:
            continue
        if value not in cleaned:
            cleaned.append(value)
        if len(cleaned) >= MAX_KEYWORDS:
            break
    return cleaned


def _find_boundary(
    seconds: int,
    lines: List[TranscriptLine],
    cursor: int,
) -> Optional[int]:
    """从 cursor 开始，按原文顺序找第一条时间戳匹配的发言。"""
    for index in range(cursor, len(lines)):
        if lines[index].seconds == seconds:
            return index
    return None


def _section_seconds(section: SectionSummary) -> Optional[int]:
    seconds = timestamp_to_seconds(section.time_start)
    if seconds is not None:
        return seconds
    match = _TIME_IN_TEXT_RE.search(section.time_start or "")
    if match:
        return timestamp_to_seconds(match.group(0))
    return None


def _coerce_item(item: Any) -> Any:
    """对常见的小偏差做轻量修复，避免一个字段类型错误丢掉整段。"""
    if not isinstance(item, dict):
        return item
    data = dict(item)
    key_words = data.get("key_words")
    if key_words is None:
        data["key_words"] = []
    elif isinstance(key_words, str):
        data["key_words"] = [
            part.strip()
            for part in re.split(r"[、,，;；]", key_words)
            if part.strip()
        ]
    return data


def normalize_sections(
    raw: str,
    lines: List[TranscriptLine],
) -> Tuple[List[SectionSummary], List[str]]:
    """把模型输出规整成可渲染的分段列表。"""
    if not lines:
        return [], ["逐字稿为空"]

    warnings: List[str] = []
    items = extract_json_array(raw)

    parsed: List[Tuple[int, SectionSummary]] = []
    for item in items:
        try:
            section = SectionSummary.model_validate(_coerce_item(item))
        except Exception as exc:  # noqa: BLE001 - 单条非法只影响该条
            warnings.append(f"忽略非法分段：{str(exc)[:120]}")
            continue

        seconds = _section_seconds(section)
        if seconds is None:
            warnings.append(f"忽略无法解析 time_start 的分段：{section.time_start!r}")
            continue
        parsed.append((seconds, section))

    if not parsed:
        return [], warnings

    original_order = [section.time_start for _, section in parsed]
    parsed.sort(key=lambda pair: pair[0])
    if [section.time_start for _, section in parsed] != original_order:
        warnings.append("模型输出未按时间排序，已按 time_start 重新排序")

    deduped: List[Tuple[int, SectionSummary]] = []
    seen_seconds: set[int] = set()
    for seconds, section in parsed:
        if seconds in seen_seconds:
            warnings.append(f"忽略重复 time_start：{section.time_start}")
            continue
        seen_seconds.add(seconds)
        deduped.append((seconds, section))

    positioned: List[Tuple[int, SectionSummary]] = []
    cursor = 0
    for seconds, section in deduped:
        line_index = _find_boundary(seconds, lines, cursor)
        if line_index is None:
            warnings.append(f"忽略原文中不存在的 time_start：{section.time_start}")
            continue
        cursor = line_index + 1
        positioned.append((line_index, section))

    if not positioned:
        return [], warnings

    final: List[SectionSummary] = []
    for position, (line_index, section) in enumerate(positioned):
        next_index = (
            positioned[position + 1][0]
            if position + 1 < len(positioned)
            else len(lines)
        )
        if next_index <= line_index:
            warnings.append(f"忽略空分段：{section.time_start}")
            continue

        summary = clean_summary(section.section_summary)
        if not summary:
            warnings.append(f"忽略空纪要分段：{lines[line_index].timestamp}")
            continue

        final.append(
            SectionSummary(
                time_start=lines[line_index].timestamp,
                title=clean_title(section.title, summary),
                key_words=clean_keywords(section.key_words),
                section_summary=summary,
            )
        )

    if final and final[0].time_start != lines[0].timestamp:
        warnings.append("第一段未从原文首行开始，已向前对齐到首行")
        final[0] = final[0].model_copy(
            update={"time_start": lines[0].timestamp}
        )

    return final, list(dict.fromkeys(warnings))


__all__ = [
    "clean_keywords",
    "clean_summary",
    "clean_title",
    "extract_json_array",
    "fallback_title",
    "normalize_sections",
]
