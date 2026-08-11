"""Keyword and vector scoring utilities."""
from __future__ import annotations

import math
import re
from collections import Counter


_ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")
_CJK = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese/English text for a lightweight BM25-like score."""
    lowered = text.lower()
    tokens = _ASCII_WORD.findall(lowered)
    cjk_chars = _CJK.findall(lowered)
    tokens.extend(cjk_chars)
    tokens.extend("".join(pair) for pair in zip(cjk_chars, cjk_chars[1:]))
    return tokens


def keyword_scores(query: str, texts: list[str]) -> list[float]:
    query_terms = Counter(tokenize(query))
    if not query_terms:
        return [0.0 for _ in texts]
    doc_terms = [Counter(tokenize(text)) for text in texts]
    doc_count = len(doc_terms)
    df: Counter[str] = Counter()
    for terms in doc_terms:
        for term in terms:
            df[term] += 1

    scores: list[float] = []
    for terms in doc_terms:
        score = 0.0
        length_norm = math.sqrt(sum(terms.values()) or 1)
        for term, q_count in query_terms.items():
            tf = terms.get(term, 0)
            if not tf:
                continue
            idf = math.log((doc_count + 1) / (df[term] + 0.5)) + 1
            score += q_count * (tf / length_norm) * idf
        scores.append(score)
    return scores


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


__all__ = ["cosine_similarity", "keyword_scores", "tokenize"]
