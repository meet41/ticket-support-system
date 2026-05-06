"""
RAG Service
-----------
Implements the full Retrieval-Augmented Generation pipeline:
  1. Convert user query to embedding
  2. Hybrid retrieval (semantic + optional keyword)
  3. Construct structured context
  4. Call OpenAI GPT to generate a grounded answer
  5. Log the interaction to ai_logs
"""
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from bson import ObjectId

from app.config.db import get_database
from app.config.settings import settings
from app.services.embedding_service import search_similar_embeddings

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _openai_client():
    """Return an OpenAI client, or raise if key is not configured."""
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured. Set it in your .env file.")
    try:
        from openai import OpenAI
        return OpenAI(api_key=settings.OPENAI_API_KEY)
    except ImportError:
        raise ImportError("openai package is required. Install it with: pip install openai")


def _truncate_to_tokens(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + " [truncated]"


def _build_context(tickets: List[dict], max_words: int = 2000) -> str:
    """Build a structured context block from retrieved tickets."""
    lines = []
    word_count = 0
    for i, t in enumerate(tickets, 1):
        subject = t.get("subject", "N/A")
        description = t.get("description", "")
        resolution = t.get("resolution") or ""
        status = t.get("status", "")
        priority = t.get("priority", "")

        entry = (
            f"[Ticket {i}: {t.get('ticket_number', 'N/A')}]\n"
            f"  Subject : {subject}\n"
            f"  Status  : {status} | Priority: {priority}\n"
            f"  Issue   : {description[:400]}\n"
        )
        if resolution:
            entry += f"  Resolution: {resolution[:300]}\n"
        entry_words = len(entry.split())
        if word_count + entry_words > max_words:
            break
        lines.append(entry)
        word_count += entry_words
    return "\n".join(lines)


async def _save_log(
    query: str,
    response: str,
    ticket_ids: List[int],
    tokens_used: int,
    latency_ms: float,
    endpoint: str = "query",
) -> str:
    db = get_database()
    doc = {
        "query": query,
        "response": response,
        "retrieved_ticket_ids": ticket_ids,
        "tokens_used": tokens_used,
        "latency_ms": latency_ms,
        "endpoint": endpoint,
        "helpful": None,
        "feedback_comment": None,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.ai_logs.insert_one(doc)
    return str(result.inserted_id)


# ─── Core RAG Query ───────────────────────────────────────────────────────────

async def rag_query(
    question: str,
    top_k: int = 5,
    filters: Optional[Dict[str, Any]] = None,
) -> dict:
    """Ask a question and get a grounded AI answer with ticket citations."""
    start_time = time.time()
    db = get_database()

    # 1. Semantic retrieval
    similar = await search_similar_embeddings(question, top_k=top_k, filters=filters)

    # 2. Fetch full ticket docs for context
    ticket_ids = [s["ticket_id"] for s in similar]
    tickets = []
    if ticket_ids:
        async for t in db.tickets.find({"ticket_id": {"$in": ticket_ids}}):
            t["_id"] = str(t["_id"])
            tickets.append(t)

    # Re-order tickets to match similarity ranking
    ticket_map = {t["ticket_id"]: t for t in tickets}
    ordered = [ticket_map[tid] for tid in ticket_ids if tid in ticket_map]

    citations = [
        {
            "ticket_id": s["ticket_id"],
            "ticket_number": s["ticket_number"] or ticket_map.get(s["ticket_id"], {}).get("ticket_number", ""),
            "subject": ticket_map.get(s["ticket_id"], {}).get("subject", ""),
            "relevance_score": round(s["similarity_score"], 4),
        }
        for s in similar
        if s["ticket_id"] in ticket_map
    ]

    # 3. Build context
    context = _build_context(ordered, max_words=settings.RAG_MAX_CONTEXT_TOKENS)

    # 4. Generate LLM response
    tokens_used = 0
    if not ordered:
        answer = (
            "I could not find any relevant tickets matching your question. "
            "Please try rephrasing or provide more details."
        )
    else:
        system_prompt = (
            "You are a helpful support intelligence assistant. "
            "Answer the user's question STRICTLY based on the provided support ticket data. "
            "Cite ticket numbers (e.g., TCK-42) when referencing specific tickets. "
            "Do NOT fabricate information. "
            "If the tickets do not contain enough information to answer, say so clearly."
        )
        user_prompt = (
            f"Support ticket context:\n{context}\n\n"
            f"Question: {question}\n\n"
            "Please provide a concise, grounded answer based only on the tickets above."
        )

        try:
            client = _openai_client()
            completion = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=800,
                temperature=0.3,
            )
            answer = completion.choices[0].message.content.strip()
            tokens_used = completion.usage.total_tokens
        except ValueError as exc:
            # No API key – provide a context-based summary instead
            logger.warning("OpenAI not configured, returning context summary: %s", exc)
            answer = (
                f"[AI response unavailable – OpenAI API key not set]\n\n"
                f"Based on {len(ordered)} retrieved ticket(s):\n"
                + "\n".join(
                    f"• {t.get('ticket_number')}: {t.get('subject')} ({t.get('status')})"
                    for t in ordered
                )
            )
        except Exception as exc:
            logger.error("OpenAI call failed: %s", exc)
            answer = f"AI response generation failed: {exc}"

    latency_ms = round((time.time() - start_time) * 1000, 2)
    log_id = await _save_log(question, answer, ticket_ids, tokens_used, latency_ms, "query")

    return {
        "answer": answer,
        "citations": citations,
        "retrieved_count": len(ordered),
        "tokens_used": tokens_used,
        "latency_ms": latency_ms,
        "log_id": log_id,
    }


# ─── Similar Ticket Finder ────────────────────────────────────────────────────

async def find_similar_tickets(ticket_number: str, top_k: int = 5) -> dict:
    """Return tickets semantically similar to the given ticket."""
    db = get_database()
    source = await db.tickets.find_one({"ticket_number": ticket_number})
    if not source:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_number} not found.")

    query_text = source.get("description", "") + " " + (source.get("resolution") or "")
    similar = await search_similar_embeddings(query_text.strip(), top_k=top_k + 1)

    # Exclude the source ticket itself
    source_id = source["ticket_id"]
    results = [s for s in similar if s["ticket_id"] != source_id][:top_k]

    ticket_ids = [r["ticket_id"] for r in results]
    full_tickets: dict = {}
    async for t in db.tickets.find({"ticket_id": {"$in": ticket_ids}}):
        full_tickets[t["ticket_id"]] = t

    similar_out = [
        {
            "ticket_id": r["ticket_id"],
            "ticket_number": r["ticket_number"] or full_tickets.get(r["ticket_id"], {}).get("ticket_number", ""),
            "subject": full_tickets.get(r["ticket_id"], {}).get("subject", ""),
            "status": full_tickets.get(r["ticket_id"], {}).get("status", ""),
            "priority": full_tickets.get(r["ticket_id"], {}).get("priority", ""),
            "similarity_score": round(r["similarity_score"], 4),
            "description": (full_tickets.get(r["ticket_id"], {}).get("description") or "")[:200],
        }
        for r in results
    ]

    return {
        "source_ticket_number": ticket_number,
        "similar_tickets": similar_out,
    }


