import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException

from app.config.db import get_database
from app.config.settings import settings
from app.services.embedding_service import generate_embedding
from app.utils.prompt_injection_guard import sanitize_query
from app.utils.vector_utils import batch_cosine_similarity

logger = logging.getLogger(__name__)

TOP_K = 5
SIMILARITY_THRESHOLD = 0.25
MAX_CONTEXT_CHARS = 6000  # approx. 1500 tokens


# ─────────────────────────────────────────────────────────
# Retrieval helpers
# ─────────────────────────────────────────────────────────


async def semantic_search(
    query_embedding: List[float],
    top_k: int = TOP_K,
    customer_id: Optional[int] = None,
) -> List[dict]:
    """
    Fetch all stored embeddings, compute cosine similarity in-process,
    and return the top-k unique tickets sorted by score.
    Optionally filter by customer_id for tenant isolation.
    """
    db = get_database()

    filter_q: dict = {}
    if customer_id is not None:
        filter_q["metadata.customer_id"] = customer_id

    # Fetch all chunks (embedding + metadata only – no heavy fields)
    rows = []
    async for doc in db.ticket_embeddings.find(
        filter_q,
        {
            "ticket_id": 1,
            "ticket_number": 1,
            "chunk_text": 1,
            "embedding": 1,
            "metadata": 1,
        },
    ):
        rows.append(doc)

    if not rows:
        return []

    embeddings = [r["embedding"] for r in rows]
    scores = batch_cosine_similarity(query_embedding, embeddings)

    # Attach scores and keep best score per ticket
    best: dict[int, dict] = {}
    for row, score in zip(rows, scores):
        tid = row["ticket_id"]
        if tid not in best or score > best[tid]["score"]:
            best[tid] = {
                "ticket_id": tid,
                "ticket_number": row.get("ticket_number", ""),
                "score": score,
                "chunk_text": row.get("chunk_text", ""),
                "metadata": row.get("metadata", {}),
            }

    # Filter by threshold and return top-k
    results = sorted(best.values(), key=lambda x: x["score"], reverse=True)
    results = [r for r in results if r["score"] >= SIMILARITY_THRESHOLD]
    return results[:top_k]


async def keyword_search(
    query: str,
    top_k: int = TOP_K,
    customer_id: Optional[int] = None,
) -> List[dict]:
    """
    Simple MongoDB regex-based keyword search on subject + description.
    Falls back gracefully when no matches are found.
    """
    db = get_database()

    words = [w for w in query.split() if len(w) > 2]
    if not words:
        return []

    # Build OR conditions over subject and description
    regex_conditions = []
    for word in words[:8]:  # limit to first 8 meaningful words
        escaped = word.replace("(", r"\(").replace(")", r"\)")
        regex_conditions.append({"subject": {"$regex": escaped, "$options": "i"}})
        regex_conditions.append(
            {"description": {"$regex": escaped, "$options": "i"}}
        )

    filter_q: dict = {"$or": regex_conditions}
    if customer_id is not None:
        filter_q["customer_id"] = customer_id

    results = []
    async for ticket in db.tickets.find(filter_q, {"messages": 0}).limit(top_k * 2):
        results.append(
            {
                "ticket_id": ticket["ticket_id"],
                "ticket_number": ticket.get("ticket_number", ""),
                "score": 0.5,  # fixed keyword-match score
                "subject": ticket.get("subject", ""),
                "description": ticket.get("description", ""),
                "resolution": ticket.get("resolution", ""),
                "status": ticket.get("status", ""),
                "priority": ticket.get("priority", ""),
                "created_at": ticket.get("created_at"),
            }
        )
    return results[:top_k]


async def hybrid_search(
    query: str,
    top_k: int = TOP_K,
    customer_id: Optional[int] = None,
) -> List[dict]:
    """
    Merge semantic and keyword results, deduplicate by ticket_id,
    and return the top-k by blended score.
    """
    query_embedding = generate_embedding(query)
    sem_results = await semantic_search(query_embedding, top_k, customer_id)
    kw_results = await keyword_search(query, top_k, customer_id)

    merged: dict[int, dict] = {}

    for r in sem_results:
        merged[r["ticket_id"]] = {
            **r,
            "sem_score": r["score"],
            "kw_score": 0.0,
        }

    for r in kw_results:
        tid = r["ticket_id"]
        if tid in merged:
            merged[tid]["kw_score"] = r["score"]
        else:
            merged[tid] = {
                **r,
                "sem_score": 0.0,
                "kw_score": r["score"],
            }

    # Blended score: 70% semantic + 30% keyword
    for item in merged.values():
        item["score"] = 0.7 * item.get("sem_score", 0.0) + 0.3 * item.get(
            "kw_score", 0.0
        )

    ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:top_k]


