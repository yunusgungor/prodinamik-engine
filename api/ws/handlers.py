"""WebSocket handler'ları — gerçek zamanlı kanallar.

WS Kanalları:
- /ws/runs/{slug}       → Run state değişimleri (anlık)
- /ws/human              → HITL soruları, approval bildirimleri
- /ws/metrics            → Health score, degradation, alerts live stream
- /ws/events             → Tüm engine event'leri (broadcast)
"""

from __future__ import annotations

import json
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from api.deps import get_engine, manager

logger = logging.getLogger("prodinamik.api.ws")

router = APIRouter()


@router.websocket("/ws/runs/{slug}")
async def ws_run_events(websocket: WebSocket, slug: str):
    """Run'a özel state değişim kanalı."""
    channel = f"run:{slug}"
    await websocket.accept()
    await manager.connect(channel, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            # Client ping'lerine pong
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(channel, websocket)


@router.websocket("/ws/human")
async def ws_human_events(websocket: WebSocket):
    """HITL ve insan onay kanalı."""
    channel = "human"
    await websocket.accept()
    await manager.connect(channel, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(channel, websocket)


@router.websocket("/ws/metrics")
async def ws_metrics(websocket: WebSocket):
    """Canlı metrik akışı kanalı."""
    channel = "metrics"
    await websocket.accept()
    await manager.connect(channel, websocket)

    try:
        engine = get_engine()
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(channel, websocket)


@router.websocket("/ws/events")
async def ws_all_events(websocket: WebSocket):
    """Tüm engine event'leri (broadcast)."""
    channel = "events"
    await websocket.accept()
    await manager.connect(channel, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(channel, websocket)
