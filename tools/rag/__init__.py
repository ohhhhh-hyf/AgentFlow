"""Lightweight local RAG utilities.

The package is intentionally independent from domain runners. It can ingest
documents into a local store and retrieve context without changing existing
AgentFlow task behavior.
"""
from .config import RAGSettings, resolve_rag_settings
from .ingest import ingest_path
from .reference import (
    build_rag_reference,
    build_rag_reference_from_text,
    build_rag_reference_sync,
    extract_signal_sentences,
)
from .retriever import retrieve_context, search

__all__ = [
    "RAGSettings",
    "build_rag_reference",
    "build_rag_reference_from_text",
    "build_rag_reference_sync",
    "extract_signal_sentences",
    "ingest_path",
    "resolve_rag_settings",
    "retrieve_context",
    "search",
]
