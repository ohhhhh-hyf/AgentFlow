"""OCR 笔记还原：图片 → 结构化 Markdown（可入库 knowledge library）。

流程：
1. 文字识别：三种引擎主进程直调（serverocr / paddleocr / rapidocr，
   由 ``OCR_ENGINE`` 分派，见 engines.py）→ 带坐标的文本行
2. 版面识别：根据 bbox / 字高 / 留白 / 编号模式标记标题候选
3. LLM 重构 + 审校：整理为结构化 Markdown

对外接口：
- ``ocr_image_to_markdown(image_path, use_llm=True) -> str``
"""
from __future__ import annotations

from .layout import ocr_image_lines  # noqa: E402
from .reconstruct import reconstruct_markdown  # noqa: E402


def ocr_image_to_markdown(image_path: str, use_llm: bool = True) -> str:
    """单张图片 → 结构化 Markdown 文本。"""
    from pathlib import Path

    path = Path(image_path)
    if not path.is_file():
        raise ValueError(f"图片不存在：{image_path}")
    lines = ocr_image_lines(str(path))
    if not lines:
        return "（OCR 未识别到文字）"
    if not use_llm:
        return _lines_to_text(lines)
    return reconstruct_markdown(lines)


def _lines_to_text(lines: list[dict]) -> str:
    """无 LLM 时：按坐标顺序拼纯文本。"""
    from .adapter import _clean_ocr_text

    parts: list[str] = []
    for item in lines:
        text = _clean_ocr_text(item.get("text"))
        if text:
            parts.append(text)
    return "\n".join(parts)


__all__ = [
    "ocr_image_to_markdown",
]
