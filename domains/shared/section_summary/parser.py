"""逐字稿解析与 Prompt 输入格式化。

兼容常见 ASR 格式：
1. ``张三 00:00:01\\n内容``
2. ``[00:00:01] 张三\\n内容``
3. ``00:00:01 [张三] 内容``
4. ``00:00:01 张三 内容``

发言行前的列表符号（``•`` / ``·`` / ``-`` / ``*``）会先被剥离，
因此 ``• 发言者 1 52:00`` 也能正常识别。
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .errors import SectionSummaryInputError
from .models import TranscriptLine

_TS = r"\d{1,3}:\d{1,2}(?::\d{1,2})?"

# 一行内：时间戳 [发言人] 内容
_ONE_LINE_BRACKET_RE = re.compile(
    rf"^\s*\[?({_TS})\]?\s*[\[【]\s*([^\]】]{{1,32}}?)\s*[\]】]\s*(.*)$"
)
# 一行内：时间戳 发言人 内容
_ONE_LINE_BARE_RE = re.compile(
    rf"^\s*\[?({_TS})\]?\s+([^\s:：\[\]【】]{{1,32}})\s+(.+)$"
)
# 独占一行：发言人 时间戳
_SPEAKER_TS_RE = re.compile(rf"^\s*([^\n]{{1,32}}?)\s+({_TS})\s*$")
# 独占一行：时间戳 发言人
_TS_SPEAKER_RE = re.compile(
    rf"^\s*\[?({_TS})\]?\s+([^\s:：\[\]【】]{{1,32}})\s*$"
)
# 发言行前的列表符号：• / · 可不带空格，- / * 要求后跟空白（避免误伤强调符号）
_LEADING_BULLET_RE = re.compile(r"^\s*(?:[•·]\s*|[-*]\s+)")

_SENTENCE_PUNCT = set("。！？；，,;!?")


def _looks_like_speaker(value: str) -> bool:
    speaker = (value or "").strip()
    return bool(speaker) and not any(ch in _SENTENCE_PUNCT for ch in speaker)


def _strip_leading_bullet(line: str) -> str:
    """去掉发言行前的列表符号，避免 ``• 发言者 1 52:00`` 把 ``•`` 算进发言人。"""
    return _LEADING_BULLET_RE.sub("", line, count=1)


def _detect_header(line: str) -> Optional[Tuple[str, str, str]]:
    """识别一条发言头，返回 ``(时间戳, 发言人, 行内内容)``。"""
    match = _ONE_LINE_BRACKET_RE.match(line)
    if match:
        return match.group(1).strip(), match.group(2).strip(), match.group(3).strip()

    match = _ONE_LINE_BARE_RE.match(line)
    if match and _looks_like_speaker(match.group(2)):
        return match.group(1).strip(), match.group(2).strip(), match.group(3).strip()

    match = _SPEAKER_TS_RE.match(line)
    if match and _looks_like_speaker(match.group(1)):
        return match.group(2).strip(), match.group(1).strip(), ""

    match = _TS_SPEAKER_RE.match(line)
    if match and _looks_like_speaker(match.group(2)):
        return match.group(1).strip(), match.group(2).strip(), ""

    return None


def timestamp_to_seconds(value: str) -> Optional[int]:
    """把 ``HH:MM:SS`` / ``MM:SS`` 转成秒；无法解析返回 None。"""
    text = (value or "").strip().strip("[]【】")
    if not text:
        return None
    # ASR 可能带毫秒：00:12:30.123
    text = re.split(r"[.,]", text, maxsplit=1)[0]
    parts = text.split(":")
    if len(parts) not in (2, 3):
        return None
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if any(number < 0 for number in numbers):
        return None
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]


def parse_transcript(transcript: str) -> List[TranscriptLine]:
    """把逐字稿解析成带时间戳的发言列表。

    无法识别到任何带时间戳的发言头时抛出 ``SectionSummaryInputError``。
    """
    raw_text = (transcript or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = raw_text.split("\n")

    headers: List[Tuple[int, str, str, str]] = []
    for line_index, line in enumerate(lines):
        detected = _detect_header(_strip_leading_bullet(line))
        if detected is not None:
            timestamp, speaker, inline_content = detected
            headers.append((line_index, timestamp, speaker, inline_content))

    if not headers:
        raise SectionSummaryInputError(
            "未识别到带时间戳的发言行；请提供类似 `张三 00:00:01` 或 "
            "`00:00:01 [张三] 内容` 的逐字稿。"
        )

    parsed: List[TranscriptLine] = []
    for position, (line_index, timestamp, speaker, inline_content) in enumerate(headers):
        next_index = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
        body_lines: List[str] = []
        if inline_content:
            body_lines.append(inline_content)
        body_lines.extend(lines[line_index + 1 : next_index])
        text = "\n".join(body_lines).strip()

        seconds = timestamp_to_seconds(timestamp)
        if seconds is None:
            continue

        parsed.append(
            TranscriptLine(
                index=len(parsed),
                timestamp=timestamp,
                seconds=seconds,
                speaker=speaker.strip(),
                text=text,
            )
        )

    if not parsed:
        raise SectionSummaryInputError("逐字稿中没有可用的时间戳。")
    return parsed


def format_transcript_for_prompt(lines: List[TranscriptLine]) -> str:
    """格式化为 Prompt 要求的 ``时间戳 [发言人] 内容`` 单行文本。"""
    formatted: List[str] = []
    for line in lines:
        speaker = re.sub(r"[\[\]【】]", "", line.speaker or "").strip() or "未知发言人"
        text = re.sub(r"\s+", " ", line.text or "").strip()
        entry = f"{line.timestamp} [{speaker}]"
        if text:
            entry = f"{entry} {text}"
        formatted.append(entry)
    return "\n".join(formatted)


__all__ = [
    "format_transcript_for_prompt",
    "parse_transcript",
    "timestamp_to_seconds",
]
