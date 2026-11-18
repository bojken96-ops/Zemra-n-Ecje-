"""WebSocket for live dashboard updates (Redis pub/sub fan-out)."""
import asyncio
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.db import SessionLocal
from app.services import auth
from app.services.events import CHANNEL

router = APIRouter()
log = logging.getLogger(__name__)


@router.websocket("/api/ws")
async def ws(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin and origin not in get_settings().origins:
        await websocket.close(code=4403)
        return
    db = SessionLocal()
    try:
        sess = auth.resolve_session(db, websocket.cookies.get(auth.SESSION_COOKIE))
    finally:
        db.close()
    if sess is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(CHANNEL)

    async def pump():
        async for msg in pubsub.listen():
            if msg.get("type") == "message":
                await websocket.send_text(msg["data"])

    task = asyncio.create_task(pump())
    try:
        while True:
            await websocket.receive_text()  # keepalive pings from the client
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        await pubsub.unsubscribe(CHANNEL)
        await pubsub.aclose()
        await r.aclose()