# ─────────────────────────────────────────────────────────
# Context construction
# ─────────────────────────────────────────────────────────


async def build_context(ticket_ids: List[int]) -> str:
    """Fetch full ticket details and build a compact context string."""
    if not ticket_ids:
        return ""

    db = get_database()
    lines = []
    char_count = 0

    for tid in ticket_ids:
        ticket = await db.tickets.find_one({"ticket_id": tid}, {"messages": 0})
        if not ticket:
            continue

        block = (
            f"---\n"
            f"Ticket: {ticket.get('ticket_number', tid)}\n"
            f"Subject: {ticket.get('subject', '')}\n"
            f"Status: {ticket.get('status', '')}\n"
            f"Priority: {ticket.get('priority', '')}\n"
            f"Description: {ticket.get('description', '')}\n"
        )
        resolution = ticket.get("resolution", "")
        if resolution:
            block += f"Resolution: {resolution}\n"

        if char_count + len(block) > MAX_CONTEXT_CHARS:
            break

        lines.append(block)
        char_count += len(block)

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# OpenAI call
# ─────────────────────────────────────────────────────────


def _call_openai(prompt: str) -> tuple[str, dict]:
    """
    Call OpenAI ChatCompletion and return (response_text, token_usage).
    Raises RuntimeError if the API key is not configured or the call fails.
    """
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. "
            "Set it in your .env file to enable AI response generation."
        )

    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=settings.OPENAI_MAX_TOKENS,
            temperature=0.2,
        )
        text = response.choices[0].message.content or ""
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens
            if response.usage
            else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
        return text, usage
    except ImportError as exc:
        raise RuntimeError(
            "openai package is not installed. Run: pip install openai"
        ) from exc


# ─────────────────────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────────────────────


def build_rag_prompt(query: str, context: str, cited_numbers: List[str]) -> str:
    citations_hint = (
        (", ".join(cited_numbers)) if cited_numbers else "no specific tickets"
    )
    return f"""You are a helpful support intelligence assistant. Answer the following question strictly based on the historical support ticket data provided below. Do not use any outside knowledge.

If the provided context does not contain enough information to answer the question, say: "I could not find relevant information in the historical tickets."

Always cite the ticket numbers (e.g. TCK-1, TCK-2) that support your answer.

Relevant tickets ({citations_hint}):
{context}

---
Question: {query}

Answer:"""


def build_summary_prompt(ticket: dict) -> str:
    return f"""You are a support knowledge-base analyst. Summarize the resolution pattern for the following support ticket in 2-4 sentences. Focus on the root cause and the steps taken to resolve the issue.

Ticket: {ticket.get('ticket_number', '')}
Subject: {ticket.get('subject', '')}
Description: {ticket.get('description', '')}
Resolution: {ticket.get('resolution', '')}

Summary:"""


# ─────────────────────────────────────────────────────────
# Public RAG entry-points
# ─────────────────────────────────────────────────────────


