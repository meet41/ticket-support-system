import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.db import connect_to_mongo, close_mongo_connection
from app.config.redis_client import connect_to_redis, close_redis
from app.routes import auth_routes, ticket_routes, message_routes
from app.websocket.websocket_routes import router as websocket_router
from app.websocket.chat_manager import chat_manager
from app.websocket.notification_manager import notification_manager
from app.services.ticket_service import start_auto_resolve_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    await connect_to_redis()

    # Start Redis-backed managers
    chat_manager.start()
    notification_manager.start()

    auto_resolve_task = asyncio.create_task(start_auto_resolve_loop())
    logger.info("Admin-support backend started.")

    try:
        yield
    finally:
        auto_resolve_task.cancel()
        try:
            await auto_resolve_task
        except asyncio.CancelledError:
            pass

        chat_manager.stop()
        notification_manager.stop()
        await close_redis()
        await close_mongo_connection()
        logger.info("Admin-support backend shut down.")


app = FastAPI(
    title="Ticket Support — Admin & Support API",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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