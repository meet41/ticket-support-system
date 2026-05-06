"""
AI / RAG Routes — Customer Backend
------------------------------------
Limited AI endpoints available to customers.
"""
from fastapi import APIRouter, Depends

from app.dependencies.auth_dependency import get_current_user
from app.dependencies.role_dependency import require_roles
from app.schemas.ai_schema import (
    AIQueryRequest, AIQueryResponse,
    SimilarTicketsRequest, SimilarTicketsResponse,
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
    current_user: dict = Depends(require_roles(["customer"])),
):
    """
    Ask a question about support tickets.
    Returns an AI-generated answer grounded in ticket data.
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
    current_user: dict = Depends(require_roles(["customer"])),
):
    """
    Find tickets similar to the specified ticket.
    Customers can use this to check if their issue has been seen before.
    """
    return await rag_service.find_similar_tickets(
        ticket_number=ticket_number,
        top_k=payload.top_k,
    )


# ─────────────────────────────────────────────
# POST /ai/feedback
# ─────────────────────────────────────────────

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    payload: FeedbackRequest,
    current_user: dict = Depends(require_roles(["customer"])),
):
    """Submit feedback on an AI response."""
    return await rag_service.submit_feedback(
        log_id=payload.log_id,
        helpful=payload.helpful,
        comment=payload.comment,
    )
