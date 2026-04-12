import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from datetime import datetime, timezone, timedelta
from app.config.db import connect_to_mongo, close_mongo_connection, get_database
from app.routes import auth_routes, ticket_routes, message_routes
from app.websocket.websocket_routes import router as websocket_router, notification_manager, manager
from app.services.ticket_service import start_auto_resolve_loop
from app.utils.shared import notification_queue
from app.constants.websocket_events import WSEvent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL = 2  # seconds


async def _poll_ticket_changes():
    """
    Issue 1 & 2: Poll MongoDB every 2 s for:
    - New tickets (created_at > last_check)  → push to notification_queue (Issue 1)
    - New messages from customers            → broadcast to connected engineers (Issue 2)

    Works with standalone MongoDB (no replica set required).
    """
    db = get_database()
    last_check = datetime.now(timezone.utc)
    # Track last seen message count per ticket to detect new messages
    ticket_msg_counts: dict[int, int] = {}

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            now = datetime.now(timezone.utc)

            # ── Issue 1: New tickets ──────────────────────────────────────────
            async for ticket in db.tickets.find(
                {"created_at": {"$gt": last_check}},
                {"ticket_id": 1, "ticket_number": 1, "subject": 1,
                 "priority": 1, "customer_id": 1, "created_at": 1},
            ):
                await notification_queue.put({
                    "event": WSEvent.TICKET_CREATED,
                    "ticket_id": ticket["ticket_id"],
                    "ticket_number": ticket.get("ticket_number", ""),
                    "subject": ticket.get("subject", ""),
                    "priority": ticket.get("priority", ""),
                    "customer_id": ticket.get("customer_id"),
                    "created_at": str(ticket.get("created_at", "")),
                })
                logger.info("Poll: new ticket %s → notification_queue", ticket.get("ticket_number"))

            # ── Issue 2: New messages from customers ─────────────────────────
            async for ticket in db.tickets.find(
                {"last_message_at": {"$gt": last_check - timedelta(seconds=POLL_INTERVAL + 1)}},
                {"ticket_id": 1, "messages": 1},
            ):
                tid = ticket["ticket_id"]
                messages = ticket.get("messages", [])
                prev_count = ticket_msg_counts.get(tid, len(messages))

                new_msgs = messages[prev_count:]
                for msg in new_msgs:
                    if msg.get("sender_type") == "customer":
                        await manager.broadcast(tid, jsonable_encoder(msg))

                ticket_msg_counts[tid] = len(messages)

            last_check = now

        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("Poll error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    notification_manager.start()
    auto_resolve_task = asyncio.create_task(start_auto_resolve_loop())
    poll_task = asyncio.create_task(_poll_ticket_changes())
    logger.info("Admin-support backend started.")
    try:
        yield
    finally:
        auto_resolve_task.cancel()
        poll_task.cancel()
        for t in [auto_resolve_task, poll_task]:
            try: await t
            except asyncio.CancelledError: pass
        notification_manager.stop()
        await close_mongo_connection()


app = FastAPI(title="Ticket Support — Admin & Support API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "https://ticket-system-admin.vercel.app",
    ],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(ticket_routes.router)
app.include_router(message_routes.router)
app.include_router(websocket_router)

@app.get("/", tags=["Health"])
async def root():
    return {"message": "Admin/Support API is running.", "docs": "/docs"}

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}