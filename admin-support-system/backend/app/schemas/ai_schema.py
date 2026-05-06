from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Request schemas
# ─────────────────────────────────────────────


class AIQueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000, description="Natural language question")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of tickets to retrieve")


class FeedbackRequest(BaseModel):
    log_id: str = Field(..., description="AI log document ID")
    feedback: str = Field(..., pattern="^(helpful|not_helpful)$", description="helpful or not_helpful")


class TrendsRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=365, description="Look-back period in days")


class BulkEmbedRequest(BaseModel):
    force_reembed: bool = Field(
        default=False,
        description="If true, re-embed tickets that already have embeddings",
    )


# ─────────────────────────────────────────────
# Response schemas
# ─────────────────────────────────────────────


class AIQueryResponse(BaseModel):
    log_id: str
    query: str
    response: str
    sources: List[str] = Field(default_factory=list)
    latency_ms: float
    token_usage: Dict[str, Any] = Field(default_factory=dict)


class SimilarTicketItem(BaseModel):
    ticket_id: int
    ticket_number: str
    score: float
    subject: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None


class SimilarTicketsResponse(BaseModel):
    ticket_number: str
    similar: List[SimilarTicketItem]


class ResolutionSummaryResponse(BaseModel):
    ticket_number: str
    summary: str


class TrendsResponse(BaseModel):
    period_days: int
    total_tickets: int
    status_distribution: Dict[str, int]
    priority_distribution: Dict[str, int]
    top_subjects: List[Dict[str, Any]]
    daily_volume: List[Dict[str, Any]]
    avg_resolution_hours: Optional[float]


class AILogOut(BaseModel):
    log_id: str
    query: str
    user_id: str
    user_role: str
    retrieved_ticket_numbers: List[str]
    response: str
    token_usage: Dict[str, Any]
    latency_ms: float
    feedback: Optional[str]
    created_at: datetime


class BulkEmbedResponse(BaseModel):
    total: int
    embedded: int
    skipped: int
    errors: int
    message: str
