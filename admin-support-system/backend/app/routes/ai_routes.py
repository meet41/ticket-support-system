"""
AI / RAG Routes
---------------
Endpoints for the AI-powered support intelligence features.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from app.dependencies.auth_dependency import get_current_user
from app.dependencies.role_dependency import require_roles
from app.schemas.ai_schema import (
    AIQueryRequest, AIQueryResponse,
    SimilarTicketsRequest, SimilarTicketsResponse,
    TrendAnalysisRequest, TrendAnalysisResponse,
    ResolutionSummaryResponse,
    AILogsResponse,
    FeedbackRequest, FeedbackResponse,
)
from app.services import rag_service

router = APIRouter(prefix="/ai", tags=["AI Intelligence"])


# ─────────────────────────────────────────────
# POST /ai/query — Ask a RAG question
# ─────────────────────────────────────────────

@router.post("/query", response_model=AIQueryResponse)
async def ai_query(
    payload: AIQueryRequest,
    current_user: dict = Depends(require_roles(["support", "admin"])),
):
    """
    Ask a natural-language question about historical tickets.
    Returns an AI-generated answer grounded in real ticket data with citations.
    """
    return await rag_service.rag_query(
        question=payload.question,
        top_k=payload.top_k,
        filters=payload.filters,
    )


# ─────────────────────────────────────────────
# POST /ai/similar-tickets/{ticket_number}
# ─────────────────────────────────────────────

@router.post("/similar-tickets/{ticket_number}", response_model=SimilarTicketsResponse)
async def similar_tickets(
    ticket_number: str,
    payload: SimilarTicketsRequest = SimilarTicketsRequest(),
    current_user: dict = Depends(require_roles(["support", "admin"])),
):
    """
    Find tickets semantically similar to the specified ticket.
    Useful for identifying duplicates or related issues.
    """
    return await rag_service.find_similar_tickets(
        ticket_number=ticket_number,
        top_k=payload.top_k,
    )


# ─────────────────────────────────────────────
# POST /ai/analyze-trends
# ─────────────────────────────────────────────

@router.post("/analyze-trends", response_model=TrendAnalysisResponse)
async def analyze_trends(
    payload: TrendAnalysisRequest = TrendAnalysisRequest(),
    current_user: dict = Depends(require_roles(["support", "admin"])),
):
    """
    Analyze ticket trends over a configurable time window.
    Groups results by subject, status, or priority.
    """
    return await rag_service.analyze_trends(
        days=payload.days,
        group_by=payload.group_by,
    )


# ─────────────────────────────────────────────
# POST /ai/summarize-resolution/{ticket_number}
# ─────────────────────────────────────────────

@router.post("/summarize-resolution/{ticket_number}", response_model=ResolutionSummaryResponse)
async def summarize_resolution(
    ticket_number: str,
    current_user: dict = Depends(require_roles(["support", "admin"])),
):
    """
    Generate an AI summary of how a ticket was resolved,
    including key resolution steps extracted from the conversation.
    """
    return await rag_service.summarize_resolution(ticket_number=ticket_number)


# ─────────────────────────────────────────────
# GET /ai/logs — AI query logs
# ─────────────────────────────────────────────

@router.get("/logs", response_model=AILogsResponse)
async def get_logs(
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    current_user: dict = Depends(require_roles(["admin"])),
):
    """
    Retrieve AI query logs with performance metrics.
    Admin only.
    """
    return await rag_service.get_ai_logs(limit=limit, skip=skip)


# ─────────────────────────────────────────────
# POST /ai/feedback — Submit feedback on an AI response
# ─────────────────────────────────────────────

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    payload: FeedbackRequest,
    current_user: dict = Depends(require_roles(["support", "admin"])),
):
    """
    Mark an AI response as helpful or not helpful.
    Used to improve retrieval quality over time.
    """
    return await rag_service.submit_feedback(
        log_id=payload.log_id,
        helpful=payload.helpful,
        comment=payload.comment,
    )
