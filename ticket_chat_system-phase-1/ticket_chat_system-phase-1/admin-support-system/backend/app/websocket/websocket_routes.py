"""
WebSocket routes — admin-support backend
=========================================
  /ws/{ticket_id}           — real-time chat for support engineers & admins
  /ws/notifications/live    — real-time ticket-lifecycle notifications

All message delivery (including cross-service to the customer backend) is handled
via Redis pub/sub inside ChatManager — no polling, no HTTP forwarding.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket.chat_manager import chat_manager
from app.websocket.notification_manager import notification_manager
from app.services.message_service import add_message, get_messages, mark_messages_read
from app.utils.jwt import decode_token
from app.config.db import get_database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket"])


# ── Auth helper ───────────────────────────────────────────────────────────────

async def _authenticate_ws(websocket: WebSocket) -> dict | None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return None
    try:
        payload = decode_token(token)
    except Exception:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return None
    if payload.get("type") != "access":
        await websocket.close(code=1008, reason="Invalid token type")
        return None
    return payload


# ── Chat WebSocket ────────────────────────────────────────────────────────────

@router.websocket("/ws/{ticket_id}")
async def websocket_chat_endpoint(websocket: WebSocket, ticket_id: int):
    """
    Real-time chat for a ticket (admin / support side).

    Access levels
    -------------
    - Assigned engineer or admin: full read-write
    - Non-assigned support engineer: read-only (viewer)

    Cross-service delivery
    ----------------------
    Messages published to Redis chat:ticket:{id} are automatically received
    by the customer backend and forwarded to the connected customer — no
    separate polling or HTTP forwarding required.
    """
    user = await _authenticate_ws(websocket)
    if user is None:
        return

    db = get_database()
    ticket = await db.tickets.find_one({"ticket_id": ticket_id})
    if not ticket:
        await websocket.close(code=4004, reason="Ticket not found")
        return

    role = user.get("role")
    user_id = int(user["sub"].split("_")[-1])
    sender_type = "support"
    sender_name = user.get("name", "")

    assigned_engineer_id = ticket.get("assigned_engineer_id")
    is_assigned = role == "admin" or assigned_engineer_id == user_id

    conn_id = await chat_manager.connect(ticket_id, websocket)

    # Send chat history and access level immediately on connect
    history = await get_messages(ticket_id)
    await chat_manager.send_history(websocket, history)
    await websocket.send_json({
        "type": "access_info",
        "read_only": not is_assigned,
        "assigned_engineer_id": assigned_engineer_id,
        "user_id": user_id,
    })
    await mark_messages_read(ticket_id, "support")

    # Announce viewer presence if non-assigned support engineer joins
    if not is_assigned:
        await chat_manager.publish_raw(ticket_id, {
            "type": "viewer_joined",
            "viewer_id": user_id,
            "viewer_name": sender_name,
            "ticket_id": ticket_id,
        })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")

            if msg_type == "typing":
                current = await db.tickets.find_one({"ticket_id": ticket_id}, {"status": 1})
                if current and current.get("status") == "closed":
                    continue
                await chat_manager.publish_typing(
                    ticket_id=ticket_id,
                    sender_type=sender_type,
                    is_typing=data.get("is_typing", False),
                    exclude_conn_id=conn_id,
                )
                continue

            # Reload ticket state before every message
            current = await db.tickets.find_one(
                {"ticket_id": ticket_id},
                {"status": 1, "assigned_engineer_id": 1},
            )
            current_assigned = current.get("assigned_engineer_id") if current else None

            if role != "admin" and current_assigned != user_id:
                await websocket.send_json({
                    "type": "error",
                    "message": "Only the assigned engineer can send messages. You have read-only access.",
                })
                continue

            if current and current.get("status") == "closed":
                await websocket.send_json({"type": "error", "message": "This ticket is closed."})
                continue

            message = {
                "sender_id": user_id,
                "sender_type": sender_type,
                "sender_name": sender_name,
                "message": data.get("message", ""),
                "message_type": data.get("message_type", "text"),
                "file_url": data.get("file_url", ""),
                "timestamp": datetime.now(timezone.utc),
                "is_read_by_customer": False,
                "is_read_by_support": True,
            }
            await add_message(ticket_id, message)
            # Redis delivery reaches the customer backend automatically
            await chat_manager.publish_message(ticket_id, message)

    except WebSocketDisconnect:
        chat_manager.disconnect(ticket_id, websocket)
        # Clear typing indicator on disconnect
        await chat_manager.publish_typing(ticket_id, sender_type, False)
        if not is_assigned:
            await chat_manager.publish_raw(ticket_id, {
                "type": "viewer_left",
                "viewer_id": user_id,
                "viewer_name": sender_name,
                "ticket_id": ticket_id,
            })


# ── Notifications WebSocket ───────────────────────────────────────────────────

@router.websocket("/ws/notifications/live")
async def websocket_notification_endpoint(websocket: WebSocket):
    """
    Support engineers and admins connect here to receive real-time
    ticket-lifecycle notifications from the Redis notifications channel.

    Supported incoming actions:
      { "action": "attend", "ticket_id": <int> }  — claim an open ticket
    """
    user = await _authenticate_ws(websocket)
    if user is None:
        return

    if user.get("role") not in ("support", "admin"):
        await websocket.close(code=4003, reason="Access denied. Support/admin only.")
        return

    engineer_team = user.get("team", "")
    await notification_manager.connect(websocket, team=engineer_team)
    await notification_manager.listen(websocket, user)