"""Ingest local documents into a RAG collection."""
from __future__ import annotations

from pathlib import Path

from .chunking import default_rag_source, split_documents
from .config import RAGSettings
from .documents import load_documents
from .embeddings import embed_texts
from .store import collection_dir, reset_collection, save_collection


def ingest_path(
    source_path: Path,
    domain: str,
    task: str,
    settings: RAGSettings,
) -> dict:
    """Ingest a file or directory into rag_store/{domain}/{task}."""
    documents = load_documents(source_path)
    if not documents:
        raise ValueError(f"没有找到可入库的 RAG 资料：{source_path}")

    chunks = split_documents(
        documents,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )
    if not chunks:
        raise ValueError(f"RAG 资料没有产生有效分块：{source_path}")

    vectors = None
    if settings.mode == "vector":
        vectors = embed_texts([chunk.text for chunk in chunks], settings)

    out_dir = collection_dir(settings, domain, task)
    reset_collection(out_dir)
    save_collection(out_dir, chunks, settings, vectors=vectors)
    return {
        "source_path": str(source_path),
        "store_path": str(out_dir),
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "mode": settings.mode,
    }


def ingest_default(domain: str, task: str, settings: RAGSettings) -> dict:
    source = default_rag_source(settings.samples_dir, domain, task)
    return ingest_path(source, domain, task, settings)


__all__ = ["ingest_default", "ingest_path"]