# ─── Trend Analysis ───────────────────────────────────────────────────────────

async def analyze_trends(days: int = 30, group_by: str = "subject") -> dict:
    """Aggregate ticket counts over the last N days, grouped by a field."""
    db = get_database()
    since = datetime.now(timezone.utc) - timedelta(days=days)

    allowed_fields = {"subject", "status", "priority"}
    if group_by not in allowed_fields:
        group_by = "subject"

    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": f"${group_by}", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]

    raw = []
    async for doc in db.tickets.aggregate(pipeline):
        raw.append({"label": doc["_id"] or "Unknown", "count": doc["count"]})

    total = sum(r["count"] for r in raw)
    trends = [
        {
            "label": r["label"],
            "count": r["count"],
            "percentage": round(r["count"] / total * 100, 1) if total else 0.0,
        }
        for r in raw
    ]

    # Brief text summary
    if trends:
        top = trends[0]
        summary = (
            f"In the last {days} days, {total} ticket(s) were created. "
            f"The most common {group_by} is '{top['label']}' "
            f"({top['count']} tickets, {top['percentage']}%)."
        )
    else:
        summary = f"No tickets found in the last {days} days."

    return {
        "period_days": days,
        "total_tickets": total,
        "trends": trends,
        "summary": summary,
    }


