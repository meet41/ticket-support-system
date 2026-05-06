from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


class Message(BaseModel):
    message_id: int
    sender_id: int
    sender_type: str        # customer | support
    message: str
    message_type: str       # text | file | image
    file_url: Optional[str] = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_read_by_customer: bool = False
    is_read_by_support: bool = False
