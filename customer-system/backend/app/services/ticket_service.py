import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import HTTPException, status

from app.config.db import get_database
from app.constants.ticket_status import TicketStatus, SUBJECT_PRIORITY_MAP, PREDEFINED_SUBJECTS
from app.constants.roles import Role
from app.constants.websocket_events import WSEvent
from app.utils.shared import notification_queue

logger = logging.getLogger(__name__)

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def serialize_ticket(ticket: dict) -> dict:
    if ticket and "_id" in ticket:
        ticket["_id"] = str(ticket["_id"])
    return ticket

async def get_next_ticket_id() -> int:
    db = get_database()
    last = await db.tickets.find_one({}, sort=[("ticket_id", -1)], projection={"ticket_id": 1})
    return (last["ticket_id"] + 1) if last else 1

def generate_ticket_number(ticket_id: int) -> str:
    return f"TCK-{ticket_id}"

def extract_user_id(current_user: dict) -> int:
    sub = current_user.get("sub", "")
    try:
        return int(sub.split("_")[-1])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid user token format.")

async def _broadcast_status(ticket_id: int, status: str, ticket_number: str = ""):
    try:
        from app.websocket.websocket_routes import manager
        await manager.broadcast_status(ticket_id, status, ticket_number)
    except Exception:
        pass

def get_predefined_subjects() -> list:
    return PREDEFINED_SUBJECTS

async def create_ticket(current_user: dict, subject: str, description: str) -> dict:
    if subject not in SUBJECT_PRIORITY_MAP:
        raise HTTPException(status_code=400, detail=f"Invalid subject.")
    db = get_database()
    customer_id = extract_user_id(current_user)

    # Issue 6: Block duplicate subject if an open/in_progress ticket already exists
    existing = await db.tickets.find_one({
        "customer_id": customer_id,
        "subject": subject,
        "status": {"$in": [TicketStatus.OPEN, TicketStatus.IN_PROGRESS]},
    })
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"You already have an active ticket with this subject ({existing['ticket_number']}). "
                   f"Please wait for it to be resolved or closed before raising a new one.",
        )

    priority = SUBJECT_PRIORITY_MAP[subject]
    ticket_id = await get_next_ticket_id()
    ticket_number = generate_ticket_number(ticket_id)
    now = utcnow()
    system_message = {
        "message_id": 1,
        "sender_id": 0,
        "sender_type": "system",
        "sender_name": "Support Bot",
        "message": (
            "Thank you for contacting support. Your ticket has been received and "
            "will be reviewed shortly. Please wait while we connect you with an agent."
        ),
        "message_type": "text",
        "file_url": "",
        "timestamp": now,
    }
    ticket_doc = {
        "ticket_id": ticket_id,
        "ticket_number": ticket_number,
        "customer_id": customer_id,
        "assigned_engineer_id": None,
        "status": TicketStatus.OPEN,
        "priority": priority,
        "subject": subject,
        "description": description,
        "created_at": now,
        "updated_at": now,
        "last_message_at": now,
        "closed_at": None,
        "messages": [system_message],
    }
    await db.tickets.insert_one(ticket_doc)
    await notification_queue.put({
        "event": WSEvent.TICKET_CREATED,
        "ticket_id": ticket_id,
        "ticket_number": ticket_number,
        "subject": subject,
        "priority": priority,
        "customer_id": customer_id,
        "created_at": str(now),
    })
    return serialize_ticket(ticket_doc)

async def get_my_tickets(current_user: dict) -> list:
    db = get_database()
    customer_id = extract_user_id(current_user)
    cursor = db.tickets.find({"customer_id": customer_id}, {"messages": 0}).sort("created_at", -1)
    tickets = []
    async for t in cursor:
        tickets.append(serialize_ticket(t))
    return tickets

async def get_open_tickets() -> list:
    db = get_database()
    cursor = db.tickets.find({"status": TicketStatus.OPEN, "assigned_engineer_id": None}, {"messages": 0}).sort("created_at", 1)
    tickets = []
    async for t in cursor:
        tickets.append(serialize_ticket(t))
    return tickets

