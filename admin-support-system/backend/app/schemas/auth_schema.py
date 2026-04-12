from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# ── Request Schemas ───────────────────────────────────────────────────────────

class CustomerRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Full name")
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(..., min_length=6, description="Minimum 6 characters")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class CreateSupportEngineerRequest(BaseModel):
    """Schema for admin to create a new support engineer account."""
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    department: str = Field(..., min_length=2, max_length=100)
    role_id: int = Field(2, description="Role ID: 1=admin, 2=support")
    team: str = Field("team1", description="Team assignment e.g. team1, team2, team3")


# ── Response Schemas ──────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    name: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


# ── Profile Schemas ───────────────────────────────────────────────────────────

class CustomerResponse(BaseModel):
    customer_id: int
    name: str
    email: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    role: str = "customer"


class SupportEngineerResponse(BaseModel):
    support_id: int
    name: str
    email: str
    role_id: int
    department: str
    team: Optional[str] = ""
    is_active: bool
    is_online: bool
    last_seen: Optional[datetime] = None
    created_at: datetime


# ── Role Schema ───────────────────────────────────────────────────────────────

class RoleResponse(BaseModel):
    role_id: int
    role_name: str
    permissions: List[str]