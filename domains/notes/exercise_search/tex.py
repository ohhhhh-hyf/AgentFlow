"""把题库 <tex data-latex> / LaTeX 源码收成可读数学文本。"""
from __future__ import annotations

import html
import re

_TEX_TAG = re.compile(
    r'<tex\b[^>]*data-latex=(["\'])(.*?)\1[^>]*>.*?</tex>',
    re.I | re.S,
)
_CMD = [
    (r"\\displaystyle", ""),
    (r"\\textstyle", ""),
    (r"\\left", ""),
    (r"\\right", ""),
    (r"\\middle", ""),
    (r"\\quad", " "),
    (r"\\qquad", " "),
    (r"\\,", " "),
    (r"\\;", " "),
    (r"\\:", " "),
    (r"\\!", ""),
    (r"\\cdot", "·"),
    (r"\\times", "×"),
    (r"\\div", "÷"),
    (r"\\pm", "±"),
    (r"\\mp", "∓"),
    (r"\\neq", "≠"),
    (r"\\ne\b", "≠"),
    (r"\\geq", "≥"),
    (r"\\geqq", "≥"),
    (r"\\ge\b", "≥"),
    (r"\\leq", "≤"),
    (r"\\leqq", "≤"),
    (r"\\le\b", "≤"),
    (r"\\geqslant", "≥"),
    (r"\\leqslant", "≤"),
    (r"\\gt\b", ">"),
    (r"\\lt\b", "<"),
    (r"\\approx", "≈"),
    (r"\\equiv", "≡"),
    (r"\\sim", "∼"),
    (r"\\infty", "∞"),
    (r"\\in\b", "∈"),
    (r"\\notin", "∉"),
    (r"\\subset", "⊂"),
    (r"\\subseteq", "⊆"),
    (r"\\cup", "∪"),
    (r"\\cap", "∩"),
    (r"\\emptyset", "∅"),
    (r"\\varnothing", "∅"),
    (r"\\forall", "∀"),
    (r"\\exists", "∃"),
    (r"\\neg", "¬"),
    (r"\\rightarrow", "→"),
    (r"\\to\b", "→"),
    (r"\\Rightarrow", "⇒"),
    (r"\\Leftarrow", "⇐"),
    (r"\\Leftrightarrow", "⇔"),
    (r"\\partial", "∂"),
    (r"\\circ", "∘"),
    (r"\\dots", "…"),
    (r"\\cdots", "⋯"),
    (r"\\ldots", "…"),
    (r"\\alpha", "α"),
    (r"\\beta", "β"),
    (r"\\gamma", "γ"),
    (r"\\delta", "δ"),
    (r"\\epsilon", "ε"),
    (r"\\varepsilon", "ε"),
    (r"\\theta", "θ"),
    (r"\\lambda", "λ"),
    (r"\\mu", "μ"),
    (r"\\pi", "π"),
    (r"\\sigma", "σ"),
    (r"\\phi", "φ"),
    (r"\\varphi", "φ"),
    (r"\\omega", "ω"),
    (r"\\Delta", "Δ"),
    (r"\\Omega", "Ω"),
    (r"\\mathbb\{R\}", "R"),
    (r"\\mathbf\{R\}", "R"),
    (r"\\mathrm\{R\}", "R"),
    (r"\\mathbb\{Z\}", "Z"),
    (r"\\mathbb\{N\}", "N"),
    (r"\\mathbb\{Q\}", "Q"),
    (r"\\mathbb\{C\}", "C"),
]
_SUP = re.compile(r"\^\{([^{}]+)\}|\^([A-Za-z0-9+\-])")
_SUB = re.compile(r"_\{([^{}]+)\}|_([A-Za-z0-9+\-])")
_GROUP = re.compile(r"(?<![A-Za-z\\])\{([^{}]*)\}")
_SUP_MAP = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
_SUB_MAP = str.maketrans("0123456789+-=()aeox", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓ")


def _skip_space(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _brace_arg(text: str, start: int) -> tuple[str, int] | None:
    start = _skip_space(text, start)
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index], index + 1
    return None


def _rewrite_fracs(text: str) -> str:
    out: list[str] = []
    pos = 0
    for match in re.finditer(r"\\(?:d|t)?frac\b", text):
        first = _brace_arg(text, match.end())
        if first is None:
            continue
        second = _brace_arg(text, first[1])
        if second is None:
            continue
        out.append(text[pos : match.start()])
        out.append(_pretty_frac(first[0], second[0]))
        pos = second[1]
    out.append(text[pos:])
    return "".join(out)


def _rewrite_sqrts(text: str) -> str:
    out: list[str] = []
    pos = 0
    for match in re.finditer(r"\\sqrt\b", text):
        cursor = _skip_space(text, match.end())
        idx = ""
        if cursor < len(text) and text[cursor] == "[":
            close = text.find("]", cursor)
            if close < 0:
                continue
            idx = text[cursor + 1 : close]
            cursor = close + 1
        body = _brace_arg(text, cursor)
        if body is None:
            continue
        out.append(text[pos : match.start()])
        out.append(f"{idx}√({body[0]})" if idx else f"√({body[0]})")
        pos = body[1]
    out.append(text[pos:])
    return "".join(out)


def _rewrite_text(text: str) -> str:
    out: list[str] = []
    pos = 0
    for match in re.finditer(
        r"\\(?:text|mathrm|mathbf|boldsymbol|operatorname)\b", text
    ):
        body = _brace_arg(text, match.end())
        if body is None:
            continue
        out.append(text[pos : match.start()])
        out.append(body[0])
        pos = body[1]
    out.append(text[pos:])
    return "".join(out)


def pretty_latex(raw: object) -> str:
    text = html.unescape(str(raw or "")).replace("\n", " ")
    if not text.strip():
        return ""
    prev = None
    while prev != text:
        prev = text
        text = _rewrite_text(text)
        text = _rewrite_sqrts(text)
        text = _rewrite_fracs(text)
        text = _SUP.sub(lambda m: _raise(m.group(1) or m.group(2)), text)
        text = _SUB.sub(lambda m: _lower(m.group(1) or m.group(2)), text)
        for pattern, repl in _CMD:
            text = re.sub(pattern, repl, text)
        text = _GROUP.sub(r"\1", text)
    text = re.sub(r"\\([A-Za-z]+)", r"\1", text)
    text = text.replace("\\{", "{").replace("\\}", "}").replace("\\", "")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.)\]}])", r"\1", text)
    text = re.sub(r"([([/{])\s+", r"\1", text)
    return text.strip()


