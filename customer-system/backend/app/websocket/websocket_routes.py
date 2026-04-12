import logging
import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from app.websocket.manager import ConnectionManager
from app.services.message_service import add_message, get_messages, mark_messages_read
from app.utils.jwt import decode_token
from app.config.db import get_database
from app.config.settings import settings
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket"])
manager = ConnectionManager()

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


# ── Issue 3: Internal endpoint — receives typing events forwarded from admin backend ──
@router.post("/internal/typing/{ticket_id}")
async def internal_typing(ticket_id: int, request: Request):
    """
    Called by the admin-support backend to forward a support engineer's typing
    event to customers connected on this backend's WebSocket.
    """
    body = await request.json()
    sender_type = body.get("sender_type", "support")
    is_typing = body.get("is_typing", False)
    await manager.broadcast_typing(ticket_id, sender_type, is_typing)
    return {"ok": True}


@router.websocket("/ws/{ticket_id}")
async def websocket_chat_endpoint(websocket: WebSocket, ticket_id: int):
    """
    Real-time chat for a ticket (customer side).
    Issue 3: Typing events are forwarded to the admin backend.
    Issue 2: Messages from support arrive via change stream → manager.broadcast(),
             not through this WS endpoint.
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

    await manager.connect(ticket_id, websocket)
    history = await get_messages(ticket_id)
    await manager.send_history(websocket, history)
    user_type = "customer" if sender_type == "customer" else "support"
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
                # Issue 3: Forward to admin backend so support engineers see "Customer is typing"
                await _forward_typing_to_admin(ticket_id, sender_type, data.get("is_typing", False))
                continue

            current_ticket = await db.tickets.find_one({"ticket_id": ticket_id}, {"status": 1})
            if current_ticket and current_ticket.get("status") == "closed":
                await websocket.send_json({
                    "type": "error",
                    "message": "This ticket is closed. Please raise a new ticket.",
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
            # Admin backend's change stream detects this DB write and
            # pushes the message to the connected support engineer (Issue 2)

    except WebSocketDisconnect:
        manager.disconnect(ticket_id, websocket)
        await manager.broadcast_typing(ticket_id, sender_type, False, exclude=None)


async def _forward_typing_to_admin(ticket_id: int, sender_type: str, is_typing: bool):
    """Issue 3: Forward customer typing event to admin-support backend's internal endpoint."""
    admin_url = getattr(settings, "ADMIN_BACKEND_URL", "")
    if not admin_url:
        return
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(
                f"{admin_url}/internal/typing/{ticket_id}",
                json={"sender_type": sender_type, "is_typing": is_typing},
            )
    except Exception:
        pass  # Non-critical — typing is best-effort
