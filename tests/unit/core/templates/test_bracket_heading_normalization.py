"""门禁前确定性归一化：`## [栏名]` → `## 栏名`。"""
from __future__ import annotations

from core.execution.hard_execution import (
    enforce_render_output,
    gate_render_output,
    strip_bracketed_column_headings,
)

_TEMPLATE = """## [沟通背景]
[单段概括]

## [核心信息]
[事实与数据]
"""


def test_strip_bracketed_headings_only_for_template_columns() -> None:
    text = (
        "## [沟通背景]\n"
        "背景说明，[待确认] 事项保留。\n"
        "- [ ] 待办保留\n"
        "## [核心信息]\n"
        "核心内容。\n"
        "## [自定义栏]\n"
        "不命中模板，保持不变。\n"
    )
    normalized, count = strip_bracketed_column_headings(text, _TEMPLATE)

    assert count == 2
    assert "## 沟通背景" in normalized
    assert "## 核心信息" in normalized
    assert "## [自定义栏]" in normalized
    assert "[待确认]" in normalized
    assert "- [ ] 待办保留" in normalized


def test_enforce_render_output_normalizes_before_validation() -> None:
    output = "## [沟通背景]\n背景内容。\n\n## [核心信息]\n核心内容。\n"
    text, notes, issues = enforce_render_output(_TEMPLATE, output)

    assert "## 沟通背景" in text
    assert "## 核心信息" in text
    assert any("已去除栏目标题方括号 2 处" in n for n in notes)
    assert not any("残留占位符" in i for i in issues)


def test_gate_passes_after_heading_normalization() -> None:
    output = "## [沟通背景]\n背景内容。\n\n## [核心信息]\n核心内容。\n"
    result = gate_render_output(_TEMPLATE, output)

    assert result["gate_ok"] is True
    assert result["hard_issues"] == []
    assert "## 沟通背景" in result["text"]


def test_unknown_bracketed_heading_is_left_untouched() -> None:
    output = "## [非模板栏]\n内容。\n"
    normalized, count = strip_bracketed_column_headings(output, _TEMPLATE)

    assert count == 0
    assert normalized == output
