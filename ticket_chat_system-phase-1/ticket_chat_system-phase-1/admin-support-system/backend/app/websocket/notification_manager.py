"""
NotificationManager (admin-support backend)
===========================================
Manages WebSocket connections for support engineers and fans out
ticket-lifecycle events received from the Redis 'notifications' channel.

Publishers
----------
  ticket_service.py  — ticket_created, ticket_taken, ticket_resolved,
                        ticket_closed, ticket_reopened, auto_resolved
  message_service.py — first_message

Team-based routing
------------------
  ticket_created  → all engineers  (anyone can pick it up)
  everything else → same-team engineers, or all if no team context
"""
import asyncio
import json
import logging
from typing import Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

NOTIFICATIONS_CHANNEL = "notifications"


class NotificationManager:
    def __init__(self) -> None:
        self._connections: Dict[WebSocket, str] = {}   # ws -> team
        self._listen_task: asyncio.Task | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the Redis listener. Called once at app startup."""
        if self._listen_task is None or self._listen_task.done():
            self._listen_task = asyncio.create_task(
                self._listen(), name="notification-redis-listener"
            )

    def stop(self) -> None:
        """Cancel the listener. Called at app shutdown."""
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()

    # ── Connection management ─────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, team: str = "") -> None:
        await websocket.accept()
        self._connections[websocket] = team
        logger.debug(
            "Notification WS connected  team=%s  total=%d", team, len(self._connections)
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)
        logger.debug("Notification WS disconnected  total=%d", len(self._connections))

    # ── Per-connection listener ───────────────────────────────────────────────

    async def listen(self, websocket: WebSocket, user: dict) -> None:
        """
        Keep the WS alive and handle incoming engineer actions.
        Supported actions:
          { "action": "attend", "ticket_id": <int> }  — claim an open ticket
        """
        engineer_id = int(user["sub"].split("_")[-1])
        engineer_team = user.get("team", "")
        engineer_email = user.get("email", "")

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                    if data.get("action") == "attend":
                        ticket_id = data.get("ticket_id")
                        if ticket_id:
                            from app.services.ticket_service import take_ticket_by_id
                            await take_ticket_by_id(int(ticket_id), engineer_id, engineer_team)
                except (json.JSONDecodeError, Exception) as exc:
                    logger.debug("Notification WS receive error: %s", exc)
        except WebSocketDisconnect:
            await self.disconnect(websocket)
            if engineer_email:
                await self._mark_engineer_offline(engineer_email)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _recipients(self, event: str, team: str) -> Set[WebSocket]:
        if event == "ticket_created":
            return set(self._connections)
        if team:
            matched = {ws for ws, t in self._connections.items() if t == team}
            return matched or set(self._connections)
        return set(self._connections)

    async def _mark_engineer_offline(self, email: str) -> None:
        try:
            from app.config.db import get_database
            from datetime import datetime, timezone
            db = get_database()
            await db.support_engineers.update_one(
                {"email": email},
                {"$set": {"is_online": False, "last_seen": datetime.now(timezone.utc)}},
            )
            logger.debug("Marked engineer %s offline on WS disconnect.", email)
        except Exception as exc:
            logger.debug("Failed to mark engineer offline: %s", exc)

    # ── Redis listener ────────────────────────────────────────────────────────

    async def _listen(self) -> None:
        """Subscribe to the Redis notifications channel and fan-out to engineers."""
        from app.config.redis_client import get_redis
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(NOTIFICATIONS_CHANNEL)
        logger.info("Notification listener subscribed to channel: %s", NOTIFICATIONS_CHANNEL)

        try:
            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue
                try:
                    message: dict = json.loads(raw["data"])
                except json.JSONDecodeError as exc:
                    logger.warning("Malformed notification payload: %s", exc)
                    continue
                await self._fan_out(message)
        except asyncio.CancelledError:
            logger.info("Notification listener cancelled.")
        except Exception as exc:
            logger.exception("Notification listener crashed: %s", exc)
        finally:
            try:
                await pubsub.unsubscribe(NOTIFICATIONS_CHANNEL)
                await pubsub.aclose()
            except Exception:
                pass

    async def _fan_out(self, message: dict) -> None:
        if not self._connections:
            return
        event = message.get("event", "")
        team = message.get("team", "")
        recipients = self._recipients(event, team)
        payload = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in list(recipients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


# Singleton shared across the application
notification_manager = NotificationManager()