async def query_rag(
    query: str,
    user_id: str,
    user_role: str,
    customer_id: Optional[int] = None,
) -> dict:
    """
    Full RAG pipeline:
      1. Sanitize query
      2. Hybrid retrieval
      3. Context construction
      4. OpenAI response generation
      5. Log the query
    """
    t0 = time.time()

    safe_query = sanitize_query(query)

    candidates = await hybrid_search(safe_query, TOP_K, customer_id)
    ticket_ids = [c["ticket_id"] for c in candidates]
    ticket_numbers = [c.get("ticket_number", str(c["ticket_id"])) for c in candidates]

    context = await build_context(ticket_ids)

    token_usage: dict = {}
    response_text = ""

    if not context:
        response_text = (
            "I could not find relevant information in the historical tickets "
            "to answer your question."
        )
    else:
        prompt = build_rag_prompt(safe_query, context, ticket_numbers)
        try:
            response_text, token_usage = _call_openai(prompt)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

    latency_ms = round((time.time() - t0) * 1000, 2)

    # Persist log
    db = get_database()
    log_doc = {
        "query": safe_query,
        "user_id": user_id,
        "user_role": user_role,
        "retrieved_ticket_ids": ticket_ids,
        "retrieved_ticket_numbers": ticket_numbers,
        "response": response_text,
        "token_usage": token_usage,
        "latency_ms": latency_ms,
        "feedback": None,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.ai_logs.insert_one(log_doc)
    log_id = str(result.inserted_id)

    return {
        "log_id": log_id,
        "query": safe_query,
        "response": response_text,
        "sources": ticket_numbers,
        "latency_ms": latency_ms,
        "token_usage": token_usage,
    }


async def find_similar_tickets(
    ticket_number: str,
    top_k: int = TOP_K,
) -> List[dict]:
    """Return tickets semantically similar to the given ticket."""
    db = get_database()
    ticket = await db.tickets.find_one({"ticket_number": ticket_number})
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_number} not found.")

    subject = ticket.get("subject", "")
    description = ticket.get("description", "")
    query_text = f"{subject} {description}".strip()

    query_embedding = generate_embedding(query_text)
    results = await semantic_search(query_embedding, top_k + 1)  # +1 to exclude self

    # Exclude the ticket itself
    results = [r for r in results if r["ticket_id"] != ticket["ticket_id"]]
    return results[:top_k]


async def summarize_resolution(ticket_number: str) -> dict:
    """Generate a brief AI summary of how a ticket was resolved."""
    db = get_database()
    ticket = await db.tickets.find_one(
        {"ticket_number": ticket_number}, {"messages": 0}
    )
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_number} not found.")

    if not ticket.get("resolution") and ticket.get("status") not in (
        "resolved",
        "closed",
    ):
        return {
            "ticket_number": ticket_number,
            "summary": "This ticket has not been resolved yet.",
        }

    prompt = build_summary_prompt(ticket)
    try:
        summary, _ = _call_openai(prompt)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return {"ticket_number": ticket_number, "summary": summary.strip()}


async def analyze_trends(days: int = 30) -> dict:
    """
    Produce trend analytics using MongoDB aggregations.
    No ClickHouse required — all computed from the tickets collection.
    """
    from datetime import timedelta

    db = get_database()
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # --- Status distribution ---
    status_pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    status_dist = {}
    async for doc in db.tickets.aggregate(status_pipeline):
        status_dist[doc["_id"]] = doc["count"]

    # --- Priority distribution ---
    priority_pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": "$priority", "count": {"$sum": 1}}},
    ]
    priority_dist = {}
    async for doc in db.tickets.aggregate(priority_pipeline):
        priority_dist[doc["_id"]] = doc["count"]

    # --- Top subjects ---
    subject_pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": "$subject", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_subjects = []
    async for doc in db.tickets.aggregate(subject_pipeline):
        top_subjects.append({"subject": doc["_id"], "count": doc["count"]})

    # --- Daily volume (last 14 days for chart) ---
    daily_pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {
            "$group": {
                "_id": {
                    "year": {"$year": "$created_at"},
                    "month": {"$month": "$created_at"},
                    "day": {"$dayOfMonth": "$created_at"},
                },
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id.year": 1, "_id.month": 1, "_id.day": 1}},
    ]
    daily_volume = []
    async for doc in db.tickets.aggregate(daily_pipeline):
        d = doc["_id"]
        daily_volume.append(
            {
                "date": f"{d['year']}-{d['month']:02d}-{d['day']:02d}",
                "count": doc["count"],
            }
        )

    # --- Average resolution time ---
    resolution_pipeline = [
        {
            "$match": {
                "created_at": {"$gte": since},
                "status": {"$in": ["resolved", "closed"]},
                "closed_at": {"$ne": None},
            }
        },
        {
            "$project": {
                "resolution_hours": {
                    "$divide": [
                        {"$subtract": ["$closed_at", "$created_at"]},
                        3_600_000,  # ms → hours
                    ]
                }
            }
        },
        {"$group": {"_id": None, "avg_hours": {"$avg": "$resolution_hours"}}},
    ]
    avg_resolution_hours = None
    async for doc in db.tickets.aggregate(resolution_pipeline):
        avg_resolution_hours = round(doc.get("avg_hours", 0), 2)

    total = sum(status_dist.values())

    return {
        "period_days": days,
        "total_tickets": total,
        "status_distribution": status_dist,
        "priority_distribution": priority_dist,
        "top_subjects": top_subjects,
        "daily_volume": daily_volume,
        "avg_resolution_hours": avg_resolution_hours,
    }
