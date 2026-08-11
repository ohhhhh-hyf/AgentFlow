"""Document loading helpers for local RAG sources."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_SUFFIXES = {".txt", ".md", ".json"}


@dataclass(frozen=True)
class SourceDocument:
    path: Path
    text: str

    @property
    def source(self) -> str:
        return self.path.name


def _read_json(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    return json.dumps(data, ensure_ascii=False, indent=2)


def load_documents(path: Path) -> list[SourceDocument]:
    """Load txt/md/json documents from a file or directory."""
    if not path.exists():
        raise FileNotFoundError(f"RAG 资料路径不存在：{path}")

    files: list[Path]
    if path.is_file():
        files = [path]
    else:
        files = sorted(
            file for file in path.rglob("*") if file.is_file() and file.suffix.lower() in SUPPORTED_SUFFIXES
        )

    documents: list[SourceDocument] = []
    for file in files:
        suffix = file.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            continue
        text = _read_json(file) if suffix == ".json" else file.read_text(encoding="utf-8")
        text = text.strip()
        if text:
            documents.append(SourceDocument(path=file, text=text))
    return documents


__all__ = ["SUPPORTED_SUFFIXES", "SourceDocument", "load_documents"]
