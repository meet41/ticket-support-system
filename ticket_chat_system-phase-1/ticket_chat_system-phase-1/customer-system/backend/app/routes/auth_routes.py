from fastapi import APIRouter, HTTPException, status, Depends

from app.schemas.auth_schema import (
    CustomerRegisterRequest,
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    AccessTokenResponse,
    CustomerResponse,
    MessageResponse,
)
from app.services.auth_service import (
    register_customer,
    authenticate_customer,
    create_tokens_for_user,
    refresh_access_token,
    revoke_refresh_token,
    cleanup_expired_tokens,
)
from app.dependencies.auth_dependency import get_current_user
from app.config.db import get_database

router = APIRouter(prefix="/auth", tags=["Auth"])


# ─────────────────────────────────────────────
# Customer Routes (Customer backend only)
# ─────────────────────────────────────────────

@router.post("/customer/register", response_model=MessageResponse, status_code=201)
async def customer_register(data: CustomerRegisterRequest):
    """Register a new customer account."""
    try:
        customer = await register_customer(
            name=data.name,
            email=data.email,
            password=data.password,
        )
        return {"message": f"Account created successfully. Welcome, {customer['name']}!"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/customer/login", response_model=TokenResponse)
async def customer_login(data: LoginRequest):
    """Login as a customer. Returns access token (15 min) and refresh token (7 days)."""
    try:
        customer = await authenticate_customer(email=data.email, password=data.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    access_token, refresh_token = await create_tokens_for_user(
        user_id=f"customer_{customer['customer_id']}",
        user_type="customer",
        role="customer",
        name=customer["name"],
        email=customer["email"],
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": "customer",
        "name": customer["name"],
    }


@router.post("/customer/refresh", response_model=AccessTokenResponse)
async def customer_refresh(data: RefreshTokenRequest):
    """Get a new access token using a valid refresh token."""
    try:
        new_token = await refresh_access_token(data.refresh_token)
        return {"access_token": new_token, "token_type": "bearer"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/customer/logout", response_model=MessageResponse)
async def customer_logout(
    data: RefreshTokenRequest,
    current_user: dict = Depends(get_current_user),
):
    """Logout by deleting refresh token from DB. Client must also clear local storage."""
    deleted = await revoke_refresh_token(data.refresh_token)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token not found. Already logged out.",
        )
    await cleanup_expired_tokens()
    return {"message": "Logged out successfully."}


@router.get("/customer/me", response_model=CustomerResponse)
async def get_customer_profile(current_user: dict = Depends(get_current_user)):
    """Get current customer's profile. Requires valid access token."""
    if current_user.get("role") != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Customer accounts only.",
        )
    db = get_database()
    customer_id = int(current_user["sub"].split("_")[1])  # "customer_1" -> 1
    customer = await db.customers.find_one({"customer_id": customer_id})
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    return {
        "customer_id": customer["customer_id"],
        "name": customer["name"],
        "email": customer["email"],
        "is_active": customer["is_active"],
        "created_at": customer["created_at"],
        "last_login": customer.get("last_login"),
        "role": "customer",
    }