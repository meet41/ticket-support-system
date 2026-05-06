from typing import Dict, List, Optional
from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, ticket_id: int, websocket: WebSocket):
        await websocket.accept()
        if ticket_id not in self.active_connections:
            self.active_connections[ticket_id] = []
        self.active_connections[ticket_id].append(websocket)
        for key,value in self.active_connections.items():
            print(f"Ticket-{key} active: {len(value)}")

    def disconnect(self, ticket_id: int, websocket: WebSocket):
        if ticket_id in self.active_connections:
            try:
                self.active_connections[ticket_id].remove(websocket)
            except ValueError:
                pass
            if not self.active_connections[ticket_id]:
                del self.active_connections[ticket_id]

    async def send_history(self, websocket: WebSocket, messages: list):
        await websocket.send_json({"type": "history", "messages": jsonable_encoder(messages)})

    async def broadcast(self, ticket_id: int, message: dict):
        await self._fan_out(ticket_id, {"type": "message", "message": jsonable_encoder(message)})

    async def broadcast_status(self, ticket_id: int, status: str, ticket_number: str = ""):
        await self._fan_out(ticket_id, {"type": "status_update", "ticket_id": ticket_id, "ticket_number": ticket_number, "status": status})

    async def broadcast_typing(self, ticket_id: int, sender_type: str, is_typing: bool, exclude: Optional[WebSocket] = None):
        payload = {"type": "typing", "sender_type": sender_type, "is_typing": is_typing}
        if ticket_id in self.active_connections:
            dead = []
            for conn in list(self.active_connections[ticket_id]):
                if conn is exclude:
                    continue
                try:
                    await conn.send_json(payload)
                except Exception:
                    dead.append(conn)
            for d in dead:
                self.disconnect(ticket_id, d)

    async def _fan_out(self, ticket_id: int, payload: dict):
        if ticket_id in self.active_connections:
            dead = []
            for conn in list(self.active_connections[ticket_id]):
                try:
                    await conn.send_json(payload)
                except Exception:
                    dead.append(conn)
            for d in dead:
                self.disconnect(ticket_id, d)
