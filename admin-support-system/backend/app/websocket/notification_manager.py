import asyncio
import json
import logging
from typing import Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

from app.utils.shared import notification_queue

logger = logging.getLogger(__name__)


class NotificationManager:
    """
    Manages WebSocket connections for support engineers and broadcasts
    ticket-lifecycle notifications from the shared queue.

    Team-based routing:
        - ticket_created  → broadcast to ALL engineers (anyone can take it)
        - ticket_taken / ticket_resolved / ticket_closed / ticket_reopened
                          → engineers of the same team only (or all if no team)
    """

    def __init__(self) -> None:
        self.connections: Dict[WebSocket, str] = {}  # ws -> team
        self._broadcaster_task: asyncio.Task | None = None

    def start(self) -> None:
        if self._broadcaster_task is None or self._broadcaster_task.done():
            self._broadcaster_task = asyncio.create_task(
                self._broadcaster(), name="notification-broadcaster"
            )

    def stop(self) -> None:
        if self._broadcaster_task and not self._broadcaster_task.done():
            self._broadcaster_task.cancel()

    async def connect(self, websocket: WebSocket, team: str = "") -> None:
        await websocket.accept()
        self.connections[websocket] = team
        logger.debug("Notification WS connected (team=%s). Total: %d", team, len(self.connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        self.connections.pop(websocket, None)
        logger.debug("Notification WS disconnected. Total: %d", len(self.connections))

    def _connections_for_team(self, team: str) -> Set[WebSocket]:
        if not team:
            return set(self.connections.keys())
        return {ws for ws, t in self.connections.items() if t == team}

    async def listen(self, websocket: WebSocket, user: dict) -> None:
        engineer_id = int(user["sub"].split("_")[-1])
        engineer_team = user.get("team", "")
        engineer_email = user.get("email", "")
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                    if data.get("action") == "attend":
                        from app.services.ticket_service import take_ticket_by_id
                        ticket_id = data.get("ticket_id")
                        if ticket_id:
                            await take_ticket_by_id(int(ticket_id), engineer_id, engineer_team)
                except (json.JSONDecodeError, Exception) as exc:
                    logger.debug("Notification WS receive error: %s", exc)
        except WebSocketDisconnect:
            await self.disconnect(websocket)
            # Issue 4: Mark engineer offline when tab is closed / WS disconnects
            if engineer_email:
                try:
                    from app.config.db import get_database
                    from datetime import datetime, timezone
                    db = get_database()
                    await db.support_engineers.update_one(
                        {"email": engineer_email},
                        {"$set": {"is_online": False, "last_seen": datetime.now(timezone.utc)}},
                    )
                    logger.debug("Marked engineer %s offline on WS disconnect", engineer_email)
                except Exception as exc:
                    logger.debug("Failed to mark engineer offline: %s", exc)

    async def _broadcaster(self) -> None:
        while True:
            try:
                message = await notification_queue.get()
                notification_queue.task_done()

                if not self.connections:
                    continue

                event = message.get("event", "")
                team = message.get("team", "")

                if event == "ticket_created":
                    # All engineers see new tickets — anyone can pick up
                    recipients = set(self.connections.keys())
                elif event in ("ticket_taken", "ticket_resolved", "ticket_closed", "ticket_reopened"):
                    # Only same-team engineers; fall back to all if no team info
                    recipients = self._connections_for_team(team) if team else set(self.connections.keys())
                else:
                    recipients = set(self.connections.keys())

                payload = json.dumps(message)
                results = await asyncio.gather(
                    *[ws.send_text(payload) for ws in list(recipients)],
                    return_exceptions=True,
                )
                for ws, result in zip(list(recipients), results):
                    if isinstance(result, Exception):
                        logger.debug("Pruning failed notification WS: %s", result)
                        await self.disconnect(ws)

            except asyncio.CancelledError:
                logger.info("Notification broadcaster task cancelled.")
                return
            except Exception as exc:
                logger.exception("Unexpected notification broadcaster error: %s", exc)