def replace_tex_html(raw: object) -> str:
    """把 HTML 里的 <tex data-latex> 换成可读公式。"""
    text = str(raw or "")
    return _TEX_TAG.sub(
        lambda m: pretty_latex(m.group(2)),
        text,
    )


def _pretty_frac(num: str, den: str) -> str:
    num = num.strip()
    den = den.strip()
    if _needs_paren(num):
        num = f"({num})"
    if _needs_paren(den):
        den = f"({den})"
    return f"{num}/{den}"


def _needs_paren(part: str) -> bool:
    return bool(re.search(r"[+\- =<>≤≥≠]", part)) and not (
        part.startswith("(") and part.endswith(")")
    )


def _raise(part: str) -> str:
    mapped = part.translate(_SUP_MAP)
    if mapped != part or any(ch not in "0123456789+-=()n" for ch in part):
        if all(ch in "0123456789+-=()n" for ch in part):
            return mapped
        return f"^({part})" if len(part) > 1 else f"^{part}"
    return mapped


def _lower(part: str) -> str:
    mapped = part.translate(_SUB_MAP)
    if mapped != part or any(ch not in "0123456789+-=()aeox" for ch in part):
        if all(ch in "0123456789+-=()aeox" for ch in part):
            return mapped
        return f"_({part})" if len(part) > 1 else f"_{part}"
    return mapped


__all__ = ["pretty_latex", "replace_tex_html"]
