"""
bus_client.py — Jarvis's connection to the Cantivia event bus.
Import and call connect_to_bus() from Jarvis's api_server.py startup.
"""

import asyncio
import json
import logging
import os
import sys

import websockets

sys.path.insert(0, os.path.expanduser("~/jarvis"))
from config import LLAMA_CPP_URL

log = logging.getLogger("jarvis.bus")
BUS_URL = "ws://127.0.0.1:8002"

_bus_ws = None  # module-level connection


async def connect_to_bus():
    """Maintain a persistent connection to the bus. Call as asyncio task."""
    global _bus_ws
    while True:
        try:
            async with websockets.connect(BUS_URL) as ws:
                _bus_ws = ws
                await ws.send(json.dumps({"register": "jarvis"}))
                log.info("Jarvis connected to Cantivia Bus")

                async for raw in ws:
                    event = json.loads(raw)
                    await handle_bus_event(event)

        except (websockets.ConnectionClosed, OSError) as e:
            _bus_ws = None
            log.warning(f"Bus disconnected ({e}), retrying in 3s...")
            await asyncio.sleep(3)


async def handle_bus_event(event: dict):
    """React to events routed from the bus."""
    etype = event.get("type")

    if etype == "TASK_VOICE":
        # Cantivia wants Jarvis to speak something
        msg = event.get("msg", "")
        log.info(f"[BUS→JARVIS] Speaking: {msg[:80]}")
        # Hook into your existing TTS pipeline
        asyncio.create_task(speak(msg))

    elif etype == "AGENT_SPAWN":
        task = event.get("task", "")
        log.info(f"[BUS→JARVIS] Agent spawn request: {task}")
        # Route through Jarvis's existing agent_loop
        from core.router import agent_loop
        asyncio.create_task(agent_loop(task))

    elif etype == "STATUS":
        log.info(f"[BUS] {event.get('msg')}")


async def publish(event: dict):
    """Send an event to the bus from Jarvis."""
    global _bus_ws
    if _bus_ws:
        try:
            await _bus_ws.send(json.dumps(event))
        except websockets.ConnectionClosed:
            _bus_ws = None
            log.warning("Bus connection lost while publishing")
    else:
        log.warning(f"Bus not connected — dropped event: {event.get('type')}")


async def speak(text: str):
    """Stub — wire this to your existing Qwen3-TTS pipeline in interfaces/voice/"""
    # Your live_voice.py or voice_daemon.py handles this
    # For now just log — you'll wire it in Phase 7
    log.info(f"[TTS STUB] {text}")