# ─── Resolution Summarizer ────────────────────────────────────────────────────

async def summarize_resolution(ticket_number: str) -> dict:
    """Generate an AI summary of how a ticket was resolved."""
    db = get_database()
    ticket = await db.tickets.find_one({"ticket_number": ticket_number})
    if not ticket:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_number} not found.")

    messages = ticket.get("messages", [])
    conversation = []
    for msg in messages:
        sender = msg.get("sender_type", "unknown")
        content = msg.get("message", "")
        if content:
            conversation.append(f"[{sender}]: {content}")

    conv_text = "\n".join(conversation[-20:])  # last 20 messages for context

    prompt_data = (
        f"Ticket: {ticket_number}\n"
        f"Subject: {ticket.get('subject', '')}\n"
        f"Status: {ticket.get('status', '')}\n"
        f"Description: {ticket.get('description', '')}\n\n"
        f"Conversation (last 20 messages):\n{conv_text}\n\n"
    )

    tokens_used = 0
    try:
        client = _openai_client()
        completion = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a support analytics assistant. "
                        "Summarize how this ticket was handled and resolved. "
                        "Extract 3-5 key resolution steps as a bullet list."
                    ),
                },
                {"role": "user", "content": prompt_data},
            ],
            max_tokens=600,
            temperature=0.2,
        )
        raw_answer = completion.choices[0].message.content.strip()
        tokens_used = completion.usage.total_tokens

        # Split into summary + steps (best-effort)
        lines = [l.strip() for l in raw_answer.split("\n") if l.strip()]
        step_lines = [l for l in lines if l.startswith(("•", "-", "*", "1.", "2.", "3."))]
        non_step = [l for l in lines if l not in step_lines]
        summary_text = " ".join(non_step[:3]) if non_step else raw_answer
        resolution_steps = step_lines or ["No explicit steps identified."]
    except ValueError as exc:
        logger.warning("OpenAI not configured: %s", exc)
        summary_text = (
            f"[AI unavailable] Ticket {ticket_number} ({ticket.get('subject')}) "
            f"has status '{ticket.get('status')}'. Configure OPENAI_API_KEY for detailed summaries."
        )
        resolution_steps = ["Configure OPENAI_API_KEY to enable resolution summaries."]
    except Exception as exc:
        logger.error("summarize_resolution failed: %s", exc)
        summary_text = f"Summary generation failed: {exc}"
        resolution_steps = []

    return {
        "ticket_number": ticket_number,
        "subject": ticket.get("subject", ""),
        "summary": summary_text,
        "resolution_steps": resolution_steps,
        "tokens_used": tokens_used,
    }


# ─── AI Logs ──────────────────────────────────────────────────────────────────

async def get_ai_logs(limit: int = 50, skip: int = 0) -> dict:
    """Retrieve AI query logs with pagination."""
    db = get_database()
    total = await db.ai_logs.count_documents({})
    cursor = db.ai_logs.find({}).sort("created_at", -1).skip(skip).limit(limit)
    logs = []
    async for doc in cursor:
        logs.append({
            "id": str(doc["_id"]),
            "query": doc.get("query", ""),
            "response_preview": (doc.get("response") or "")[:200],
            "retrieved_ticket_ids": doc.get("retrieved_ticket_ids", []),
            "tokens_used": doc.get("tokens_used", 0),
            "latency_ms": doc.get("latency_ms", 0.0),
            "helpful": doc.get("helpful"),
            "created_at": doc.get("created_at"),
        })
    return {"logs": logs, "total": total}


async def submit_feedback(log_id: str, helpful: bool, comment: Optional[str] = None) -> dict:
    """Update an ai_log document with user feedback."""
    db = get_database()
    try:
        oid = ObjectId(log_id)
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid log_id format.")

    result = await db.ai_logs.update_one(
        {"_id": oid},
        {"$set": {"helpful": helpful, "feedback_comment": comment}},
    )
    if result.matched_count == 0:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="AI log not found.")
    return {"message": "Feedback recorded.", "log_id": log_id}
