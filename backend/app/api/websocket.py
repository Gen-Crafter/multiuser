"""WebSocket endpoint for real-time logs and campaign events."""

from __future__ import annotations

import asyncio
import json
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.security import decode_token

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections per user."""

    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(ws)

    async def disconnect(self, user_id: str, ws: WebSocket):
        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id].discard(ws)
                if not self._connections[user_id]:
                    del self._connections[user_id]

    async def send_to_user(self, user_id: str, message: dict):
        async with self._lock:
            sockets = self._connections.get(user_id, set()).copy()
        for ws in sockets:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(message)
            except Exception:
                await self.disconnect(user_id, ws)

    async def broadcast(self, message: dict):
        async with self._lock:
            all_sockets = [
                (uid, ws)
                for uid, sockets in self._connections.items()
                for ws in sockets
            ]
        for uid, ws in all_sockets:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(message)
            except Exception:
                await self.disconnect(uid, ws)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # Authenticate via token query param
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=4001, reason="Missing token")
        return

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("No sub")
    except Exception:
        await ws.close(code=4001, reason="Invalid token")
        return

    await manager.connect(user_id, ws)

    try:
        while True:
            # Keep connection alive; client can send pings
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(user_id, ws)
