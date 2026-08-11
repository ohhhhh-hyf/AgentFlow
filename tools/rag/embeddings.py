"""Embedding provider adapters for RAG vector mode."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import RAGSettings


class EmbeddingError(RuntimeError):
    """Raised when an embedding provider request fails."""


def _post_json(url: str, api_key: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise EmbeddingError(f"Embedding API 请求失败：HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise EmbeddingError(f"Embedding API 网络请求失败：{exc}") from exc


def embed_texts(texts: list[str], settings: RAGSettings) -> list[list[float]]:
    """Create embeddings with an OpenAI-compatible embeddings endpoint."""
    if not texts:
        return []
    if not settings.api_key:
        raise EmbeddingError(
            "RAG_MODE=vector 需要配置 API Key："
            "SILICONFLOW_API_KEY、ZHIPU_API_KEY 或 RAG_API_KEY"
        )

    payload = {
        "model": settings.embedding_model,
        "input": texts,
    }
    data = _post_json(f"{settings.base_url}/embeddings", settings.api_key, payload)
    items = data.get("data")
    if not isinstance(items, list):
        raise EmbeddingError(f"Embedding API 返回格式异常：{data}")
    ordered = sorted(items, key=lambda item: item.get("index", 0))
    vectors: list[list[float]] = []
    for item in ordered:
        embedding = item.get("embedding")
        if not isinstance(embedding, list):
            raise EmbeddingError(f"Embedding API 缺少 embedding 字段：{item}")
        vectors.append([float(value) for value in embedding])
    if len(vectors) != len(texts):
        raise EmbeddingError("Embedding API 返回数量与输入文本数量不一致")
    return vectors


__all__ = ["EmbeddingError", "embed_texts"]
