from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ---------- Request Schemas ----------

class TicketCreateRequest(BaseModel):
    """Customer sends this when creating a ticket."""
    subject: str = Field(..., description="Must be one of the predefined subjects")
    description: str = Field(..., min_length=10, max_length=1000)


class TicketFilterParams(BaseModel):
    """Optional filters for GET /tickets/all (support engineers & admin)."""
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_engineer_id: Optional[int] = None


# ---------- Embedded Message Schema ----------

class MessageOut(BaseModel):
    message_id: int
    sender_id: int
    sender_type: str                # "customer" | "support"
    message: str
    message_type: str               # "text" | "file" | "image"
    file_url: Optional[str] = None
    timestamp: datetime


# ---------- Response Schemas ----------

class TicketSummaryOut(BaseModel):
    """Lightweight ticket info for list endpoints."""
    ticket_id: int
    ticket_number: str
    customer_id: int
    status: str
    priority: str
    subject: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    assigned_engineer_id: Optional[int] = None


class TicketDetailOut(BaseModel):
    """Full ticket info including messages for GET /tickets/{ticket_number}."""
    ticket_id: int
    ticket_number: str
    customer_id: int
    assigned_engineer_id: Optional[int] = None
    status: str
    priority: str
    subject: str
    description: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    messages: List[MessageOut] = []


class TicketCreateResponse(BaseModel):
    """Returned to customer after ticket creation."""
    ticket_number: str
    subject: str
    priority: str
    status: str
    created_at: datetime
    message: str = "Ticket created successfully. Our support team has been notified."


class SubjectsListResponse(BaseModel):
    """Returned for frontend dropdown population."""
    subjects: List[str]
