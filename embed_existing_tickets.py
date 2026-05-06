#!/usr/bin/env python3
"""
embed_existing_tickets.py
--------------------------
One-shot script to generate and store embeddings for ALL existing tickets
in MongoDB.  Run this once after setting up the AI system on an existing
deployment to backfill embeddings.

Usage:
    cd <project-root>
    python embed_existing_tickets.py [--mongo-url mongodb://...] [--db ticket_support_db]

Environment variables (override via .env or CLI args):
    MONGODB_URL     – MongoDB connection string
    DATABASE_NAME   – Database name
    EMBEDDING_MODEL – Sentence-transformer model name
"""
import asyncio
import argparse
import logging
import os
import re
from datetime import datetime, timezone
from typing import List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("embed_existing_tickets")


# ── Config ─────────────────────────────────────────────────────────────────────

DEFAULT_MONGO_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DEFAULT_DB_NAME = os.getenv("DATABASE_NAME", "ticket_support_db")
DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
DEFAULT_CHUNK_SIZE = int(os.getenv("EMBEDDING_CHUNK_SIZE", "500"))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _chunk_text(text: str, max_tokens: int = DEFAULT_CHUNK_SIZE) -> List[str]:
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


async def embed_all(mongo_url: str, db_name: str, model_name: str, batch_size: int = 50):
    """Main embedding loop."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from sentence_transformers import SentenceTransformer

    logger.info("Connecting to MongoDB: %s / %s", mongo_url, db_name)
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    logger.info("Loading embedding model: %s", model_name)
    model = SentenceTransformer(model_name)

    total = await db.tickets.count_documents({})
    logger.info("Found %d ticket(s) to embed.", total)

    processed = 0
    errors = 0

    async for ticket in db.tickets.find({}):
        ticket_id = ticket.get("ticket_id")
        ticket_number = ticket.get("ticket_number", "")

        text_parts = []
        if ticket.get("description"):
            text_parts.append(ticket["description"])
        if ticket.get("resolution"):
            text_parts.append("Resolution: " + ticket["resolution"])

        full_text = " ".join(text_parts).strip()
        if not full_text:
            logger.debug("Ticket %s has no text to embed, skipping.", ticket_number)
            continue

        chunks = _chunk_text(full_text)

        # Remove stale embeddings
        await db.ticket_embeddings.delete_many({"ticket_id": ticket_id})

        docs = []
        for idx, chunk in enumerate(chunks):
            try:
                vector = model.encode(chunk, normalize_embeddings=True).tolist()
                docs.append({
                    "ticket_id": ticket_id,
                    "ticket_number": ticket_number,
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
            except Exception as exc:
                logger.error("Chunk encoding failed ticket %s idx %d: %s", ticket_number, idx, exc)
                errors += 1

        if docs:
            await db.ticket_embeddings.insert_many(docs)
            logger.info("[%d/%d] Embedded %s (%d chunk(s))", processed + 1, total, ticket_number, len(docs))

        processed += 1

    # Ensure indexes
    logger.info("Ensuring indexes on ticket_embeddings …")
    await db.ticket_embeddings.create_index([("ticket_id", 1)])
    await db.ticket_embeddings.create_index([("metadata.subject", 1)])
    await db.ticket_embeddings.create_index([("metadata.status", 1)])

    logger.info("Ensuring indexes on ai_logs …")
    await db.ai_logs.create_index([("created_at", -1)])
    await db.ai_logs.create_index([("helpful", 1)])

    logger.info(
        "Done. Processed: %d  Errors: %d  Total chunks stored: see ticket_embeddings collection.",
        processed, errors,
    )
    client.close()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk embed all tickets into MongoDB.")
    parser.add_argument("--mongo-url", default=DEFAULT_MONGO_URL)
    parser.add_argument("--db", default=DEFAULT_DB_NAME)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    asyncio.run(embed_all(args.mongo_url, args.db, args.model))
