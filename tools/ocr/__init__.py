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


def _lines_to_text(lines: list[dict]) -> str:
    """无 LLM 时：按坐标顺序拼纯文本。"""
    return "\n".join(
        item.get("formula") or item.get("text") or ""
        for item in lines
        if (item.get("text") or item.get("formula"))
    )


__all__ = ["ocr_image_to_markdown", "ocr_images_to_markdown"]
