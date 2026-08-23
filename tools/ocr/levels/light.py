from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tools.memory.store import safe_id
from tools.ocr import server_ocr_image_recognize


@dataclass(frozen=True)
class LightOcrResult:
    """Light OCR result saved for later knowledge ingestion."""

    raw_text: str
    reviewed_markdown: str
    raw_path: Path
    reviewed_path: Path

    @property
    def files(self) -> list[str]:
        return [str(self.raw_path), str(self.reviewed_path)]


def _safe_stem(image_path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", image_path.stem).strip("._") or "image"


def run_light_ocr(
    image_path: str | Path,
    *,
    user_id: str,
    subject: str,
    project_root: str | Path,
) -> LightOcrResult:
    """Run the current Light pipeline: server OCR -> LLM draft/review -> txt + md."""
    path = Path(image_path)
    if not path.is_file():
        raise ValueError(f"图片不存在：{path}")

    raw_txt, _no_llm_md, _llm_md, reviewed_md, _review_notes = server_ocr_image_recognize(str(path))
    return save_light_ocr_outputs(
        path,
        raw_text=raw_txt,
        reviewed_markdown=reviewed_md,
        user_id=user_id,
        subject=subject,
        project_root=project_root,
    )


def save_light_ocr_outputs(
    image_path: str | Path,
    *,
    raw_text: str,
    reviewed_markdown: str,
    user_id: str,
    subject: str,
    project_root: str | Path,
) -> LightOcrResult:
    """Save Light-compatible OCR outputs."""
    path = Path(image_path)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    base_dir = (
        Path(project_root)
        / "data"
        / safe_id(user_id)
        / "ocr"
        / safe_id(subject)
    )
    txt_dir = base_dir / "txt"
    md_dir = base_dir / "md"
    txt_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)

    stem = _safe_stem(path)
    raw_path = txt_dir / f"{stem}_{stamp}_ocr.txt"
    reviewed_path = md_dir / f"{stem}_{stamp}_llmv2.md"
    raw_path.write_text(raw_text, encoding="utf-8")
    reviewed_path.write_text(reviewed_markdown, encoding="utf-8")

    return LightOcrResult(
        raw_text=raw_text,
        reviewed_markdown=reviewed_markdown,
        raw_path=raw_path,
        reviewed_path=reviewed_path,
    )
