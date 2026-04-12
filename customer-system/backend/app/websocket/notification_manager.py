import asyncio
import json
import logging
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect

from app.utils.shared import notification_queue

logger = logging.getLogger(__name__)


class NotificationManager:
    """
    Manages WebSocket connections for support engineers and broadcasts
    ticket-lifecycle notifications from the shared queue to every
    connected engineer.

    Events broadcast to engineers:
        - new_ticket      : A new ticket was created by a customer.
        - first_message   : First chat message sent on an unattended ticket.
        - ticket_attended : An engineer has claimed the ticket (others can dismiss it).
        - ticket_resolved : A ticket was resolved (informational).
        - ticket_closed   : A ticket was permanently closed (informational).
        - ticket_reopened : A resolved ticket was reopened by the customer.

    Engineers can also send:
        { "action": "attend", "ticket_id": <int>, "engineer_id": <int> }
    to claim a ticket via the notification WebSocket.
    """

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()
        self._broadcaster_task: asyncio.Task | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the shared broadcaster. Called once at app startup."""
        if self._broadcaster_task is None or self._broadcaster_task.done():
            self._broadcaster_task = asyncio.create_task(
                self._broadcaster(), name="notification-broadcaster"
            )

    def stop(self) -> None:
        """Cancel the broadcaster. Called at app shutdown."""
        if self._broadcaster_task and not self._broadcaster_task.done():
            self._broadcaster_task.cancel()

    # ── Connection management ─────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.debug("Notification WS connected. Total: %d", len(self.active_connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)
        logger.debug("Notification WS disconnected. Total: %d", len(self.active_connections))

    # ── Per-connection listener ───────────────────────────────────────────────

    async def listen(self, websocket: WebSocket, user: dict) -> None:
        """
        Keep the connection alive and handle incoming engineer actions.
        Engineers can send { "action": "attend", "ticket_id": X }
        to claim a ticket. Engineer identity is derived from the authenticated token.
        """
        engineer_id = int(user["sub"].split("_")[-1])
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                    if data.get("action") == "attend":
                        from app.services.ticket_service import take_ticket_by_id
                        ticket_id = data.get("ticket_id")
                        if ticket_id:
                            await take_ticket_by_id(int(ticket_id), engineer_id)
                except (json.JSONDecodeError, Exception) as exc:
                    logger.debug("Notification WS receive error: %s", exc)
        except WebSocketDisconnect:
            await self.disconnect(websocket)

    # ── Broadcaster ───────────────────────────────────────────────────────────

    async def _broadcaster(self) -> None:
        """
        Drains the notification_queue and fans out every event to all
        connected engineers. json.dumps called once per event.
        """
        while True:
            try:
                message = await notification_queue.get()
                notification_queue.task_done()

                if not self.active_connections:
                    continue

                payload = json.dumps(message)

                results = await asyncio.gather(
                    *[ws.send_text(payload) for ws in list(self.active_connections)],
                    return_exceptions=True,
                )

                for ws, result in zip(list(self.active_connections), results):
                    if isinstance(result, Exception):
                        logger.debug("Pruning failed notification WS: %s", result)
                        await self.disconnect(ws)

            except asyncio.CancelledError:
                logger.info("Notification broadcaster task cancelled.")
                return
            except Exception as exc:
                logger.exception("Unexpected notification broadcaster error: %s", exc)
