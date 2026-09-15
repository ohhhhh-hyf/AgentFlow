"""把整理稿里的 $ / $$ 定界修成 KaTeX 能解析的形式，并修复不成对的 \\left/\\right。

同时删掉模型偶发写进正文的「渲染器/程序报错串」（如 KaTeX 的 ParseError）：
整理提示词要求模型处理公式定界，它遇到修不好的公式时偶尔会把渲染器的报错文案
当成说明写出来，例如::

    角向方程：sinθ…{$ ParseError: KaTeX parse error: Expected '}', got 'EOF' at end of input: ∂^{2
"""
from __future__ import annotations

import re

_FENCE_RE = re.compile(r"(```[\s\S]*?```|`[^`]+`)")
_TRIPLE_DOLLAR_RE = re.compile(r"\${3,}")

# ── 模型自述噪声：渲染器/程序报错文案 ────────────────────────
# 只匹配这几类带明确特征的报错形态，不误删正文里正常讨论 KaTeX/LaTeX 的句子
# （「本页公式用 KaTeX 渲染」不含 parse error，也不会命中；编程笔记里
#  「ParseError: 具体内容」这类**带内容**的示例同样保留 —— 只有行尾孤立的
#  `ParseError:` 残渣才会被删，那正是抄报错抄一半留下的痕迹）。
_PROGRAM_NOISE_RES = (
    # ParseError: KaTeX parse error: …（模型把整条报错抄进正文的最常见形态）
    re.compile(r"[ \t]*\bParseError:\s*(?:KaTeX\s+)?parse error:[^\n]*"),
    # KaTeX parse error: …（不带 ParseError 前缀）
    re.compile(r"[ \t]*\bKaTeX parse error:[^\n]*"),
    # 单行剩个孤立的 ParseError:（上面两条删完后的残渣）
    re.compile(r"[ \t]*\bParseError:[ \t]*$", re.M),
    # KaTeX 另两种典型文案
    re.compile(r"[ \t]*Expected '[^'\n]*', got 'EOF' at end of input:[^\n]*"),
    # 这条报错文案止于 \right 本身，不吞掉后面的正文
    re.compile(r"[ \t]*Missing or unrecognized delimiter for \\right[ \t]*"),
)
_NOISE_HINTS = ("ParseError", "KaTeX", "at end of input", "unrecognized delimiter")


def strip_program_noise(text: str) -> str:
    """删掉模型写进正文的渲染器/程序报错串；整行只剩报错时整行删除。"""
    raw = text or ""
    if not any(hint in raw for hint in _NOISE_HINTS):
        return raw                      # 快速路径：绝大多数文本直接返回
    out: list[str] = []
    for line in raw.splitlines():
        cleaned = line
        for pattern in _PROGRAM_NOISE_RES:
            cleaned = pattern.sub("", cleaned)
        if cleaned != line:
            if not cleaned.strip():
                continue                # 整行都是报错 → 整行删掉
            cleaned = cleaned.rstrip()
        out.append(cleaned)
    joined = "\n".join(out)
    if joined != raw:
        joined = re.sub(r"\n{3,}", "\n\n", joined)   # 删行留下的多余空行收敛
    return joined

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
    """OCR / LLM 文本的统一收尾：先删模型自述的报错串，再修 $ 定界与 \\left/\\right 配对。

    顺序有意如此 —— 报错串常出现在公式中间（``…{$ ParseError: KaTeX…``），
    先删它才会留下悬空的 ``$``，正好由后一步转义成字面 ``\\$``。
    """
    raw = strip_program_noise(text or "")
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


__all__ = ["normalize_markdown_math", "strip_program_noise"]
