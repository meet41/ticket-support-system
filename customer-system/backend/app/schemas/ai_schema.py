from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ─── Request Schemas ───────────────────────────────────────────────────────────

class AIQueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000, description="Natural language question")
    top_k: int = Field(5, ge=1, le=20, description="Number of tickets to retrieve")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional MongoDB filter dict")


class SimilarTicketsRequest(BaseModel):
    top_k: int = Field(5, ge=1, le=20)


class TrendAnalysisRequest(BaseModel):
    days: int = Field(30, ge=1, le=365, description="Look-back window in days")
    group_by: str = Field("subject", description="Field to group by: subject|status|priority")


class FeedbackRequest(BaseModel):
    log_id: str = Field(..., description="ID of the ai_logs document")
    helpful: bool
    comment: Optional[str] = Field(None, max_length=500)


# ─── Response Schemas ──────────────────────────────────────────────────────────

class TicketCitation(BaseModel):
    ticket_id: int
    ticket_number: str
    subject: str
    relevance_score: float


class AIQueryResponse(BaseModel):
    answer: str
    citations: List[TicketCitation]
    retrieved_count: int
    tokens_used: int
    latency_ms: float
    log_id: str


class SimilarTicketOut(BaseModel):
    ticket_id: int
    ticket_number: str
    subject: str
    status: str
    priority: str
    similarity_score: float
    description: Optional[str] = None


class SimilarTicketsResponse(BaseModel):
    source_ticket_number: str
    similar_tickets: List[SimilarTicketOut]


class TrendItem(BaseModel):
    label: str
    count: int
    percentage: float


class TrendAnalysisResponse(BaseModel):
    period_days: int
    total_tickets: int
    trends: List[TrendItem]
    summary: str


class ResolutionSummaryResponse(BaseModel):
    ticket_number: str
    subject: str
    summary: str
    resolution_steps: List[str]
    tokens_used: int


class AILogOut(BaseModel):
    id: str
    query: str
    response_preview: str
    retrieved_ticket_ids: List[int]
    tokens_used: int
    latency_ms: float
    helpful: Optional[bool] = None
    created_at: datetime


class AILogsResponse(BaseModel):
    logs: List[AILogOut]
    total: int


class FeedbackResponse(BaseModel):
    message: str
    log_id: str
