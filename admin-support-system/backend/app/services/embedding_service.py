"""
Embedding Service
-----------------
Generates text embeddings using sentence-transformers (all-MiniLM-L6-v2)
and stores them in MongoDB's `ticket_embeddings` collection.
"""
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

from app.config.db import get_database
from app.config.settings import settings

logger = logging.getLogger(__name__)

_model = None  # lazy-loaded


def _get_model():
    """Lazy-load the sentence-transformer model once per process."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(settings.EMBEDDING_MODEL)
            logger.info("Loaded embedding model: %s", settings.EMBEDDING_MODEL)
        except Exception as exc:
            logger.error("Failed to load embedding model: %s", exc)
            raise
    return _model


def _chunk_text(text: str, max_tokens: int = None) -> List[str]:
    """
    Naively splits text into chunks of ~max_tokens words.
    Sentence-level splitting is attempted first.
    """
    max_tokens = max_tokens or settings.EMBEDDING_CHUNK_SIZE
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks, current, current_len = [], [], 0
    for sent in sentences:
        word_count = len(sent.split())
        if current_len + word_count > max_tokens and current:
            chunks.append(" ".join(current))
            current, current_len = [], 0
        current.append(sent)
        current_len += word_count
    if current:
        chunks.append(" ".join(current))
    return chunks or [text]


def generate_embedding(text: str) -> List[float]:
    """Return a float list embedding for the given text."""
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


async def embed_ticket(ticket: dict) -> None:
    """
    Embed a ticket's description (and resolution if present) and store chunks
    in the `ticket_embeddings` collection.  Idempotent – deletes old chunks first.
    """
    db = get_database()
    ticket_id = ticket.get("ticket_id")
    if ticket_id is None:
        return

    text_parts = []
    if ticket.get("description"):
        text_parts.append(ticket["description"])
    if ticket.get("resolution"):
        text_parts.append("Resolution: " + ticket["resolution"])

    full_text = " ".join(text_parts).strip()
    if not full_text:
        return

    chunks = _chunk_text(full_text)

    # Remove stale embeddings
    await db.ticket_embeddings.delete_many({"ticket_id": ticket_id})

    docs = []
    for idx, chunk in enumerate(chunks):
        try:
            vector = generate_embedding(chunk)
        except Exception as exc:
            logger.warning("Embedding failed for ticket %s chunk %d: %s", ticket_id, idx, exc)
            continue
        docs.append({
            "ticket_id": ticket_id,
            "ticket_number": ticket.get("ticket_number", ""),
            "chunk_index": idx,
            "chunk": chunk,
            "embedding_vector": vector,
            "metadata": {
                "subject": ticket.get("subject", ""),
                "status": ticket.get("status", ""),
                "priority": ticket.get("priority", ""),
                "customer_id": ticket.get("customer_id"),
                "created_at": ticket.get("created_at"),
            },
            "embedded_at": datetime.now(timezone.utc),
        })

    if docs:
        await db.ticket_embeddings.insert_many(docs)
        logger.debug("Embedded ticket %s (%d chunk(s))", ticket_id, len(docs))


async def bulk_embed_all_tickets() -> int:
    """Embed every ticket in the database.  Returns number of tickets processed."""
    db = get_database()
    count = 0
    async for ticket in db.tickets.find({}):
        try:
            await embed_ticket(ticket)
            count += 1
        except Exception as exc:
            logger.warning("bulk_embed: ticket %s failed: %s", ticket.get("ticket_id"), exc)
    logger.info("bulk_embed_all_tickets: processed %d ticket(s)", count)
    return count


async def search_similar_embeddings(
    query_text: str,
    top_k: int = 5,
    filters: Optional[dict] = None,
) -> List[dict]:
    """
    Compute cosine similarity between query embedding and stored embeddings.
    Returns top_k results sorted by similarity descending.
    """
    try:
        import numpy as np
    except ImportError:
        logger.error("numpy is required for vector search")
        return []

    try:
        query_vec = generate_embedding(query_text)
    except Exception as exc:
        logger.error("Failed to generate query embedding: %s", exc)
        return []

    q = np.array(query_vec, dtype=np.float32)

    mongo_filter = filters or {}
    # Pull all embedding chunks (feasible for typical support systems ≤100k tickets)
    # For large scale, replace with Atlas Vector Search
    cursor = get_database().ticket_embeddings.find(
        mongo_filter,
        {"ticket_id": 1, "ticket_number": 1, "chunk": 1, "embedding_vector": 1, "metadata": 1},
    )

    scored = []
    async for doc in cursor:
        vec = doc.get("embedding_vector")
        if not vec:
            continue
        v = np.array(vec, dtype=np.float32)
        norm = np.linalg.norm(v)
        if norm == 0:
            continue
        score = float(np.dot(q, v) / norm)
        scored.append({
            "ticket_id": doc["ticket_id"],
            "ticket_number": doc.get("ticket_number", ""),
            "chunk": doc.get("chunk", ""),
            "metadata": doc.get("metadata", {}),
            "similarity_score": score,
        })

    # Deduplicate by ticket_id – keep highest score per ticket
    best: dict = {}
    for item in scored:
        tid = item["ticket_id"]
        if tid not in best or item["similarity_score"] > best[tid]["similarity_score"]:
            best[tid] = item

    ranked = sorted(best.values(), key=lambda x: x["similarity_score"], reverse=True)
    return ranked[:top_k]
