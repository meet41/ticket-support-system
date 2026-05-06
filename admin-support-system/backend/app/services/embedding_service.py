import logging
from datetime import datetime, timezone
from typing import List

from app.config.db import get_database
from app.utils.text_chunking import chunk_text

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

_model = None


def get_embedding_model():
    """Lazy-load the sentence-transformers model (downloaded on first use)."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
            logger.info("Embedding model loaded: %s", EMBEDDING_MODEL_NAME)
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            ) from exc
    return _model


def generate_embedding(text: str) -> List[float]:
    """Generate a single embedding vector for the given text."""
    model = get_embedding_model()
    vector = model.encode(text, convert_to_numpy=True)
    return vector.tolist()


def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts (batched for efficiency)."""
    model = get_embedding_model()
    vectors = model.encode(texts, convert_to_numpy=True, batch_size=32)
    return vectors.tolist()


async def embed_ticket(ticket: dict) -> int:
    """
    Generate and persist embeddings for all text chunks of a ticket.
    Deletes any pre-existing embeddings for the same ticket_id first.
    Returns the number of chunks embedded.
    """
    db = get_database()
    ticket_id = ticket.get("ticket_id")

    subject = ticket.get("subject", "")
    description = ticket.get("description", "")
    resolution = ticket.get("resolution", "")

    full_text = f"Subject: {subject}\n\nDescription: {description}"
    if resolution:
        full_text += f"\n\nResolution: {resolution}"

    chunks = chunk_text(full_text)
    if not chunks:
        return 0

    # Remove stale embeddings for this ticket
    await db.ticket_embeddings.delete_many({"ticket_id": ticket_id})

    embeddings = generate_embeddings_batch(chunks)

    now = datetime.now(timezone.utc)
    docs = [
        {
            "ticket_id": ticket_id,
            "ticket_number": ticket.get("ticket_number", ""),
            "chunk_index": i,
            "chunk_text": chunk,
            "embedding": embedding,
            "embedding_model": EMBEDDING_MODEL_NAME,
            "metadata": {
                "subject": subject,
                "status": ticket.get("status", ""),
                "priority": ticket.get("priority", ""),
                "customer_id": ticket.get("customer_id"),
                "created_at": ticket.get("created_at"),
            },
            "created_at": now,
        }
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]

    if docs:
        await db.ticket_embeddings.insert_many(docs)
        logger.info(
            "Embedded ticket %s (%d chunks)", ticket.get("ticket_number"), len(docs)
        )

    return len(docs)


async def embed_ticket_by_number(ticket_number: str) -> int:
    """Embed a single ticket identified by its human-readable ticket number."""
    db = get_database()
    ticket = await db.tickets.find_one({"ticket_number": ticket_number})
    if not ticket:
        return 0
    return await embed_ticket(ticket)


async def embed_all_tickets(batch_size: int = 50) -> dict:
    """
    Bulk-embed every ticket in the database that does not yet have embeddings.
    Returns a summary dict: {total, embedded, skipped, errors}.
    """
    db = get_database()
    already_embedded = set(
        doc["ticket_id"]
        async for doc in db.ticket_embeddings.find({}, {"ticket_id": 1})
    )

    total = 0
    embedded = 0
    skipped = 0
    errors = 0

    cursor = db.tickets.find({}, {"_id": 0})
    batch: List[dict] = []

    async def _flush(batch: List[dict]):
        nonlocal embedded, skipped, errors
        for ticket in batch:
            tid = ticket.get("ticket_id")
            if tid in already_embedded:
                skipped += 1
                continue
            try:
                n = await embed_ticket(ticket)
                if n:
                    embedded += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.warning("Error embedding ticket %s: %s", tid, exc)
                errors += 1

    async for ticket in cursor:
        total += 1
        batch.append(ticket)
        if len(batch) >= batch_size:
            await _flush(batch)
            batch.clear()

    if batch:
        await _flush(batch)

    return {
        "total": total,
        "embedded": embedded,
        "skipped": skipped,
        "errors": errors,
    }
