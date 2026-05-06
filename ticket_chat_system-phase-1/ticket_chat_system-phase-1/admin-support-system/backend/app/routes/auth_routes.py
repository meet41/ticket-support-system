from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime, timezone

from app.schemas.auth_schema import (
    CustomerRegisterRequest,
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    AccessTokenResponse,
    CustomerResponse,
    SupportEngineerResponse,
    MessageResponse,
    CreateSupportEngineerRequest,
)
from app.services.auth_service import (
    register_customer,
    authenticate_customer,
    authenticate_support_engineer,
    create_support_engineer,
    create_tokens_for_user,
    refresh_access_token,
    revoke_refresh_token,
    cleanup_expired_tokens,
    set_engineer_offline,
    set_engineer_online
)
from app.dependencies.auth_dependency import get_current_user
from app.dependencies.role_dependency import require_roles
from app.config.db import get_database

router = APIRouter(prefix="/auth", tags=["Auth"])


# ─────────────────────────────────────────────
# Customer Routes
# ─────────────────────────────────────────────

@router.post("/customer/register", response_model=MessageResponse, status_code=201)
async def customer_register(data: CustomerRegisterRequest):
    """
    Register a new customer account.
    Only customers self-register. Support engineers are created by admin.
    """
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
    """
    Login as a customer.
    Returns access token (15 min) and refresh token (7 days).
    """
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


# ─────────────────────────────────────────────
# Staff Routes (Support Engineers & Admin)
# ─────────────────────────────────────────────

@router.post("/staff/login", response_model=TokenResponse)
async def staff_login(data: LoginRequest):
    """
    Login for support engineers and admins.
    Accounts are pre-created — no public registration.
    Sets engineer is_online = True on login.
    """
    try:
        engineer = await authenticate_support_engineer(
            email=data.email, password=data.password
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    if not engineer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
   
    role_name = engineer.get("role_name", "support")
    access_token, refresh_token = await create_tokens_for_user(
        user_id=f"support_{engineer['support_id']}",
        user_type="support_engineer",
        role=role_name,
        name=engineer["name"],
        email=engineer["email"],
        team=engineer.get("team", ""),
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": role_name,
        "name": engineer["name"],
    }


@router.post("/staff/create", status_code=201)
async def create_staff(
    details: CreateSupportEngineerRequest,
    current_user: dict = Depends(require_roles(["admin"]))
):
    """
    Admin creates a new support engineer account.
    Only admin can call this endpoint.
    """
    try:
        engineer = await create_support_engineer(details)
        return {
            "success": True,
            "message": "Support engineer created successfully.",
            "data": engineer,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/staff/refresh", response_model=AccessTokenResponse)
async def staff_refresh(data: RefreshTokenRequest):
    """Get a new access token using a valid refresh token."""
    try:
        new_token = await refresh_access_token(data.refresh_token)
        return {"access_token": new_token, "token_type": "bearer"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/staff/logout", response_model=MessageResponse)
async def staff_logout(
    data: RefreshTokenRequest,
    current_user: dict = Depends(require_roles(["support", "admin"])),
):
    """
    Logout support engineer.
    Marks engineer as offline, deletes refresh token from DB.
    """
    if current_user.get("user_type") == "support_engineer":
        await set_engineer_offline(current_user["email"])

    deleted = await revoke_refresh_token(data.refresh_token)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token not found. Already logged out.",
        )
    await cleanup_expired_tokens()
    return {"message": "Logged out successfully. You are now offline."}


@router.get("/staff/me", response_model=SupportEngineerResponse)
async def get_staff_profile(
    current_user: dict = Depends(require_roles(["support", "admin"]))
):
    """Get current support engineer/admin's profile."""
    db = get_database()
    support_id = int(current_user["sub"].split("_")[1])  # "support_101" -> 101
    engineer = await db.support_engineers.find_one({"support_id": support_id})
    if not engineer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engineer not found.")
    return {
        "support_id": engineer["support_id"],
        "name": engineer["name"],
        "email": engineer["email"],
        "role_id": engineer["role_id"],
        "department": engineer["department"],
        "team": engineer.get("team", ""),
        "is_active": engineer["is_active"],
        "is_online": engineer["is_online"],
        "last_seen": engineer.get("last_seen"),
        "created_at": engineer["created_at"],
    }


# ─────────────────────────────────────────────
# Admin — Lookup Endpoints
# ─────────────────────────────────────────────

@router.get("/admin/engineers")
async def list_all_engineers(
    current_user: dict = Depends(require_roles(["admin"])),
):
    """Admin: list all support engineers for dashboard assignment view."""
    db = get_database()
    roles_map = {}
    async for r in db.roles.find():
        roles_map[r["role_id"]] = r["role_name"]

    engineers = []
    async for eng in db.support_engineers.find({}, {"password": 0, "_id": 0}):
        eng["role_name"] = roles_map.get(eng.get("role_id"), "support")
        engineers.append(eng)
    return engineers


@router.get("/admin/customers")
async def list_all_customers(
    current_user: dict = Depends(require_roles(["admin"])),
):
    """Admin: list all customers for dashboard views."""
    db = get_database()
    customers = []
    async for cust in db.customers.find({}, {"password": 0, "_id": 0}):
        customers.append(cust)
    return customers