"""
message_service.py
==================
Shared message operations used by both chat WebSocket handlers.

The 'first_message' notification is published to Redis so the admin backend's
NotificationManager can alert engineers about new activity on unattended tickets.
"""
import json
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.config.db import get_database

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _publish_notification(event: dict) -> None:
    from app.config.redis_client import get_redis
    try:
        await get_redis().publish("notifications", json.dumps(event, default=str))
    except Exception as exc:
        logger.warning("Failed to publish notification: %s", exc)


async def add_message(ticket_id: int, message: dict) -> int:
    """
    Append a message to the ticket's messages array.

    Side effects
    ------------
    - Fires a 'first_message' Redis notification when this is the very first
      customer message and no engineer is assigned yet.
    - Auto-reopens resolved tickets when a customer sends a new message.
    """
    db = get_database()
    ticket = await db.tickets.find_one({"ticket_id": ticket_id})
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found.",
        )

    existing_messages = ticket.get("messages", [])
    message["message_id"] = len(existing_messages) + 1

    is_first_message = len(existing_messages) == 0
    already_attended = ticket.get("assigned_engineer_id") is not None

    result = await db.tickets.update_one(
        {"ticket_id": ticket_id},
        {
            "$push": {"messages": message},
            "$set": {"last_message_at": utcnow(), "updated_at": utcnow()},
        },
    )

    # Auto-reopen resolved ticket when customer sends a new message
    if message.get("sender_type") == "customer" and ticket.get("status") == "resolved":
        from app.services.ticket_service import reopen_ticket
        await reopen_ticket(ticket.get("ticket_number", ""))

    # Alert engineers about the first customer message on an unattended ticket
    if is_first_message and not already_attended:
        await _publish_notification({
            "event": "first_message",
            "ticket_id": ticket_id,
            "ticket_number": ticket.get("ticket_number", ""),
            "subject": ticket.get("subject", ""),
            "priority": ticket.get("priority", ""),
            "sender_type": message.get("sender_type"),
            "message_preview": message.get("message", "")[:120],
        })

    return result.modified_count


async def get_messages(ticket_id: int) -> list:
    """Return the full messages array for a ticket."""
    db = get_database()
    ticket = await db.tickets.find_one({"ticket_id": ticket_id})
    return ticket.get("messages", []) if ticket else []


async def mark_messages_read(ticket_id: int, user_type: str) -> None:
    """Mark all messages as read for the given side (customer or support)."""
    db = get_database()
    field = "is_read_by_support" if user_type == "support" else "is_read_by_customer"
    await db.tickets.update_one(
        {"ticket_id": ticket_id},
        {"$set": {f"messages.$[].{field}": True}},
    )