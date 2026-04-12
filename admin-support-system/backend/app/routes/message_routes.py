from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth_dependency import get_current_user
from app.services.message_service import get_messages
from app.config.db import get_database

router = APIRouter(prefix="/tickets", tags=["Messages"])


@router.get("/{ticket_id}/messages")
async def list_messages(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    Returns all messages for a given ticket_id.
    Customers can only access their own tickets. Support/admin can access any.
    """
    db = get_database()
    ticket = await db.tickets.find_one({"ticket_id": ticket_id})
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    if current_user.get("role") == "customer":
        user_id = int(current_user["sub"].split("_")[-1])
        if ticket["customer_id"] != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    return await get_messages(ticket_id)
