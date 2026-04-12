from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.auth_service import get_current_user_from_token

# HTTPBearer extracts token from "Authorization: Bearer <token>" header
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    FastAPI dependency that validates the access token.
    Returns the decoded token payload:
    {
        "sub": "customer_1" | "support_101",
        "user_type": "customer" | "support_engineer",
        "role": "customer" | "support" | "admin",
        "name": str,
        "email": str
    }

    Usage:
        @router.get("/protected")
        async def route(user: dict = Depends(get_current_user)):
            ...
    """
    try:
        user_payload = await get_current_user_from_token(credentials.credentials)
        return user_payload
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )