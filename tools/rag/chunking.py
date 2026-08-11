"""Text chunking for local RAG ingestion."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .documents import SourceDocument


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    source: str
    source_path: str
    index: int


def _paragraphs(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n+", text.strip())
    return [re.sub(r"\s+", " ", block).strip() for block in blocks if block.strip()]


def _markdown_sections(text: str) -> list[str]:
    sections: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and current:
            section = "\n".join(current).strip()
            if section:
                sections.append(section)
            current = [line]
        else:
            current.append(line)
    if current:
        section = "\n".join(current).strip()
        if section:
            sections.append(section)
    return sections if len(sections) > 1 else []


def _window_text(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    step = max(size - overlap, 1)
    while start < len(text):
        part = text[start : start + size].strip()
        if part:
            chunks.append(part)
        if start + size >= len(text):
            break
        start += step
    return chunks


def split_document(document: SourceDocument, chunk_size: int, overlap: int) -> list[Chunk]:
    """Split one document into deterministic chunks."""
    parts: list[str] = []
    sections = _markdown_sections(document.text)
    if sections:
        for section in sections:
            parts.extend(_window_text(section, chunk_size, overlap))
    else:
        parts = _split_plain_text(document.text, chunk_size, overlap)

    chunks: list[Chunk] = []
    for idx, text in enumerate(parts):
        chunk_id = f"{document.path.stem}#{idx:04d}"
        chunks.append(
            Chunk(
                id=chunk_id,
                text=text,
                source=document.source,
                source_path=str(document.path),
                index=idx,
            )
        )
    return chunks


def _split_plain_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for paragraph in _paragraphs(text):
        if not current:
            current = paragraph
            continue
        candidate = f"{current}\n\n{paragraph}"
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            parts.extend(_window_text(current, chunk_size, overlap))
            current = paragraph
    if current:
        parts.extend(_window_text(current, chunk_size, overlap))
    return parts


def split_documents(
    documents: list[SourceDocument],
    chunk_size: int,
    overlap: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(split_document(document, chunk_size, overlap))
    return chunks


def default_rag_source(samples_dir: Path, domain: str, task: str | None = None) -> Path:
    """Return the preferred local RAG source directory."""
    if task:
        task_dir = samples_dir / domain / "rag" / task
        if task_dir.exists():
            return task_dir
    return samples_dir / domain / "rag"


__all__ = ["Chunk", "default_rag_source", "split_document", "split_documents"]
