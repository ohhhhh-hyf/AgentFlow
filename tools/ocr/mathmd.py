"""把整理稿里的 $ / $$ 定界修成 KaTeX 能解析的形式。"""
from __future__ import annotations

import re

_FENCE_RE = re.compile(r"(```[\s\S]*?```|`[^`]+`)")
_TRIPLE_DOLLAR_RE = re.compile(r"\${3,}")


def normalize_markdown_math(text: str) -> str:
    """修 $...$$、$$...$、$$$，避免 KaTeX 'Can't use function $ in math mode'。"""
    raw = text or ""
    if "$" not in raw:
        return raw
    parts: list[str] = []
    last = 0
    for match in _FENCE_RE.finditer(raw):
        parts.append(_normalize_math_chunk(raw[last : match.start()]))
        parts.append(match.group(0))
        last = match.end()
    parts.append(_normalize_math_chunk(raw[last:]))
    return "".join(parts)


def _normalize_math_chunk(chunk: str) -> str:
    chunk = _TRIPLE_DOLLAR_RE.sub("$$", chunk)
    out: list[str] = []
    i = 0
    n = len(chunk)
    while i < n:
        if chunk[i] == "\\" and i + 1 < n:
            out.append(chunk[i : i + 2])
            i += 2
            continue
        if chunk.startswith("$$", i):
            closer = _find_math_close(chunk, i + 2, display=True)
            if closer is None:
                out.append("\\$\\$" + chunk[i + 2 :])
                break
            body, end = closer
            out.append("$$" + body + "$$")
            i = end
            continue
        if chunk[i] == "$":
            closer = _find_math_close(chunk, i + 1, display=False)
            if closer is None:
                out.append("\\$" + chunk[i + 1 :])
                break
            body, end = closer
            out.append("$" + body + "$")
            i = end
            continue
        out.append(chunk[i])
        i += 1
    return "".join(out)


def _find_math_close(chunk: str, start: int, *, display: bool) -> tuple[str, int] | None:
    """找到公式结束。display 允许误写成单 $ 收尾；inline 允许误写成 $$ 收尾。"""
    j = start
    n = len(chunk)
    while j < n:
        if chunk[j] == "\\" and j + 1 < n:
            j += 2
            continue
        if not display and chunk[j] == "\n" and j + 1 < n and chunk[j + 1] == "\n":
            return None
        if display and chunk.startswith("$$", j):
            return chunk[start:j], j + 2
        if display and chunk[j] == "$":
            return chunk[start:j], j + 1
        if not display and chunk.startswith("$$", j):
            return chunk[start:j], j + 2
        if not display and chunk[j] == "$":
            return chunk[start:j], j + 1
        j += 1
    return None


__all__ = ["normalize_markdown_math"]
