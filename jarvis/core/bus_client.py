import asyncio
import json
import logging
import os
import sys

import websockets
import time as _time

sys.path.insert(0, os.path.expanduser("~/cowork/jarvis"))

log = logging.getLogger("jarvis.bus")
BUS_URL = "ws://127.0.0.1:8002"
_bus_ws = None


def _speak(text: str):
    """Import speak lazily to avoid circular imports."""
    try:
        sys.path.insert(0, os.path.expanduser("~/cowork/jarvis/interfaces/voice"))
        from live_voice import speak_text
        speak_text(text)
    except Exception as e:
        log.warning(f"TTS failed: {e}")
        clean = text.replace("'", "")[:200]
        os.system(f"say -v Daniel '{clean}' &")


async def connect_to_bus():
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
    etype = event.get("type")
    if etype == "TASK_VOICE":
        msg = event.get("msg", "")
        log.info(f"[BUS→JARVIS] Speaking: {msg[:80]}")
        asyncio.create_task(asyncio.to_thread(_speak, msg))
    elif etype == "AGENT_SPAWN":
        task = event.get("task", "")
        agent_id = event.get("agent_id", f"SUB-{int(_time.time())}")
        from core.agents.runtime import create_agent
        async def _run_sub():
            agent = create_agent(task, agent_id=agent_id)
            await agent.run()
        asyncio.create_task(_run_sub())
    elif etype == "STATUS":
        log.info(f"[BUS] {event.get('msg')}")


async def publish(event: dict):
    global _bus_ws
    if _bus_ws:
        try:
            await _bus_ws.send(json.dumps(event))
        except websockets.ConnectionClosed:
            _bus_ws = None
    else:
        log.warning(f"Bus not connected — dropped: {event.get('type')}")
