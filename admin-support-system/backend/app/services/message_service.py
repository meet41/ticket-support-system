from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.config.db import get_database
from app.utils.shared import notification_queue


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def serialize_ticket(ticket: dict) -> dict:
    if ticket and "_id" in ticket:
        ticket["_id"] = str(ticket["_id"])
    return ticket


# ─────────────────────────────────────────────
# Add Message to Ticket
# ─────────────────────────────────────────────

async def add_message(ticket_id: int, message: dict) -> int:
    """
    Appends a message to the ticket's messages array.
    Fires a 'first_message' notification if this is the very first message
    and the ticket has no assigned engineer yet.
    """
    db = get_database()
    ticket = await db.tickets.find_one({"ticket_id": ticket_id})

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found."
        )

    # Auto-generate message_id server-side
    existing_messages = ticket.get("messages", [])
    message["message_id"] = len(existing_messages) + 1

    is_first_message = len(existing_messages) == 0
    already_attended = ticket.get("assigned_engineer_id") is not None

    result = await db.tickets.update_one(
        {"ticket_id": ticket_id},
        {
            "$push": {"messages": message},
            "$set": {
                "last_message_at": utcnow(),
                "updated_at": utcnow(),
            },
        },
    )

    # Auto-reopen resolved ticket when customer sends a new message
    if message.get("sender_type") == "customer" and ticket.get("status") == "resolved":
        from app.services.ticket_service import reopen_ticket
        await reopen_ticket(ticket.get("ticket_number", ""))

    # Fire notification only on first message when no engineer is assigned yet
    if is_first_message and not already_attended:
        await notification_queue.put({
            "event": "first_message",
            "ticket_id": ticket_id,
            "ticket_number": ticket.get("ticket_number", ""),
            "subject": ticket.get("subject", ""),
            "priority": ticket.get("priority", ""),
            "sender_type": message.get("sender_type"),
            "message_preview": message.get("message", "")[:120],
        })

    return result.modified_count


# ─────────────────────────────────────────────
# Get Messages for a Ticket
# ─────────────────────────────────────────────

async def get_messages(ticket_id: int) -> list:
    """Returns the messages array of a ticket."""
    db = get_database()
    ticket = await db.tickets.find_one({"ticket_id": ticket_id})
    if ticket:
        return ticket.get("messages", [])
    return []


async def mark_messages_read(ticket_id: int, user_type: str):
    """Mark all messages as read for the given user type."""
    db = get_database()
    field = "is_read_by_support" if user_type == "support" else "is_read_by_customer"
    await db.tickets.update_one(
        {"ticket_id": ticket_id},
        {"$set": {f"messages.$[].{field}": True}}
    )
