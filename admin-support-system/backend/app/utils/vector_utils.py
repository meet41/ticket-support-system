from typing import List

import numpy as np


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    v1 = np.array(vec1, dtype=np.float32)
    v2 = np.array(vec2, dtype=np.float32)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


def batch_cosine_similarity(
    query_vec: List[float], doc_vecs: List[List[float]]
) -> List[float]:
    """
    Compute cosine similarity between a single query vector and many document vectors.
    Returns a list of similarity scores in the same order as doc_vecs.
    """
    if not doc_vecs:
        return []

    query = np.array(query_vec, dtype=np.float32)
    docs = np.array(doc_vecs, dtype=np.float32)

    query_norm = np.linalg.norm(query)
    if query_norm == 0.0:
        return [0.0] * len(doc_vecs)

    doc_norms = np.linalg.norm(docs, axis=1)
    # Avoid division by zero
    doc_norms = np.where(doc_norms == 0.0, 1.0, doc_norms)

    similarities = np.dot(docs, query) / (doc_norms * query_norm)
    return similarities.tolist()
