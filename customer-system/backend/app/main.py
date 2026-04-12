import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from datetime import datetime, timezone, timedelta
from app.config.db import connect_to_mongo, close_mongo_connection, get_database
from app.routes import auth_routes, ticket_routes, message_routes
from app.websocket.websocket_routes import router as websocket_router, manager
from app.services.ticket_service import start_auto_resolve_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL = 2  # seconds


async def _poll_ticket_changes():
    """
    Issue 2: Poll MongoDB every 2 s for new messages written by support engineers
    (via the admin-support backend) and broadcast them to connected customers.

    Works with standalone MongoDB (no replica set required).
    """
    db = get_database()
    ticket_msg_counts: dict[int, int] = {}

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            async for ticket in db.tickets.find(
                {"last_message_at": {"$gt": datetime.now(timezone.utc) - timedelta(seconds=POLL_INTERVAL + 1)}},
                {"ticket_id": 1, "messages": 1},
            ):
                tid = ticket["ticket_id"]
                messages = ticket.get("messages", [])
                prev_count = ticket_msg_counts.get(tid, len(messages))

                new_msgs = messages[prev_count:]
                for msg in new_msgs:
                    if msg.get("sender_type") == "support":
                        await manager.broadcast(tid, jsonable_encoder(msg))

                ticket_msg_counts[tid] = len(messages)

        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("Customer poll error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    auto_resolve_task = asyncio.create_task(start_auto_resolve_loop())
    poll_task = asyncio.create_task(_poll_ticket_changes())
    logger.info("Customer backend started.")
    try:
        yield
    finally:
        auto_resolve_task.cancel()
        poll_task.cancel()
        for t in [auto_resolve_task, poll_task]:
            try: await t
            except asyncio.CancelledError: pass
        await close_mongo_connection()


app = FastAPI(title="Ticket Support — Customer API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://ticket-system-customer.vercel.app",
    ],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(ticket_routes.router)
app.include_router(message_routes.router)
app.include_router(websocket_router)

@app.get("/", tags=["Health"])
async def root():
    return {"message": "Customer API is running.", "docs": "/docs"}

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}