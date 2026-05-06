from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from jose import JWTError

from app.config.db import get_database
from app.utils.hash import hash_password, verify_password
from app.utils.jwt import create_access_token, create_refresh_token, decode_token
from app.config.settings import settings
from app.schemas.auth_schema import CreateSupportEngineerRequest


# ─────────────────────────────────────────────
# Helper: Auto-increment ID (find-max approach)
# ─────────────────────────────────────────────


async def get_next_id(collection_name: str, id_field: str) -> int:
    """
    Get the next auto-increment ID for a collection.
    Finds the current maximum value and returns max + 1.
    """
    db = get_database()
    last_doc = await db[collection_name].find_one(
        {}, sort=[(id_field, -1)], projection={id_field: 1}
    )
    return (last_doc[id_field] + 1) if last_doc else 1


# ─────────────────────────────────────────────
# Customer Auth
# ─────────────────────────────────────────────

async def register_customer(name: str, email: str, password: str) -> dict:
    """
    Register a new customer.
    Checks for duplicate email, hashes password, inserts into customers collection.
    """
    db = get_database()

    existing = await db.customers.find_one({"email": email})
    if existing:
        raise ValueError("Email already registered.")

    customer_id = await get_next_id("customers", "customer_id")
    now = datetime.now(timezone.utc)

    customer_doc = {
        "customer_id": customer_id,
        "name": name,
        "email": email,
        "password": hash_password(password),
        "is_active": True,
        "created_at": now,
        "last_login": None,
    }

    await db.customers.insert_one(customer_doc)
    return customer_doc


async def authenticate_customer(email: str, password: str) -> Optional[dict]:
    """
    Authenticate a customer by email and password.
    Returns the customer document if valid, None if wrong password.
    Raises ValueError if account is deactivated.
    """
    db = get_database()
    customer = await db.customers.find_one({"email": email})

    if not customer:
        return None
    if not customer.get("is_active"):
        raise ValueError("Account is deactivated. Contact support.")
    if not verify_password(password, customer["password"]):
        return None

    await db.customers.update_one(
        {"email": email},
        {"$set": {"last_login": datetime.now(timezone.utc)}}
    )
    return customer


# ─────────────────────────────────────────────
# Support Engineer Auth
# ─────────────────────────────────────────────

async def authenticate_support_engineer(email: str, password: str) -> Optional[dict]:
    """
    Authenticate a support engineer or admin.
    Fetches role name from roles collection and sets is_online on login.
    """
    db = get_database()
    engineer = await db.support_engineers.find_one({"email": email})
    if not engineer:
        return None
    if not engineer.get("is_active"):
        raise ValueError("Account is deactivated. Contact admin.")
    if not verify_password(password, engineer["password"]):
        return None

    # Fetch role name from roles collection
    role_doc = await db.roles.find_one({"role_id": engineer["role_id"]})
    role_name = role_doc["role_name"] if role_doc else "support"
    # Mark engineer as online
    await db.support_engineers.update_one(
        {"email": email},
        {"$set": {"last_seen": datetime.now(timezone.utc), "is_online":True}}
    ) 

    engineer["role_name"] = role_name
    return engineer


async def create_support_engineer(details: CreateSupportEngineerRequest) -> dict:
    """
    Admin creates a new support engineer account.
    Checks email uniqueness across both customers and support_engineers collections.
    """
    db = get_database()

    existing = await db.support_engineers.find_one({"email": details.email})
    if existing:
        raise ValueError(f"Email '{details.email}' is already registered as a support engineer.")

    existing_customer = await db.customers.find_one({"email": details.email})
    if existing_customer:
        raise ValueError(f"Email '{details.email}' is already registered as a customer.")

    support_id = await get_next_id("support_engineers", "support_id")
    now = datetime.now(timezone.utc)

    engineer_doc = {
        "support_id": support_id,
        "name": details.name,
        "email": details.email,
        "password": hash_password(details.password),
        "role_id": details.role_id,
        "department": details.department,
        "team": details.team,
        "is_active": True,
        "is_online": False,
        "last_seen": None,
        "created_at": now,
    }

    result = await db.support_engineers.insert_one(engineer_doc)
    engineer_doc["_id"] = str(result.inserted_id)
    return engineer_doc


# ─────────────────────────────────────────────
# Token Service
# ─────────────────────────────────────────────

async def create_tokens_for_user(
    user_id: str,
    user_type: str,
    role: str,
    name: str,
    email: str,
    team: str = "",
) -> Tuple[str, str]:
    """
    Create and store access + refresh tokens.
    user_id format: "customer_1" or "support_101"
    Returns (access_token, refresh_token).
    """
    token_data = {
        "sub": user_id,
        "user_type": user_type,
        "role": role,
        "name": name,
        "email": email,
        "team": team,
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    db = get_database()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    await db.refresh_tokens.insert_one({
        "token": refresh_token,
        "user_id": user_id,
        "user_type": user_type,
        "role": role,
        "created_at": now,
        "expires_at": expires_at,
    })

    return access_token, refresh_token


async def refresh_access_token(refresh_token: str) -> str:
    """
    Validate refresh token and issue a new access token.
    Token must exist in DB (deleted on logout = invalid).
    """
    db = get_database()

    try:
        payload = decode_token(refresh_token)
    except Exception:
        raise ValueError("Invalid or expired refresh token.")

    if payload.get("type") != "refresh":
        raise ValueError("Token type mismatch. Expected refresh token.")

    token_doc = await db.refresh_tokens.find_one({"token": refresh_token})
    if not token_doc:
        raise ValueError("Refresh token not found or already used after logout.")

    token_data = {
        "sub": payload["sub"],
        "user_type": payload["user_type"],
        "role": payload["role"],
        "name": payload["name"],
        "email": payload["email"],
        "team": payload.get("team", ""),
    }
    return create_access_token(token_data)


async def revoke_refresh_token(refresh_token: str) -> bool:
    """Delete a refresh token from DB on logout. Returns True if found and deleted."""
    db = get_database()
    result = await db.refresh_tokens.delete_one({"token": refresh_token})
    return result.deleted_count > 0


async def revoke_all_tokens_for_user(user_id: str) -> int:
    """Delete ALL refresh tokens for a user. Used for forced logout / password change."""
    db = get_database()
    result = await db.refresh_tokens.delete_many({"user_id": user_id})
    return result.deleted_count


async def cleanup_expired_tokens() -> int:
    """Delete all expired refresh tokens. Call opportunistically on logout."""
    db = get_database()
    now = datetime.now(timezone.utc)
    result = await db.refresh_tokens.delete_many({"expires_at": {"$lt": now}})
    return result.deleted_count


async def get_current_user_from_token(access_token: str) -> dict:
    """Decode access token and return user payload. Used in auth dependency."""
    try:
        payload = decode_token(access_token)
    except Exception:
        raise ValueError("Invalid or expired access token.")

    if payload.get("type") != "access":
        raise ValueError("Token type mismatch. Expected access token.")

    return payload


# ─────────────────────────────────────────────
# Support Engineer Offline Status
# ─────────────────────────────────────────────

async def set_engineer_offline(email: str) -> None:
    """Mark support engineer as offline. Called on logout."""
    db = get_database()
    await db.support_engineers.update_one(
        {"email": email},
        {"$set": {"is_online": False, "last_seen": datetime.now(timezone.utc)}}
    )


async def set_engineer_online(email: str) -> None:
    """Mark support engineer as offline. Called on logout."""
    db = get_database()
    await db.support_engineers.update_one(
        {"email": email},
        {"$set": {"is_online": True, "last_seen": datetime.now(timezone.utc)}}
    )