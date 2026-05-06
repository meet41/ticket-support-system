# from fastapi import Depends, HTTPException, status
# from typing import List
# from ticket_chat_system.app.dependencies.auth_dependency import get_current_user
# from ticket_chat_system.app.constants.roles import Role


# def require_roles(allowed_roles: List[str]):
#     """
#     Factory dependency — pass allowed roles, returns a FastAPI dependency.

#     Usage:
#         @router.get("/tickets/open")
#         async def get_open_tickets(
#             user=Depends(require_roles([Role.SUPPORT, Role.ADMIN]))
#         ):
#     """
#     async def role_checker(current_user: dict = Depends(get_current_user)):
#         if current_user["role"] not in allowed_roles:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail=f"Access denied. Required roles: {allowed_roles}"
#             )
#         return current_user

#     return role_checker
from fastapi import Depends, HTTPException, status
from typing import List
from app.dependencies.auth_dependency import get_current_user


def require_roles(allowed_roles: List[str]):
    """
    RBAC dependency factory for ticket routes.
    Pass a list of allowed roles — returns a FastAPI dependency.

    Usage:
        @router.get("/tickets/open")
        async def get_open_tickets(
            user=Depends(require_roles(["support", "admin"]))
        ):
    """
    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {allowed_roles}"
            )
        return current_user

    return role_checker