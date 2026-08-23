"""OCR 笔记还原：图片 → 结构化 Markdown（可入库 knowledge library）。

流程（第一版，可迭代）：
1. 预处理：打开图片（多图=多页）、转 RGB、可选增强
2. 文字识别：PaddleOCR（中文，RapidOCR 兜底）→ 带坐标的文本行
3. 版面识别：根据 bbox / 字高 / 留白 / 编号模式标记标题候选和层级提示
4. 公式识别：LaTeX-OCR（pix2tex）对公式候选行裁剪 → ``$$ LaTeX $$``
5. LLM 重构：DeepSeek 把 OCR 碎片整理为结构化 Markdown
   （推断标题层级、标注 **重点**、整理表格、合并断行、去 OCR 噪声）

依赖均懒加载：缺 PaddleOCR / RapidOCR / LaTeX-OCR / LLM 时逐级降级（不崩）。

对外接口：
- ``ocr_image_to_markdown(image_path, use_llm=True) -> str``
- ``ocr_images_to_markdown(paths, output=None, use_llm=True) -> str``
- CLI：``python -m tools.ocr.cli --input 图.png --output out.md``
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from .adapter import raw_text_from_lines, recognize_image, temporary_ocr_engine  # noqa: E402
from .layout import ocr_image_lines  # noqa: E402
from .reconstruct import reconstruct_markdown, review_markdown  # noqa: E402


def _clean_ocr_text(value) -> str:
    if isinstance(value, bytes):
        for encoding in ("utf-8", "gb18030", "latin1"):
            try:
                return value.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        return value.decode("utf-8", errors="replace").strip()
    return str(value or "").strip()


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
    """多张图片（= 多页笔记）→ 合并 Markdown（页间分节）。"""
    from pathlib import Path

    blocks: list[str] = []
    for i, path in enumerate(paths, start=1):
        blocks.append(
            f"<!-- 第 {i} 页：{Path(str(path)).name} -->\n"
            f"{ocr_image_to_markdown(str(path), use_llm=use_llm)}"
        )
    text = "\n\n".join(blocks)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text, encoding="utf-8")
    return text


_temporary_ocr_engine = temporary_ocr_engine


def server_ocr_image_compare(image_path: str) -> tuple[str, str, str]:
    """单张图片 → 服务器 OCR 原文 / 无 LLM Markdown / LLM Markdown。"""
    raw_text, no_llm_md, llm_md, _reviewed_md, _review_notes = server_ocr_image_recognize(image_path)
    return raw_text, no_llm_md, llm_md


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
    "server_ocr_image_compare",
    "server_ocr_image_recognize",
]
