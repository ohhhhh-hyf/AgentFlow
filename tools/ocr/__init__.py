"""OCR 笔记还原：图片 → 结构化 Markdown（可入库 knowledge library）。

流程：
1. 文字识别：服务器 OCR（主进程）或 RapidOCR/PaddleOCR 子进程 → 带坐标的文本行
2. 版面识别：根据 bbox / 字高 / 留白 / 编号模式标记标题候选
3. LLM 重构 + 审校：整理为结构化 Markdown

对外接口：
- ``ocr_image_to_markdown(image_path, use_llm=True) -> str``
- ``ocr_images_to_markdown(paths, output=None, use_llm=True) -> str``
- CLI：``python -m tools.ocr.cli --input 图.png --output out.md``
"""
from __future__ import annotations

from .adapter import _clean_ocr_text, raw_text_from_lines, recognize_image  # noqa: E402
from .layout import ocr_image_lines  # noqa: E402
from .reconstruct import reconstruct_markdown, review_markdown  # noqa: E402


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


def ocr_images_to_markdown(
    paths: list[str] | tuple[str, ...],
    output: str | None = None,
    use_llm: bool = True,
) -> str:
    """多张图片（= 多页笔记）→ 合并 Markdown。"""
    from pathlib import Path

    blocks: list[str] = []
    for path in paths:
        body = ocr_image_to_markdown(str(path), use_llm=use_llm).strip()
        if body:
            blocks.append(body)
    text = "\n\n".join(blocks)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text, encoding="utf-8")
    return text


def server_ocr_image_recognize(image_path: str) -> tuple[str, str, str, str, str]:
    """单张图片 → 原文 / 无 LLM Markdown / LLM 初稿 / 审校 Markdown / 审校说明。"""
    from pathlib import Path

    path = Path(image_path)
    if not path.is_file():
        raise ValueError(f"图片不存在：{image_path}")

    payload = recognize_image(str(path))
    lines = list(payload.get("lines") or [])
    raw_text = raw_text_from_lines(lines) or "（OCR 未识别到文字）"

    if not lines:
        empty = "（OCR 未识别到文字）"
        return raw_text, empty, empty, empty, "未识别到可审校内容。"
    no_llm_md = _lines_to_text(lines)
    llm_md = reconstruct_markdown(lines)
    reviewed_md, review_notes = review_markdown(llm_md, lines)
    return raw_text, no_llm_md, llm_md, reviewed_md, review_notes


def _lines_to_text(lines: list[dict]) -> str:
    """无 LLM 时：按坐标顺序拼纯文本。"""
    parts: list[str] = []
    for item in lines:
        text = item.get("formula") or _clean_ocr_text(item.get("text"))
        if text:
            parts.append(text)
    return "\n".join(parts)


__all__ = [
    "ocr_image_to_markdown",
    "ocr_images_to_markdown",
    "recognize_image",
    "server_ocr_image_recognize",
]
