"""Search and context building for local RAG collections."""
from __future__ import annotations

from dataclasses import dataclass

from .config import RAGSettings
from .embeddings import embed_texts
from .scoring import cosine_similarity, keyword_scores
from .store import StoredChunk, collection_dir, load_collection, load_manifest


@dataclass(frozen=True)
class SearchResult:
    chunk: StoredChunk
    score: float
    rank: int


def _rank(
    chunks: list[StoredChunk],
    scores: list[float],
    top_k: int,
    min_score: float,
    score_ratio: float,
) -> list[SearchResult]:
    ranked = sorted(
        zip(chunks, scores),
        key=lambda item: item[1],
        reverse=True,
    )
    positive = [(chunk, float(score)) for chunk, score in ranked if score > 0]
    if not positive:
        return []
    top_score = positive[0][1]
    threshold = max(min_score, top_score * score_ratio)
    filtered = [(chunk, score) for chunk, score in positive if score >= threshold]
    if not filtered:
        filtered = positive[:1]

    results: list[SearchResult] = []
    for idx, (chunk, score) in enumerate(filtered[:top_k], start=1):
        results.append(SearchResult(chunk=chunk, score=score, rank=idx))
    return results


def search(
    domain: str,
    task: str,
    query: str,
    settings: RAGSettings,
    top_k: int | None = None,
) -> list[SearchResult]:
    """Search one local RAG collection."""
    out_dir = collection_dir(settings, domain, task)
    chunks = load_collection(out_dir)
    if not chunks:
        raise FileNotFoundError(f"RAG 索引不存在或为空，请先入库：{out_dir}")

    limit = top_k or settings.top_k
    manifest = load_manifest(out_dir)
    has_vectors = all(chunk.vector for chunk in chunks)
    use_vector = settings.mode == "vector" and has_vectors
    if manifest.get("mode") == "vector" and settings.mode == "vector" and has_vectors:
        query_vector = embed_texts([query], settings)[0]
        scores = [cosine_similarity(query_vector, chunk.vector or []) for chunk in chunks]
    elif use_vector:
        query_vector = embed_texts([query], settings)[0]
        scores = [cosine_similarity(query_vector, chunk.vector or []) for chunk in chunks]
    else:
        scores = keyword_scores(query, [chunk.text for chunk in chunks])
    return _rank(
        chunks,
        scores,
        limit,
        min_score=settings.min_score,
        score_ratio=settings.score_ratio,
    )


def build_context(results: list[SearchResult]) -> str:
    """Build a prompt-ready RAG context block."""
    if not results:
        return ""
    lines: list[str] = []
    for result in results:
        chunk = result.chunk
        lines.append(
            f"[{result.rank}] source={chunk.source} chunk={chunk.id} "
            f"score={result.score:.4f}\n{chunk.text}"
        )
    return "\n\n".join(lines)


def retrieve_context(
    domain: str,
    task: str,
    query: str,
    settings: RAGSettings,
    top_k: int | None = None,
) -> dict:
    results = search(domain, task, query, settings, top_k=top_k)
    return {
        "context": build_context(results),
        "matches": [
            {
                "rank": result.rank,
                "score": result.score,
                "id": result.chunk.id,
                "source": result.chunk.source,
                "source_path": result.chunk.source_path,
                "text": result.chunk.text,
            }
            for result in results
        ],
    }


__all__ = ["SearchResult", "build_context", "retrieve_context", "search"]
