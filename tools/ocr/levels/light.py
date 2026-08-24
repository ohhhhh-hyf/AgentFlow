from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tools.memory.store import safe_id
from tools.ocr import server_ocr_image_recognize

_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


@dataclass(frozen=True)
class LightOcrResult:
    """Light OCR result saved for later knowledge ingestion."""

    raw_text: str
    reviewed_markdown: str
    reviewed_path: Path | None = None

    @property
    def files(self) -> list[str]:
        return [str(self.reviewed_path)] if self.reviewed_path else []


def _safe_stem(image_path: Path | str) -> str:
    raw = image_path.stem if isinstance(image_path, Path) else Path(str(image_path)).stem
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw).strip(" .") or "image"
    if stem.upper() in _WINDOWS_RESERVED:
        stem = f"{stem}_"
    return stem


_VERSION_STEM_RE = re.compile(r"^v(\d+)$", re.I)


def next_batch_version_stem(
    user_id: str,
    subject: str,
    project_root: str | Path,
) -> str:
    """同一 user+subject 下，多图合并稿按 v1、v2… 递增。"""
    root = Path(project_root)
    uid = safe_id(user_id)
    subj = safe_id(subject)
    folders = [
        root / "data" / uid / "ocr" / subj / "md",
        root / "data" / uid / "ocr" / subj / "txt",
        root / "data" / uid / "knowledge" / "catalogs",
    ]
    highest = 0
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file():
                continue
            stem = path.stem
            if stem.endswith("_meta"):
                stem = stem[: -len("_meta")]
            match = _VERSION_STEM_RE.match(stem)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"v{highest + 1}"


_PAGE_COMMENT_RE = re.compile(r"^<!--\s*第\s*\d+\s*页[:：].*?-->\s*", re.M)


def _strip_page_comments(text: str) -> str:
    return _PAGE_COMMENT_RE.sub("", text or "").strip()


def combine_ocr_pages(pages: list[dict[str, str]], *, key: str) -> str:
    blocks: list[str] = []
    for page in pages:
        body = _strip_page_comments(str(page.get(key) or ""))
        if body:
            blocks.append(body)
    return "\n\n".join(blocks)


def save_combined_ocr_outputs(
    pages: list[dict[str, str]],
    *,
    user_id: str,
    subject: str,
    project_root: str | Path,
    output_stem: str | None = None,
) -> LightOcrResult:
    """把并行识别的多页按上传顺序拼成一份 md，便于一次入库。"""
    stem = output_stem or next_batch_version_stem(user_id, subject, project_root)
    return save_light_ocr_outputs(
        Path(stem),
        raw_text=combine_ocr_pages(pages, key="raw_text"),
        reviewed_markdown=combine_ocr_pages(pages, key="reviewed_markdown"),
        user_id=user_id,
        subject=subject,
        project_root=project_root,
    )


def run_light_ocr(
    image_path: str | Path,
    *,
    user_id: str,
    subject: str,
    project_root: str | Path,
    output_stem: str | None = None,
    persist: bool = True,
) -> LightOcrResult:
    """Run the current Light pipeline: server OCR -> LLM draft/review -> md."""
    path = Path(image_path)
    if not path.is_file():
        raise ValueError(f"图片不存在：{path}")

    raw_txt, _no_llm_md, _llm_md, reviewed_md, _review_notes = server_ocr_image_recognize(str(path))
    if not persist:
        return LightOcrResult(raw_text=raw_txt, reviewed_markdown=reviewed_md)
    return save_light_ocr_outputs(
        Path(output_stem) if output_stem else path,
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

    base_dir = (
        Path(project_root)
        / "data"
        / safe_id(user_id)
        / "ocr"
        / safe_id(subject)
    )
    md_dir = base_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)

    stem = _safe_stem(path)
    reviewed_path = md_dir / f"{stem}.md"
    reviewed_path.write_text(reviewed_markdown, encoding="utf-8")

    return LightOcrResult(
        raw_text=raw_text,
        reviewed_markdown=reviewed_markdown,
        reviewed_path=reviewed_path,
    )
