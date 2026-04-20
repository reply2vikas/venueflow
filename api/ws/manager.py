"""
WebSocket manager for real-time nudges.
Clients connect to /ws/live. Falls back gracefully to polling /api/alerts.
"""
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
_active: set[WebSocket] = set()

@router.websocket("/ws/live")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    _active.add(websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping", "msg": "alive"})
    except (WebSocketDisconnect, Exception):
        _active.discard(websocket)

async def broadcast(payload: dict):
    """Broadcast message to all connected clients. Prunes dead sockets."""
    dead: set[WebSocket] = set()
    for ws in _active.copy():
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)
    _active -= dead
