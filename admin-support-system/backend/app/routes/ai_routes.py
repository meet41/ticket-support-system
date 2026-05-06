from typing import List

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth_dependency import get_current_user
from app.dependencies.role_dependency import require_roles
from app.schemas.ai_schema import (
    AIQueryRequest,
    AIQueryResponse,
    AILogOut,
    BulkEmbedRequest,
    BulkEmbedResponse,
    FeedbackRequest,
    ResolutionSummaryResponse,
    SimilarTicketItem,
    SimilarTicketsResponse,
    TrendsRequest,
    TrendsResponse,
)
from app.services import rag_service
from app.services.embedding_service import embed_ticket_by_number, embed_all_tickets
from app.config.db import get_database

router = APIRouter(prefix="/ai", tags=["AI"])


# ─────────────────────────────────────────────
# POST /ai/query  — ask a question via RAG
# ─────────────────────────────────────────────


@router.post("/query", response_model=AIQueryResponse)
async def ai_query(
    payload: AIQueryRequest,
    current_user: dict = Depends(require_roles(["support", "admin"])),
):
    """
    Answer a natural language question using the RAG pipeline.
    Searches historical tickets (semantic + keyword), constructs a context
    prompt, and calls OpenAI GPT for a grounded response with ticket citations.
    """
    user_id = current_user.get("sub", "unknown")
    user_role = current_user.get("role", "unknown")
    result = await rag_service.query_rag(
        query=payload.query,
        user_id=user_id,
        user_role=user_role,
    )
    return result


# ─────────────────────────────────────────────
# POST /ai/similar-tickets/{ticket_number}
# ─────────────────────────────────────────────


@router.post("/similar-tickets/{ticket_number}", response_model=SimilarTicketsResponse)
async def similar_tickets(
    ticket_number: str,
    top_k: int = Query(default=5, ge=1, le=20),
    current_user: dict = Depends(require_roles(["support", "admin"])),
):
    """
    Find tickets semantically similar to the given ticket.
    Useful for detecting duplicates or related issues.
    """
    results = await rag_service.find_similar_tickets(ticket_number, top_k)
    similar = [
        SimilarTicketItem(
            ticket_id=r["ticket_id"],
            ticket_number=r.get("ticket_number", ""),
            score=round(r["score"], 4),
            subject=r.get("metadata", {}).get("subject") or r.get("subject"),
            status=r.get("metadata", {}).get("status") or r.get("status"),
            priority=r.get("metadata", {}).get("priority") or r.get("priority"),
        )
        for r in results
    ]
    return {"ticket_number": ticket_number, "similar": similar}


# ─────────────────────────────────────────────
# POST /ai/analyze-trends
# ─────────────────────────────────────────────


@router.post("/analyze-trends", response_model=TrendsResponse)
async def analyze_trends(
    payload: TrendsRequest,
    current_user: dict = Depends(require_roles(["admin"])),
):
    """
    Generate trend analytics from MongoDB aggregations.
    Returns status/priority distributions, top subjects, daily volume,
    and average resolution time — no ClickHouse required.
    """
    return await rag_service.analyze_trends(days=payload.days)


# ─────────────────────────────────────────────
# POST /ai/summarize-resolution/{ticket_number}
# ─────────────────────────────────────────────


@router.post(
    "/summarize-resolution/{ticket_number}", response_model=ResolutionSummaryResponse
)
async def summarize_resolution(
    ticket_number: str,
    current_user: dict = Depends(require_roles(["support", "admin"])),
):
    """
    Use AI to extract a concise summary of the resolution pattern
    for a resolved or closed ticket.
    """
    return await rag_service.summarize_resolution(ticket_number)


# ─────────────────────────────────────────────
# GET /ai/logs  — AI query history
# ─────────────────────────────────────────────


@router.get("/logs", response_model=List[AILogOut])
async def get_ai_logs(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(require_roles(["admin"])),
):
    """View recent AI query history with performance metrics (admin only)."""
    db = get_database()
    logs = []
    async for doc in db.ai_logs.find().sort("created_at", -1).limit(limit):
        logs.append(
            AILogOut(
                log_id=str(doc["_id"]),
                query=doc.get("query", ""),
                user_id=doc.get("user_id", ""),
                user_role=doc.get("user_role", ""),
                retrieved_ticket_numbers=doc.get("retrieved_ticket_numbers", []),
                response=doc.get("response", ""),
                token_usage=doc.get("token_usage", {}),
                latency_ms=doc.get("latency_ms", 0.0),
                feedback=doc.get("feedback"),
                created_at=doc.get("created_at"),
            )
        )
    return logs


# ─────────────────────────────────────────────
# POST /ai/feedback  — submit feedback on a log
# ─────────────────────────────────────────────


@router.post("/feedback")
async def submit_feedback(
    payload: FeedbackRequest,
    current_user: dict = Depends(require_roles(["support", "admin"])),
):
    """
    Record user feedback (helpful / not_helpful) for an AI response.
    Used for monitoring and future model improvement.
    """
    db = get_database()
    try:
        oid = ObjectId(payload.log_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid log_id format.")

    result = await db.ai_logs.update_one(
        {"_id": oid}, {"$set": {"feedback": payload.feedback}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="AI log not found.")

    return {"message": "Feedback recorded.", "log_id": payload.log_id}


# ─────────────────────────────────────────────
# POST /ai/embed-ticket/{ticket_number}  — embed one ticket
# ─────────────────────────────────────────────


@router.post("/embed-ticket/{ticket_number}")
async def embed_single_ticket(
    ticket_number: str,
    current_user: dict = Depends(require_roles(["admin"])),
):
    """Generate / refresh embeddings for a single ticket (admin only)."""
    n = await embed_ticket_by_number(ticket_number)
    if n == 0:
        raise HTTPException(
            status_code=404, detail=f"Ticket {ticket_number} not found or no text to embed."
        )
    return {"ticket_number": ticket_number, "chunks_embedded": n}


# ─────────────────────────────────────────────
# POST /ai/bulk-embed  — embed all existing tickets
# ─────────────────────────────────────────────


@router.post("/bulk-embed", response_model=BulkEmbedResponse)
async def bulk_embed(
    payload: BulkEmbedRequest,
    current_user: dict = Depends(require_roles(["admin"])),
):
    """
    Bulk-embed all tickets in the database.
    By default skips tickets that already have embeddings.
    Set force_reembed=true to re-embed everything.
    """
    if payload.force_reembed:
        db = get_database()
        await db.ticket_embeddings.delete_many({})

    result = await embed_all_tickets()
    return BulkEmbedResponse(
        **result,
        message=f"Bulk embedding complete. {result['embedded']} tickets embedded.",
    )