async def get_all_tickets(status_filter=None, priority_filter=None, assigned_engineer_id=None, current_user=None) -> list:
    db = get_database()
    query = {}
    if status_filter:
        query["status"] = status_filter
    if priority_filter:
        query["priority"] = priority_filter
    if assigned_engineer_id is not None:
        query["assigned_engineer_id"] = assigned_engineer_id

    # Team-based filtering: support engineers only see their team's tickets
    # Admin sees all tickets
    if current_user and current_user.get("role") not in ("admin",):
        user_team = current_user.get("team", "")
        if user_team:
            query["team"] = user_team

    cursor = db.tickets.find(query, {"messages": 0}).sort("created_at", -1)
    tickets = []
    async for t in cursor:
        tickets.append(serialize_ticket(t))
    return tickets

async def get_ticket_by_number(ticket_number: str, current_user: dict) -> dict:
    db = get_database()
    ticket = await db.tickets.find_one({"ticket_number": ticket_number})
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_number} not found.")
    if current_user.get("role") == Role.CUSTOMER:
        customer_id = extract_user_id(current_user)
        if ticket["customer_id"] != customer_id:
            raise HTTPException(status_code=403, detail="Access denied.")
    return serialize_ticket(ticket)

async def take_ticket(ticket_number: str, current_user: dict) -> dict:
    db = get_database()
    engineer_id = extract_user_id(current_user)
    engineer_team = current_user.get("team", "")
    result = await db.tickets.find_one_and_update(
        {"ticket_number": ticket_number, "status": TicketStatus.OPEN, "assigned_engineer_id": None},
        {"$set": {"assigned_engineer_id": engineer_id, "status": TicketStatus.IN_PROGRESS, "team": engineer_team, "updated_at": utcnow()}},
        return_document=True
    )
    if not result:
        existing = await db.tickets.find_one({"ticket_number": ticket_number})
        if not existing:
            raise HTTPException(status_code=404, detail=f"Ticket {ticket_number} not found.")
        raise HTTPException(status_code=409, detail="Ticket already taken or not open.")
    await notification_queue.put({
        "event": WSEvent.TICKET_TAKEN,
        "ticket_id": result["ticket_id"],
        "ticket_number": ticket_number,
        "engineer_id": engineer_id,
        "customer_id": result["customer_id"],
        "team": engineer_team,
    })
    await _broadcast_status(result["ticket_id"], TicketStatus.IN_PROGRESS, ticket_number)
    return serialize_ticket(result)

async def take_ticket_by_id(ticket_id: int, engineer_id: int, engineer_team: str = "") -> dict:
    db = get_database()
    result = await db.tickets.find_one_and_update(
        {"ticket_id": ticket_id, "status": TicketStatus.OPEN, "assigned_engineer_id": None},
        {"$set": {"assigned_engineer_id": engineer_id, "status": TicketStatus.IN_PROGRESS, "team": engineer_team, "updated_at": utcnow()}},
        return_document=True
    )
    if result:
        await notification_queue.put({
            "event": WSEvent.TICKET_TAKEN,
            "ticket_id": ticket_id,
            "ticket_number": result.get("ticket_number", ""),
            "engineer_id": engineer_id,
            "customer_id": result.get("customer_id"),
            "team": engineer_team,
        })
        await _broadcast_status(ticket_id, TicketStatus.IN_PROGRESS, result.get("ticket_number", ""))
    return serialize_ticket(result) if result else {}

async def resolve_ticket(ticket_number: str, current_user: dict) -> dict:
    db = get_database()
    ticket = await db.tickets.find_one({"ticket_number": ticket_number})
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_number} not found.")
    if ticket["status"] != TicketStatus.IN_PROGRESS:
        raise HTTPException(status_code=400, detail="Only in-progress tickets can be resolved.")
    if current_user.get("role") != Role.ADMIN:
        engineer_id = extract_user_id(current_user)
        if ticket["assigned_engineer_id"] != engineer_id:
            raise HTTPException(status_code=403, detail="Only the assigned engineer can resolve this ticket.")
    updated = await db.tickets.find_one_and_update(
        {"ticket_number": ticket_number},
        {"$set": {"status": TicketStatus.RESOLVED, "updated_at": utcnow()}},
        return_document=True
    )
    await notification_queue.put({
        "event": WSEvent.TICKET_RESOLVED, "ticket_id": ticket["ticket_id"],
        "ticket_number": ticket_number, "customer_id": ticket["customer_id"],
        "engineer_id": ticket.get("assigned_engineer_id"),
    })
    await _broadcast_status(ticket["ticket_id"], TicketStatus.RESOLVED, ticket_number)
    return serialize_ticket(updated)

