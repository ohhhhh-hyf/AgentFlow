"""Local file store for RAG chunks and vectors."""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .chunking import Chunk
from .config import RAGSettings


CHUNKS_FILE = "chunks.jsonl"
VECTORS_FILE = "vectors.jsonl"
MANIFEST_FILE = "manifest.json"


@dataclass(frozen=True)
class StoredChunk:
    id: str
    text: str
    source: str
    source_path: str
    index: int
    vector: list[float] | None = None


def collection_dir(settings: RAGSettings, domain: str, task: str) -> Path:
    return settings.store_dir / domain / task


def reset_collection(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def save_collection(
    path: Path,
    chunks: list[Chunk],
    settings: RAGSettings,
    vectors: list[list[float]] | None = None,
) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _write_jsonl(path / CHUNKS_FILE, (asdict(chunk) for chunk in chunks))
    if vectors is not None:
        rows = (
            {
                "id": chunk.id,
                "vector": vector,
            }
            for chunk, vector in zip(chunks, vectors)
        )
        _write_jsonl(path / VECTORS_FILE, rows)
    manifest = {
        "mode": settings.mode,
        "provider": settings.provider if settings.mode == "vector" else "",
        "embedding_model": settings.embedding_model if settings.mode == "vector" else "",
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "chunk_count": len(chunks),
    }
    (path / MANIFEST_FILE).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_collection(path: Path) -> list[StoredChunk]:
    chunk_rows = _read_jsonl(path / CHUNKS_FILE)
    vector_rows = {row.get("id"): row.get("vector") for row in _read_jsonl(path / VECTORS_FILE)}
    chunks: list[StoredChunk] = []
    for row in chunk_rows:
        chunks.append(
            StoredChunk(
                id=row["id"],
                text=row["text"],
                source=row["source"],
                source_path=row["source_path"],
                index=int(row["index"]),
                vector=vector_rows.get(row["id"]),
            )
        )
    return chunks


def load_manifest(path: Path) -> dict:
    manifest_path = path / MANIFEST_FILE
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


__all__ = [
    "StoredChunk",
    "collection_dir",
    "load_collection",
    "load_manifest",
    "reset_collection",
    "save_collection",
]
