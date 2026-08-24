from tools.ocr.mathmd import normalize_markdown_math


def test_inline_closed_with_double_dollar():
    raw = r"本征值 $\hat{A}|\psi\rangle=\lambda|\psi\rangle$$，称 $|\psi\rangle$ 为态矢"
    out = normalize_markdown_math(raw)
    assert r"$\hat{A}|\psi\rangle=\lambda|\psi\rangle$" in out
    assert r"$|\psi\rangle$" in out
    assert r"\rangle$$，称" not in out


def test_display_closed_with_single_dollar():
    raw = r"$$\lambda|\psi\rangle$ 是本征值"
    out = normalize_markdown_math(raw)
    assert r"$$\lambda|\psi\rangle$$" in out


def test_keeps_valid_inline_and_display():
    raw = "行内 $E=mc^2$ 和独立\n\n$$\\int f(x) dx$$\n\n结束"
    assert normalize_markdown_math(raw) == raw


def test_collapses_triple_dollar():
    assert normalize_markdown_math("$$$E=mc^2$$$") == "$$E=mc^2$$"


def test_skips_code_fence():
    raw = "正文 $a$$ 和\n```\n$a$$\n```\n"
    out = normalize_markdown_math(raw)
    assert "正文 $a$ 和" in out
    assert "```\n$a$$\n```" in out
