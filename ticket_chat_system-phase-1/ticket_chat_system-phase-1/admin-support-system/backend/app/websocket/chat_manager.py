"""
ChatManager
===========
Manages per-ticket WebSocket connections and delivers messages cross-service
via Redis pub/sub — no MongoDB polling needed.

Channel layout
--------------
  chat:ticket:<ticket_id>   — all chat events for a ticket
                              (message, status_update, typing, access_info, viewer_*)

Flow
----
  1. Any backend publishes an event to  chat:ticket:<id>  via Redis.
  2. ALL backends that have active WS connections for that ticket receive
     the event from their own Redis subscription and fan it out locally.

This replaces both the old in-process ConnectionManager and the polling loop
that queried MongoDB every 2 seconds for new messages.
"""
import asyncio
import json
import logging
from typing import Dict
from uuid import uuid4

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder

logger = logging.getLogger(__name__)

_CHANNEL_PREFIX = "chat:ticket:"
_PATTERN = f"{_CHANNEL_PREFIX}*"


def _channel(ticket_id: int) -> str:
    return f"{_CHANNEL_PREFIX}{ticket_id}"


class ChatManager:
    def __init__(self) -> None:
        # ticket_id -> {websocket: conn_id}
        self._connections: Dict[int, Dict[WebSocket, str]] = {}
        self._listen_task: asyncio.Task | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the Redis listener. Called once at app startup."""
        if self._listen_task is None or self._listen_task.done():
            self._listen_task = asyncio.create_task(
                self._listen(), name="chat-redis-listener"
            )

    def stop(self) -> None:
        """Cancel the Redis listener. Called at app shutdown."""
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()

    # ── Connection management ─────────────────────────────────────────────────

    async def connect(self, ticket_id: int, websocket: WebSocket) -> str:
        """Accept WS and register the connection. Returns a unique conn_id."""
        await websocket.accept()
        conn_id = str(uuid4())
        self._connections.setdefault(ticket_id, {})[websocket] = conn_id
        logger.debug(
            "Chat WS connected  ticket=%s  conn=%s  local_total=%d",
            ticket_id, conn_id, len(self._connections[ticket_id]),
        )
        return conn_id

    def disconnect(self, ticket_id: int, websocket: WebSocket) -> None:
        bucket = self._connections.get(ticket_id)
        if bucket:
            bucket.pop(websocket, None)
            if not bucket:
                del self._connections[ticket_id]
        logger.debug("Chat WS disconnected  ticket=%s", ticket_id)

    # ── Direct send (for history / access_info on connect) ───────────────────

    async def send_history(self, websocket: WebSocket, messages: list) -> None:
        await websocket.send_json({"type": "history", "messages": jsonable_encoder(messages)})

    # ── Publishing to Redis ───────────────────────────────────────────────────

    async def publish_message(self, ticket_id: int, message: dict) -> None:
        """Publish a chat message to Redis; all backends deliver it to their WS clients."""
        payload = {"type": "message", "message": jsonable_encoder(message)}
        await self._publish(ticket_id, payload)

    async def publish_status(self, ticket_id: int, status: str, ticket_number: str = "") -> None:
        """Publish a ticket status-change event to Redis."""
        payload = {
            "type": "status_update",
            "ticket_id": ticket_id,
            "ticket_number": ticket_number,
            "status": status,
        }
        await self._publish(ticket_id, payload)

    async def publish_typing(
        self,
        ticket_id: int,
        sender_type: str,
        is_typing: bool,
        exclude_conn_id: str | None = None,
    ) -> None:
        """
        Publish a typing indicator to Redis.
        exclude_conn_id prevents the originating connection from receiving its own event.
        """
        payload = {
            "type": "typing",
            "sender_type": sender_type,
            "is_typing": is_typing,
            "exclude_conn_id": exclude_conn_id,
        }
        await self._publish(ticket_id, payload)

    async def publish_raw(self, ticket_id: int, payload: dict) -> None:
        """Publish any arbitrary payload (viewer_joined, viewer_left, access_info, …)."""
        await self._publish(ticket_id, payload)

    async def _publish(self, ticket_id: int, payload: dict) -> None:
        from app.config.redis_client import get_redis
        try:
            await get_redis().publish(_channel(ticket_id), json.dumps(payload, default=str))
        except Exception as exc:
            logger.warning("Redis publish failed for ticket %s: %s", ticket_id, exc)

    # ── Redis listener ────────────────────────────────────────────────────────

    async def _listen(self) -> None:
        """
        Pattern-subscribe to  chat:ticket:*  and dispatch incoming events to
        locally connected WebSocket clients.
        """
        from app.config.redis_client import get_redis
        pubsub = get_redis().pubsub()
        await pubsub.psubscribe(_PATTERN)
        logger.info("Chat listener subscribed to pattern: %s", _PATTERN)

        try:
            async for raw in pubsub.listen():
                if raw["type"] != "pmessage":
                    continue
                channel: str = raw["channel"]
                try:
                    ticket_id = int(channel.removeprefix(_CHANNEL_PREFIX))
                    payload: dict = json.loads(raw["data"])
                except (ValueError, json.JSONDecodeError) as exc:
                    logger.warning("Malformed chat event on %s: %s", channel, exc)
                    continue
                await self._fan_out(ticket_id, payload)
        except asyncio.CancelledError:
            logger.info("Chat listener cancelled.")
        except Exception as exc:
            logger.exception("Chat listener crashed: %s", exc)
        finally:
            try:
                await pubsub.punsubscribe(_PATTERN)
                await pubsub.aclose()
            except Exception:
                pass

    async def _fan_out(self, ticket_id: int, payload: dict) -> None:
        """Deliver payload to all local WS clients for the given ticket."""
        bucket = self._connections.get(ticket_id)
        if not bucket:
            return

        exclude_conn_id: str | None = payload.get("exclude_conn_id")
        dead: list[WebSocket] = []

        for ws, conn_id in list(bucket.items()):
            if exclude_conn_id and conn_id == exclude_conn_id:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ticket_id, ws)


# Singleton shared across the application
chat_manager = ChatManager()