async def close_ticket(ticket_number: str, current_user: dict) -> dict:
    db = get_database()
    ticket = await db.tickets.find_one({"ticket_number": ticket_number})
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_number} not found.")
    if ticket["status"] not in [TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED]:
        raise HTTPException(status_code=400, detail=f"Cannot close ticket with status '{ticket['status']}'.")
    if current_user.get("role") != Role.ADMIN:
        engineer_id = extract_user_id(current_user)
        if ticket["assigned_engineer_id"] != engineer_id:
            raise HTTPException(status_code=403, detail="Only the assigned engineer can close this ticket.")
    now = utcnow()
    updated = await db.tickets.find_one_and_update(
        {"ticket_number": ticket_number},
        {"$set": {"status": TicketStatus.CLOSED, "closed_at": now, "updated_at": now}},
        return_document=True
    )
    await notification_queue.put({
        "event": WSEvent.TICKET_CLOSED, "ticket_id": ticket["ticket_id"],
        "ticket_number": ticket_number, "customer_id": ticket["customer_id"],
        "engineer_id": ticket.get("assigned_engineer_id"),
    })
    await _broadcast_status(ticket["ticket_id"], TicketStatus.CLOSED, ticket_number)
    return serialize_ticket(updated)

async def reopen_ticket(ticket_number: str) -> dict:
    db = get_database()
    ticket = await db.tickets.find_one({"ticket_number": ticket_number})
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_number} not found.")
    if ticket["status"] != TicketStatus.RESOLVED:
        return serialize_ticket(ticket)
    updated = await db.tickets.find_one_and_update(
        {"ticket_number": ticket_number},
        {"$set": {"status": TicketStatus.IN_PROGRESS, "updated_at": utcnow()}},
        return_document=True
    )
    await notification_queue.put({
        "event": WSEvent.TICKET_REOPENED, "ticket_id": ticket["ticket_id"],
        "ticket_number": ticket_number, "engineer_id": ticket.get("assigned_engineer_id"),
        "customer_id": ticket["customer_id"],
    })
    await _broadcast_status(ticket["ticket_id"], TicketStatus.IN_PROGRESS, ticket_number)
    return serialize_ticket(updated)

AUTO_RESOLVE_INACTIVITY_MINUTES = 5
AUTO_RESOLVE_CHECK_INTERVAL_SECONDS = 30

async def auto_resolve_inactive_tickets():
    db = get_database()
    cutoff = utcnow() - timedelta(minutes=AUTO_RESOLVE_INACTIVITY_MINUTES)
    cursor = db.tickets.find({"status": TicketStatus.IN_PROGRESS, "messages": {"$exists": True, "$ne": []}})
    resolved_count = 0
    async for ticket in cursor:
        messages = ticket.get("messages", [])
        if not messages:
            continue
        last_msg = messages[-1]
        if last_msg.get("sender_type") not in ("support",):
            continue
        msg_time = last_msg.get("timestamp")
        if not msg_time:
            continue
        if isinstance(msg_time, str):
            try:
                msg_time = datetime.fromisoformat(msg_time.replace("Z", "+00:00"))
            except ValueError:
                continue
        if msg_time.tzinfo is None:
            msg_time = msg_time.replace(tzinfo=timezone.utc)
        if msg_time <= cutoff:
            await db.tickets.update_one(
                {"ticket_id": ticket["ticket_id"]},
                {"$set": {"status": TicketStatus.RESOLVED, "updated_at": utcnow()}}
            )
            await notification_queue.put({
                "event": WSEvent.TICKET_RESOLVED,
                "ticket_id": ticket["ticket_id"],
                "ticket_number": ticket.get("ticket_number", ""),
                "customer_id": ticket["customer_id"],
                "engineer_id": ticket.get("assigned_engineer_id"),
                "auto_resolved": True,
            })
            await _broadcast_status(ticket["ticket_id"], TicketStatus.RESOLVED, ticket.get("ticket_number", ""))
            resolved_count += 1
    if resolved_count:
        logger.info("Auto-resolved %d inactive ticket(s).", resolved_count)

async def start_auto_resolve_loop():
    while True:
        try:
            await auto_resolve_inactive_tickets()
        except Exception:
            logger.exception("Error in auto-resolve loop")
        await asyncio.sleep(AUTO_RESOLVE_CHECK_INTERVAL_SECONDS)
