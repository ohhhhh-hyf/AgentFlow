"""domains.meeting.tasks.agenda_minutes.ocr —— 议程单专用轻量 OCR。"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


def pad_image_bottom(image_path: str, pad_px: int = 100) -> str | None:
    """在图片底部添加白色填充，防止 OCR 检测模型边缘截断导致末尾行丢失。"""
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            w, h = img.size
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            new_img = Image.new("RGB", (w, h + pad_px), (255, 255, 255))
            new_img.paste(img, (0, 0))

            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            new_img.save(tmp_path)
            return tmp_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("pad_image_bottom failed: %s", exc)
        return None


def ocr_agenda_images(
    image_paths: Sequence[Path | str],
    candidate_speakers: list[str] | set[str] | None = None,
) -> str:
    """议程单专用轻量 OCR：单线程直调，单图单实例，禁用上下边缘去噪裁剪，走专用议程提纯 Prompt。"""
    if not image_paths:
        return ""

    try:
        from domains.meeting.tasks.agenda_minutes.agenda_extractor import reconstruct_agenda_markdown
    except ImportError:
        from domains.meeting.tasks.agenda_minutes.agenda_extractor import reconstruct_agenda_markdown

    try:
        from infra.ocr.engines import ocr_engine_label
        from infra.ocr.layout import ocr_image_lines
        from infra.ocr.levels.light import ocr_log
    except ImportError:
        from infra.ocr.engines import ocr_engine_label
        from infra.ocr.layout import ocr_image_lines
        from infra.ocr.levels.light import ocr_log

    engine = ocr_engine_label()
    total = len(image_paths)
    ocr_log(f"agenda_ocr start engine={engine} images={total} mode=single_stream")
    parts: list[str] = []
    for idx, raw_path in enumerate(image_paths, 1):
        path = Path(raw_path)
        padded_path: str | None = None
        try:
            padded_path = pad_image_bottom(str(path), pad_px=100)
            actual_path = padded_path or str(path)
            lines = ocr_image_lines(actual_path, enable_page_chrome=False, for_agenda=True) or []
            ocr_log(f"agenda_ocr item ok {idx}/{total} lines={len(lines)} file={path.name} padded={padded_path is not None}")
            if lines:
                md = reconstruct_agenda_markdown(lines, candidate_speakers=candidate_speakers).strip()
                if md:
                    parts.append(md)
        except Exception as exc:  # noqa: BLE001
            ocr_log(f"agenda_ocr item fail {idx}/{total} file={path.name} err={exc}")
            parts.append(f"（议程单图片 {path.name} OCR 失败：{exc}）")
        finally:
            if padded_path:
                try:
                    os.unlink(padded_path)
                except OSError:
                    pass

    result = "\n\n".join(part for part in parts if part).strip()
    ocr_log(f"agenda_ocr done total={total} chars={len(result)}")
    return result
