import logging
import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from app.websocket.manager import ConnectionManager
from app.websocket.notification_manager import NotificationManager
from app.services.message_service import add_message, get_messages, mark_messages_read
from app.utils.jwt import decode_token
from app.config.db import get_database
from app.config.settings import settings
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket"])

manager = ConnectionManager()
notification_manager = NotificationManager()

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


# ── Issue 3: Internal endpoint — receives typing events forwarded from customer backend ──
@router.post("/internal/typing/{ticket_id}")
async def internal_typing(ticket_id: int, request: Request):
    """
    Called by the customer backend to forward a customer's typing event to
    support engineers connected on this backend's WebSocket.
    """
    body = await request.json()
    sender_type = body.get("sender_type", "customer")
    is_typing = body.get("is_typing", False)
    await manager.broadcast_typing(ticket_id, sender_type, is_typing)
    return {"ok": True}


@router.websocket("/ws/{ticket_id}")
async def websocket_chat_endpoint(websocket: WebSocket, ticket_id: int):
    """
    Real-time chat for a ticket (admin/support side).

    Issue 5: Only the assigned engineer (or admin) may send messages.
             Other engineers connect in read-only mode.
    Issue 3: Typing events are forwarded to the customer backend.
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

    if role == "customer" and ticket["customer_id"] != user_id:
        await websocket.close(code=4003, reason="Access denied")
        return

    sender_type = "customer" if user.get("user_type") == "customer" else "support"
    sender_name = user.get("name", "")

    # Issue 5: Determine if this engineer is the assigned one (admins always can send)
    assigned_engineer_id = ticket.get("assigned_engineer_id")
    is_assigned = role == "admin" or (sender_type == "support" and assigned_engineer_id == user_id)

    await manager.connect(ticket_id, websocket)
    history = await get_messages(ticket_id)
    await manager.send_history(websocket, history)

    # Issue 5: Inform the client about read-only status right away
    await websocket.send_json({
        "type": "access_info",
        "read_only": not is_assigned,
        "assigned_engineer_id": assigned_engineer_id,
        "user_id": user_id,
    })

    user_type = "support" if sender_type == "support" else "customer"
    await mark_messages_read(ticket_id, user_type)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")

            if msg_type == "typing":
                current_ticket = await db.tickets.find_one({"ticket_id": ticket_id}, {"status": 1})
                if current_ticket and current_ticket.get("status") == "closed":
                    continue
                await manager.broadcast_typing(
                    ticket_id=ticket_id,
                    sender_type=sender_type,
                    is_typing=data.get("is_typing", False),
                    exclude=websocket,
                )
                # Issue 3: Forward to customer backend so the customer sees "Agent is typing"
                await _forward_typing_to_customer(ticket_id, sender_type, data.get("is_typing", False))
                continue

            # Issue 5: Re-fetch assignment and block non-assigned engineers
            current_ticket = await db.tickets.find_one(
                {"ticket_id": ticket_id}, {"status": 1, "assigned_engineer_id": 1}
            )
            current_assigned = current_ticket.get("assigned_engineer_id") if current_ticket else None

            if sender_type == "support" and role != "admin" and current_assigned != user_id:
                await websocket.send_json({
                    "type": "error",
                    "message": "Only the assigned engineer can send messages. You have read-only access.",
                })
                continue

            if current_ticket and current_ticket.get("status") == "closed":
                await websocket.send_json({
                    "type": "error",
                    "message": "This ticket is closed.",
                })
                continue

            message = {
                "sender_id": user_id,
                "sender_type": sender_type,
                "sender_name": sender_name,
                "message": data.get("message", ""),
                "message_type": data.get("message_type", "text"),
                "file_url": data.get("file_url", ""),
                "timestamp": datetime.now(timezone.utc),
                "is_read_by_customer": sender_type == "customer",
                "is_read_by_support": sender_type == "support",
            }
            await add_message(ticket_id, message)
            await manager.broadcast(ticket_id, message)
            # Customer backend's change stream detects this DB write and
            # pushes the message to the connected customer (Issue 2)

    except WebSocketDisconnect:
        manager.disconnect(ticket_id, websocket)
        await manager.broadcast_typing(ticket_id, sender_type, False, exclude=None)


async def _forward_typing_to_customer(ticket_id: int, sender_type: str, is_typing: bool):
    """Issue 3: Forward support typing event to customer backend's internal endpoint."""
    customer_url = getattr(settings, "CUSTOMER_BACKEND_URL", "")
    if not customer_url:
        return
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(
                f"{customer_url}/internal/typing/{ticket_id}",
                json={"sender_type": sender_type, "is_typing": is_typing},
            )
    except Exception:
        pass  # Non-critical — typing is best-effort


@router.websocket("/ws/notifications/live")
async def websocket_notification_endpoint(websocket: WebSocket):
    """
    Support engineers receive real-time ticket notifications here.
    Can send: { "action": "attend", "ticket_id": <int> }
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
