#!/usr/bin/env python3
"""
cantivia-bus.py — The merge pin connecting Jarvis + Cantivia CLI
Runs as a standalone WebSocket hub on port 8002.
Both systems connect as clients and pub/sub through here.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime

import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [BUS] %(message)s")
log = logging.getLogger("cantivia-bus")

# ── Event types ──────────────────────────────────────────────────────────────
TASK_CODING   = "TASK_CODING"    # Jarvis → CLI: "fix the bug I mentioned"
TASK_VOICE    = "TASK_VOICE"     # CLI → Jarvis: speak a result
TASK_SHELL    = "TASK_SHELL"     # either → run shell command via Jarvis tools
HEARTBEAT     = "HEARTBEAT"      # Jarvis heartbeat engine events
AGENT_SPAWN   = "AGENT_SPAWN"    # autonomous background agent task
SCREENSHOT    = "SCREENSHOT"     # Playwright screenshot result from CLI
STATUS        = "STATUS"         # generic status update
RESULT        = "RESULT"         # task result
ERROR         = "ERROR"

# ── Connected clients registry ───────────────────────────────────────────────
clients: dict[str, websockets.WebSocketServerProtocol] = {}
# client_id → websocket. Clients register with {"register": "jarvis"} or {"register": "cantivia"}


async def broadcast(event: dict, exclude: str | None = None):
    """Send an event to all connected clients except the sender."""
    msg = json.dumps(event)
    dead = []
    for cid, ws in clients.items():
        if cid == exclude:
            continue
        try:
            await ws.send(msg)
        except websockets.ConnectionClosed:
            dead.append(cid)
    for cid in dead:
        clients.pop(cid, None)
        log.info(f"Pruned dead client: {cid}")


async def send_to(client_id: str, event: dict):
    """Send directly to a named client."""
    ws = clients.get(client_id)
    if ws:
        try:
            await ws.send(json.dumps(event))
        except websockets.ConnectionClosed:
            clients.pop(client_id, None)


async def route_event(sender_id: str, event: dict):
    """Core routing logic — decides what to do with each event type."""
    etype = event.get("type")
    log.info(f"[{sender_id}] → {etype}: {str(event)[:120]}")

    if etype == HEARTBEAT:
        # Jarvis heartbeat: battery, CPU alerts
        # Forward to cantivia for logging, no action needed unless critical
        if event.get("critical"):
            log.warning(f"CRITICAL HEARTBEAT: {event.get('msg')}")
            await broadcast(event, exclude=sender_id)

    elif etype == TASK_CODING:
        # Jarvis heard a voice command like "fix the failing test"
        # Route to Cantivia CLI to handle
        log.info(f"Routing coding task to Cantivia: {event.get('msg')}")
        await send_to("cantivia", {
            "type": TASK_CODING,
            "msg": event.get("msg"),
            "context": event.get("context", ""),
            "ts": datetime.now().isoformat()
        })

    elif etype == TASK_VOICE:
        # Cantivia CLI finished something → tell Jarvis to speak it
        log.info(f"Routing voice output to Jarvis: {event.get('msg')[:80]}")
        await send_to("jarvis", {
            "type": TASK_VOICE,
            "msg": event.get("msg"),
            "ts": datetime.now().isoformat()
        })

    elif etype == AGENT_SPAWN:
        # Autonomous task — log it and route to whoever can handle it
        log.info(f"AGENT SPAWN: {event.get('task')}")
        await broadcast(event, exclude=sender_id)

    elif etype == SCREENSHOT:
        # Playwright screenshot from Cantivia → send to Jarvis for visual analysis
        await send_to("jarvis", event)

    elif etype in (STATUS, RESULT, ERROR, TASK_SHELL):
        await broadcast(event, exclude=sender_id)

    else:
        log.warning(f"Unknown event type: {etype}")
        await broadcast(event, exclude=sender_id)


async def handler(websocket: websockets.WebSocketServerProtocol):
    """Handle a single client connection."""
    client_id = None
    try:
        async for raw in websocket:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"type": ERROR, "msg": "Invalid JSON"}))
                continue

            # Registration handshake
            if "register" in event:
                client_id = event["register"]  # "jarvis" or "cantivia"
                clients[client_id] = websocket
                log.info(f"Client registered: {client_id} (total: {len(clients)})")
                await websocket.send(json.dumps({
                    "type": STATUS,
                    "msg": f"Registered as '{client_id}'. Bus online.",
                    "peers": [k for k in clients if k != client_id]
                }))
                continue

            if not client_id:
                await websocket.send(json.dumps({
                    "type": ERROR,
                    "msg": "Send {\"register\": \"jarvis\"} or {\"register\": \"cantivia\"} first."
                }))
                continue

            await route_event(client_id, event)

    except websockets.ConnectionClosed:
        pass
    finally:
        if client_id:
            clients.pop(client_id, None)
            log.info(f"Client disconnected: {client_id}")


async def main():
    host, port = "127.0.0.1", 8002
    log.info(f"Cantivia Bus starting on ws://{host}:{port}")
    async with websockets.serve(handler, host, port):
        log.info("Bus online. Waiting for Jarvis and Cantivia to connect...")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
