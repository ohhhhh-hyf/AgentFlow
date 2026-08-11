"""RAG configuration resolved from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MODE = "keyword"
DEFAULT_PROVIDER = "siliconflow"
DEFAULT_MODEL = "BAAI/bge-m3"
DEFAULT_TOP_K = 5
DEFAULT_CHUNK_SIZE = 700
DEFAULT_CHUNK_OVERLAP = 120
DEFAULT_MIN_SCORE = 0.0
DEFAULT_SCORE_RATIO = 0.25

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


@dataclass(frozen=True)
class RAGSettings:
    enabled: bool
    mode: str
    provider: str
    api_key: str
    base_url: str
    embedding_model: str
    top_k: int
    min_score: float
    score_ratio: float
    chunk_size: int
    chunk_overlap: int
    store_dir: Path
    samples_dir: Path


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _provider_key(provider: str) -> str:
    if provider == "siliconflow":
        return _env("SILICONFLOW_API_KEY") or _env("RAG_API_KEY")
    if provider == "zhipu":
        return _env("ZHIPU_API_KEY") or _env("RAG_API_KEY")
    return _env("RAG_API_KEY")


def _provider_base_url(provider: str) -> str:
    explicit = _env("RAG_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    if provider == "zhipu":
        return ZHIPU_BASE_URL
    return SILICONFLOW_BASE_URL


def _rooted_path(raw: str, project_root: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (project_root / path).resolve()


def resolve_rag_settings(project_root: Path) -> RAGSettings:
    """Resolve RAG settings from environment variables.

    Defaults keep RAG usable without an embedding API: keyword mode stores and
    searches local chunks only.
    """
    mode = _env("RAG_MODE", DEFAULT_MODE).lower()
    if mode not in {"keyword", "vector"}:
        raise ValueError("RAG_MODE 只能是 keyword 或 vector")

    provider = _env("RAG_PROVIDER", DEFAULT_PROVIDER).lower()
    store_dir = _rooted_path(_env("RAG_STORE_DIR", "rag_store"), project_root)
    samples_dir = _rooted_path(_env("RAG_SAMPLE_DIR", "samples"), project_root)

    return RAGSettings(
        enabled=_bool_env("RAG_ENABLED", True),
        mode=mode,
        provider=provider,
        api_key=_provider_key(provider),
        base_url=_provider_base_url(provider),
        embedding_model=_env("RAG_EMBEDDING_MODEL", DEFAULT_MODEL),
        top_k=_int_env("RAG_TOP_K", DEFAULT_TOP_K),
        min_score=_float_env("RAG_MIN_SCORE", DEFAULT_MIN_SCORE),
        score_ratio=_float_env("RAG_SCORE_RATIO", DEFAULT_SCORE_RATIO),
        chunk_size=_int_env("RAG_CHUNK_SIZE", DEFAULT_CHUNK_SIZE),
        chunk_overlap=_int_env("RAG_CHUNK_OVERLAP", DEFAULT_CHUNK_OVERLAP),
        store_dir=store_dir,
        samples_dir=samples_dir,
    )


__all__ = ["RAGSettings", "resolve_rag_settings"]
