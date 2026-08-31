"""把整理稿里的 $ / $$ 定界修成 KaTeX 能解析的形式，并修复不成对的 \\left/\\right。"""
from __future__ import annotations

import re

_FENCE_RE = re.compile(r"(```[\s\S]*?```|`[^`]+`)")
_TRIPLE_DOLLAR_RE = re.compile(r"\${3,}")

# 大分隔符命令（KaTeX 报「Missing or unrecognized delimiter for \right」的根因：
# 公式体内 \left 与 \right 不成对——OCR 截断或 LLM 生成不完整）
_LEFT_CMD_RE = re.compile(r"\\left(?![a-zA-Z])")
_RIGHT_CMD_RE = re.compile(r"\\right(?![a-zA-Z])")
_LEFT_DELIM_RE = re.compile(r"\\[a-zA-Z]+|\S")  # \left 后的分隔符（命令或单字符）


def _fix_left_right_math(body: str) -> str:
    """修复公式体内不成对的 \\left/\\right。

    - 孤立的 \\rightX（前面没有配对的 \\left）→ 在它前面补 \\left.（隐形分隔符）
    - 孤立的 \\leftX（后面没有配对的 \\right）→ 在分隔符后补 \\right.
    补 \\left. / \\right. 不改变显示，只让 KaTeX 能解析。
    """
    toks: list[tuple[int, str]] = []
    for m in _LEFT_CMD_RE.finditer(body):
        toks.append((m.start(), "L"))
    for m in _RIGHT_CMD_RE.finditer(body):
        toks.append((m.start(), "R"))
    if not toks:
        return body
    toks.sort(key=lambda item: item[0])
    stack: list[int] = []
    orphan_right: list[int] = []  # 孤立 \right 的位置
    for pos, kind in toks:
        if kind == "L":
            stack.append(pos)
        elif stack:
            stack.pop()
        else:
            orphan_right.append(pos)
    orphan_left = stack  # 孤立 \left 的位置

    if not orphan_right and not orphan_left:
        return body
    out = body
    # 孤立 \rightX → 前面插 \left.：\left.\rightX
    for pos in sorted(orphan_right, reverse=True):
        out = out[:pos] + "\\left." + out[pos:]
    # 孤立 \leftX → 分隔符后插 \right.：\leftX\right.
    for pos in sorted(orphan_left, reverse=True):
        m = _LEFT_CMD_RE.search(out, pos)
        if not m:
            continue
        after = m.end()
        dm = _LEFT_DELIM_RE.match(out, after)
        if dm:
            after = dm.end()
        out = out[:after] + "\\right." + out[after:]
    return out


def normalize_markdown_math(text: str) -> str:
    """修 $...$$、$$...$、$$$ 与不成对的 \\left/\\right，避免 KaTeX 解析报错。"""
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
            out.append("$$" + _fix_left_right_math(body) + "$$")
            i = end
            continue
        if chunk[i] == "$":
            closer = _find_math_close(chunk, i + 1, display=False)
            if closer is None:
                out.append("\\$" + chunk[i + 1 :])
                break
            body, end = closer
            out.append("$" + _fix_left_right_math(body) + "$")
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
