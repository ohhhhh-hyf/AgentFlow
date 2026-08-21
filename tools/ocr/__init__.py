"""OCR 笔记还原：图片 → 结构化 Markdown（可入库 knowledge library）。

流程（第一版，可迭代）：
1. 预处理：打开图片（多图=多页）、转 RGB、可选增强
2. 文字识别：PaddleOCR（中文，RapidOCR 兜底）→ 带坐标的文本行
3. 版面识别：根据 bbox / 字高 / 留白 / 编号模式标记标题候选和层级提示
4. 图示检测：遮掉 OCR 文字框后检测大块非文字墨迹，记录位置和粗分类（不理解图内容）
5. 公式识别：LaTeX-OCR（pix2tex）对公式候选行裁剪 → ``$$ LaTeX $$``
6. LLM 重构：DeepSeek 把 OCR 碎片整理为结构化 Markdown
   （推断标题层级、标注 **重点**、整理表格、合并断行、去 OCR 噪声）

依赖均懒加载：缺 PaddleOCR / RapidOCR / LaTeX-OCR / LLM 时逐级降级（不崩）。

对外接口：
- ``ocr_image_to_markdown(image_path, use_llm=True) -> str``
- ``ocr_images_to_markdown(paths, output=None, use_llm=True) -> str``
- CLI：``python -m tools.ocr.cli --input 图.png --output out.md``
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager

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


@contextmanager
def _temporary_ocr_engine(engine: str):
    old_engine = os.environ.get("OCR_ENGINE")
    os.environ["OCR_ENGINE"] = engine
    try:
        yield
    finally:
        if old_engine is None:
            os.environ.pop("OCR_ENGINE", None)
        else:
            os.environ["OCR_ENGINE"] = old_engine


def server_ocr_image_compare(image_path: str) -> tuple[str, str, str]:
    """单张图片 → 服务器 OCR 原文 / 无 LLM Markdown / LLM Markdown。"""
    from pathlib import Path

    path = Path(image_path)
    if not path.is_file():
        raise ValueError(f"图片不存在：{image_path}")

    from .server_ocr import ocr_image

    raw_payload = ocr_image(str(path))
    raw_lines = [
        str(item.get("text") or "").strip()
        for item in (raw_payload.get("lines") or [])
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    raw_text = "\n".join(raw_lines).strip() or "（服务器 OCR 未识别到文字）"

    with _temporary_ocr_engine("serverocr"):
        lines = ocr_image_lines(str(path))
    if not lines and raw_payload.get("lines"):
        lines = list(raw_payload.get("lines") or [])

    if not lines:
        return raw_text, "（OCR 未识别到文字）", "（OCR 未识别到文字）"
    no_llm_md = _lines_to_text(lines)
    llm_md = reconstruct_markdown(lines)
    return raw_text, no_llm_md, llm_md


def _lines_to_text(lines: list[dict]) -> str:
    """无 LLM 时：按坐标顺序拼纯文本。"""
    parts: list[str] = []
    for item in lines:
        visual = item.get("visual_region") or {}
        if visual:
            label = visual.get("label") or "疑似图示"
            kind = visual.get("type") or "diagram"
            parts.append(f"<!-- 图示: {label}; type={kind}; bbox={item.get('bbox') or []} -->")
            continue
        text = item.get("formula") or item.get("text") or ""
        if text:
            parts.append(text)
    return "\n".join(parts)


__all__ = ["ocr_image_to_markdown", "ocr_images_to_markdown", "server_ocr_image_compare"]
