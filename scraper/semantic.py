"""Fail-open optional semantic reranker using Ollama nomic-embed-text.

Features:
- 100% fail-open: If Ollama library is not installed, daemon is offline,
  or errors occur, it gracefully returns input products unchanged in 0ms.
- Asynchronous non-blocking embedding via ollama.AsyncClient.
- Sanitized input: embeds only clean product titles (no JSON noise, no image URLs).
- Normalized cosine similarity scoring.
- Relative relevance filtering without arbitrary hard-truncation.
"""

import asyncio
import logging
import math
import re
from typing import Any

import config

logger = logging.getLogger(__name__)

_ollama_checked = False
_ollama_available = False


def _clean_text_for_embedding(text: str) -> str:
    """Sanitize title text for embedding vector calculation."""
    if not text:
        return ""
    # Remove HTML tags, brackets, and excessive whitespace
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"[\(\)\[\]\{\}]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:200]  # First 200 chars capture core product identity


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        dot += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


async def is_ollama_available() -> bool:
    """Check if Ollama library and daemon are reachable with a strict 300ms timeout."""
    global _ollama_checked, _ollama_available
    if _ollama_checked:
        return _ollama_available

    if not getattr(config, "OLLAMA_ENABLED", True):
        _ollama_checked = True
        _ollama_available = False
        return False

    try:
        import ollama  # type: ignore
        client = ollama.AsyncClient(host=getattr(config, "OLLAMA_HOST", "http://localhost:11434"))
        # Fast health check with short timeout
        async with asyncio.timeout(0.3):
            await client.list()
        _ollama_available = True
    except Exception:
        _ollama_available = False

    _ollama_checked = True
    return _ollama_available


async def semantic_rerank_deals(
    query: str,
    products: list[dict[str, Any]],
    similarity_floor: float = 0.35,
) -> list[dict[str, Any]]:
    """Semantically score and filter products using Ollama vector embeddings.

    Fails open immediately if Ollama is not installed or unreachable.
    """
    if not products or not query:
        return products

    if not await is_ollama_available():
        return products

    try:
        import ollama  # type: ignore
        client = ollama.AsyncClient(host=getattr(config, "OLLAMA_HOST", "http://localhost:11434"))
        model_name = getattr(config, "OLLAMA_MODEL", "nomic-embed-text")

        clean_query = _clean_text_for_embedding(query)
        clean_titles = [_clean_text_for_embedding(p.get("title", "")) for p in products]

        # Generate query embedding
        q_resp = await client.embed(model=model_name, input=clean_query)
        q_embeddings = q_resp.get("embeddings", [])
        if not q_embeddings:
            return products
        q_vec = q_embeddings[0]

        # Generate product embeddings
        p_resp = await client.embed(model=model_name, input=clean_titles)
        p_embeddings = p_resp.get("embeddings", [])
        if len(p_embeddings) != len(products):
            return products

        reranked = []
        for p, p_vec in zip(products, p_embeddings):
            sim = _cosine_similarity(q_vec, p_vec)
            p_copy = dict(p)
            p_copy["semantic_similarity"] = round(sim, 3)
            # Only keep products that meet the similarity floor
            if sim >= similarity_floor:
                # Modulate deal score with semantic alignment (never crash, smooth weighting)
                base_score = p_copy.get("deal_score", 50)
                semantic_factor = 0.70 + 0.30 * max(0.0, sim)
                p_copy["deal_score"] = min(100, round(base_score * semantic_factor))
                reranked.append(p_copy)

        # If semantic filter was too strict (fewer than 4 items), fail open to all products
        return reranked if len(reranked) >= 4 else products

    except Exception as e:
        logger.debug("Semantic reranker fail-open due to: %s", e)
        return products
