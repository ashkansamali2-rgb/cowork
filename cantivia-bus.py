#!/usr/bin/env python3
"""
cantivia-bus.py — The merge pin connecting Jarvis + Cantivia CLI.

This script runs as a standalone WebSocket hub on port 8002.
It acts as a central message broker, allowing both Jarvis and Cantivia CLI
to connect as clients and communicate via publish/subscribe patterns.
It routes events between the two systems based on their type.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

import websockets

# ── Logging setup ─────────────────────────────────────────────────────────────
LOGS_DIR = os.path.expanduser("~/cowork/logs")
os.makedirs(LOGS_DIR, exist_ok=True)

_log_path = os.path.join(LOGS_DIR, f"bus-{datetime.now().strftime('%Y-%m-%d')}.log")

_file_handler = TimedRotatingFileHandler(
    _log_path,
    when="midnight",
    backupCount=30,
    encoding="utf-8",
)
_file_handler.namer = lambda name: os.path.join(
    LOGS_DIR, "bus-" + name.rsplit("-", 1)[-1] + ".log"
    if "-" in os.path.basename(name) else name
)
_file_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"))

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(logging.Formatter("%(asctime)s [BUS] %(message)s"))

logging.basicConfig(level=logging.INFO, handlers=[_console_handler, _file_handler])
log = logging.getLogger("cantivia-bus")


def bus_log(client_id: str, event_type: str, details: str = "") -> None:
    """Write a structured log line to both stdout and the daily log file."""
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    line = f"[{ts}] [{client_id}] {event_type}: {details}"
    print(line)
    with open(_log_path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# ── Event types ──────────────────────────────────────────────────────────────
TASK_CODING    = "TASK_CODING"    # Jarvis → CLI: "fix the bug I mentioned"
TASK_VOICE     = "TASK_VOICE"     # CLI → Jarvis: speak a result
TASK_SHELL     = "TASK_SHELL"     # either → run shell command via Jarvis tools
HEARTBEAT      = "HEARTBEAT"      # Jarvis heartbeat engine events
AGENT_SPAWN    = "AGENT_SPAWN"    # autonomous background agent task
AGENT_STATUS   = "AGENT_STATUS"   # agent progress/completion update: {agent_id, status, message}
AGENT_UPDATE   = "AGENT_UPDATE"   # live ReAct step update: {agent_id, step, action, observation}
SCREENSHOT     = "SCREENSHOT"     # Playwright screenshot result from CLI
STATUS         = "STATUS"         # generic status update
RESULT         = "RESULT"         # task result
ERROR          = "ERROR"

# ── Connected clients registry ───────────────────────────────────────────────
clients: dict[str, websockets.WebSocketServerProtocol] = {}
# client_id → websocket. Clients register with {"register": "jarvis"} or {"register": "cantivia"}

# Track in-flight task start times for duration logging
_task_timers: dict[str, float] = {}

# Stats counter for daily stats logging
messages_routed: int = 0


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
        bus_log("bus", "CLIENT_PRUNED", f"dead client removed: {cid}")
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
    global messages_routed
    messages_routed += 1
    etype = event.get("type")
    detail_preview = str(event.get("msg", event.get("task", "")))[:120]
    log.info(f"[{sender_id}] → {etype}: {str(event)[:120]}")
    bus_log(sender_id, f"EVENT_{etype}", detail_preview)

    if etype == HEARTBEAT:
        # Jarvis heartbeat: battery, CPU alerts
        # Forward to cantivia for logging, no action needed unless critical
        if event.get("critical"):
            log.warning(f"CRITICAL HEARTBEAT: {event.get('msg')}")
            bus_log(sender_id, "HEARTBEAT_CRITICAL", str(event.get("msg", "")))
            await broadcast(event, exclude=sender_id)

    elif etype == TASK_CODING:
        # Jarvis heard a voice command like "fix the failing test"
        # Route to Cantivia CLI to handle
        task_key = f"{sender_id}:{event.get('msg', '')[:40]}"
        _task_timers[task_key] = time.monotonic()
        bus_log(sender_id, "TASK_START", event.get("msg", ""))
        log.info(f"Routing coding task to Cantivia: {event.get('msg')}")
        await send_to("cantivia", {
            "type": TASK_CODING,
            "msg": event.get("msg"),
            "context": event.get("context", ""),
            "cwd": event.get("cwd"),
            "ts": datetime.now().isoformat()
        })

    elif etype == TASK_VOICE:
        # Cantivia CLI finished something → tell Jarvis to speak it
        log.info(f"Routing voice output to Jarvis: {event.get('msg', '')[:80]}")
        bus_log(sender_id, "TASK_VOICE_RESULT", event.get("msg", "")[:80])
        await send_to("jarvis", {
            "type": TASK_VOICE,
            "msg": event.get("msg"),
            "ts": datetime.now().isoformat()
        })

    elif etype == RESULT:
        # A task completed — log duration if we tracked its start
        task_key = f"{sender_id}:{event.get('msg', '')[:40]}"
        if task_key in _task_timers:
            duration = time.monotonic() - _task_timers.pop(task_key)
            bus_log(sender_id, "TASK_COMPLETE", f"duration={duration:.2f}s  {event.get('msg', '')[:80]}")
        else:
            bus_log(sender_id, "TASK_COMPLETE", event.get("msg", "")[:80])
        await broadcast(event, exclude=sender_id)

    elif etype == AGENT_SPAWN:
        # Autonomous task — log it and route to whoever can handle it
        log.info(f"AGENT SPAWN: {event.get('task')}")
        bus_log(sender_id, "AGENT_SPAWN", str(event.get("task", "")))
        await broadcast(event, exclude=sender_id)

    elif etype == AGENT_STATUS:
        # Agent progress or completion update: {agent_id, status, message}
        agent_id = event.get("agent_id", "unknown")
        status   = event.get("status", "")
        message  = event.get("message", "")
        log.info(f"AGENT_STATUS [{agent_id}] {status}: {message}")
        bus_log(sender_id, f"AGENT_STATUS_{status.upper()}", f"agent={agent_id} {message[:100]}")
        await broadcast(event, exclude=sender_id)

    elif etype == AGENT_UPDATE:
        # Live ReAct step update from AgentRuntime — broadcast to all clients
        agent_id = event.get("agent_id", "unknown")
        step     = event.get("step", 0)
        log.info(f"AGENT_UPDATE [{agent_id}] step={step}: {str(event.get('action', ''))[:80]}")
        bus_log(sender_id, "AGENT_UPDATE", f"agent_id={agent_id} step={step}")
        await broadcast(event)  # all clients including sender (desktop needs it too)

    elif etype == SCREENSHOT:
        # Playwright screenshot from Cantivia → send to Jarvis for visual analysis
        await send_to("jarvis", event)

    elif etype in (STATUS, ERROR, TASK_SHELL):
        await broadcast(event, exclude=sender_id)

    else:
        log.warning(f"Unknown event type: {etype}")
        bus_log(sender_id, "EVENT_UNKNOWN", f"type={etype}")
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
                bus_log(client_id, "CLIENT_CONNECT", f"total_clients={len(clients)}")
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
            bus_log(client_id, "CLIENT_DISCONNECT", f"remaining_clients={len(clients)}")


async def _heartbeat_loop():
    """Send a heartbeat ping to all connected clients every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        ts = datetime.now().isoformat()
        msg = json.dumps({"type": "heartbeat", "ts": ts})
        dead = []
        for cid, ws in list(clients.items()):
            try:
                await ws.send(msg)
            except websockets.ConnectionClosed:
                dead.append(cid)
        for cid in dead:
            clients.pop(cid, None)
            bus_log("bus", "CLIENT_PRUNED_HEARTBEAT", f"dead client removed: {cid}")


async def _stats_loop():
    """Log message routing stats to /tmp/bus_stats.log every hour."""
    global messages_routed
    while True:
        await asyncio.sleep(3600)
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        line = f"[{ts}] messages: {messages_routed}, clients: {len(clients)}\n"
        try:
            with open("/tmp/bus_stats.log", "a", encoding="utf-8") as fh:
                fh.write(line)
        except Exception as e:
            log.warning(f"Stats log write failed: {e}")


async def main():
    host, port = "127.0.0.1", 8002
    log.info(f"Cantivia Bus starting on ws://{host}:{port}")
    bus_log("bus", "BUS_START", f"ws://{host}:{port}")
    async with websockets.serve(handler, host, port):
        log.info("Bus online. Waiting for Jarvis and Cantivia to connect...")
        asyncio.create_task(_heartbeat_loop())
        asyncio.create_task(_stats_loop())
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
