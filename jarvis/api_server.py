import sys, os, uuid
sys.path.insert(0, os.path.expanduser('~/jarvis'))
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
from core.router import agent_loop
from core.bus_client import connect_to_bus
try:
    from core.proactive import ProactiveJarvis
    _proactive = ProactiveJarvis()
    _PROACTIVE_OK = True
except Exception:
    _proactive = None
    _PROACTIVE_OK = False

from core.memory.knowledge_graph import KnowledgeGraph as KG
_kg = KG()

session_memory: dict[str, list] = {}

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


class ConnectionManager:
    def __init__(self):
        # Maps WebSocket -> {"client_type": str, "registered": bool}
        self.connections: dict = {}

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections[ws] = {"client_type": "unknown", "registered": False}

    def register(self, ws: WebSocket, client_type: str):
        if ws in self.connections:
            self.connections[ws]["client_type"] = client_type
            self.connections[ws]["registered"] = True

    def disconnect(self, ws: WebSocket):
        self.connections.pop(ws, None)

    async def send_to(self, ws: WebSocket, message: dict):
        """Send a message to a specific WebSocket only."""
        try:
            await ws.send_json(message)
        except Exception:
            pass

    async def broadcast(self, message: dict):
        """Broadcast to all connections (kept for bus/agent status events only)."""
        for ws in list(self.connections.keys()):
            try:
                await ws.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()

# HUD observer connections — receive all responses as read-only observers
hud_connections: set = set()


class SenderSocket:
    """Wraps a specific WebSocket so agent_loop replies go only to the sender."""
    def __init__(self, ws: WebSocket, is_voice: bool = False):
        self._ws = ws
        self.is_voice = is_voice

    async def send_json(self, data):
        await manager.send_to(self._ws, data)
        # Only broadcast to HUD observers for voice-originated messages
        if self.is_voice:
            for hud_ws in list(hud_connections):
                try:
                    await hud_ws.send_json(data)
                except Exception:
                    hud_connections.discard(hud_ws)


@app.on_event("startup")
async def startup():
    # Clear memory.json on startup so stale greetings can't bleed across restarts
    for mem_path in [
        os.path.expanduser('~/jarvis/memory.json'),
        os.path.expanduser('~/cowork/jarvis/memory.json'),
    ]:
        try:
            with open(mem_path, 'w') as f:
                f.write('[]')
        except Exception:
            pass
    asyncio.create_task(connect_to_bus())
    if _PROACTIVE_OK:
        asyncio.create_task(_proactive.run_periodic())

    async def _ping_connections():
        while True:
            await asyncio.sleep(30)
            dead = []
            for ws in list(manager.connections.keys()):
                try:
                    await ws.send_json({"type": "ping"})
                except Exception:
                    dead.append(ws)
            for ws in dead:
                manager.disconnect(ws)
    asyncio.create_task(_ping_connections())
    # Index codebase into knowledge graph
    try:
        import threading
        threading.Thread(target=_kg.index_codebase, daemon=True).start()
    except Exception as e:
        print(f"[KG] index error: {e}")


active_tasks: dict[str, asyncio.Task] = {}  # task_id -> Task


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global current_task
    session_id = str(uuid.uuid4())
    await manager.connect(websocket)
    pending_messages: list = []
    registered = False

    try:
        while True:
            data = await websocket.receive_json()

            # Reject oversized messages
            import sys
            msg_size = sys.getsizeof(str(data))
            if msg_size > 1_000_000:
                await websocket.send_json({"type": "error", "msg": "Message too large (max 1MB)"})
                continue

            # ── HUD observer registration ─────────────────────────────────────
            if not registered and data.get("register") == "hud":
                hud_connections.add(websocket)
                await websocket.send_json({"type": "ack", "msg": "hud registered"})
                try:
                    while True:
                        await websocket.receive_json()  # keep alive, ignore messages
                except (WebSocketDisconnect, Exception):
                    hud_connections.discard(websocket)
                return

            # ── Registration handshake ────────────────────────────────────────
            if not registered and "register" in data:
                client_type = data.get("client", data.get("register", "unknown"))
                manager.register(websocket, client_type)
                registered = True
                # Drain any messages buffered before registration
                for queued_msg, queued_cwd, queued_src in pending_messages:
                    await _handle_message(websocket, queued_msg, session_id, queued_cwd, queued_src)
                pending_messages.clear()
                continue

            user_msg = data.get("message") or data.get("msg", "")
            cwd = data.get("cwd") or None
            source = data.get("source", "unknown")

            # ── Image attachment handling ─────────────────────────────────────
            image_b64 = data.get("image")
            image_path = None
            if image_b64:
                import base64, time as _t
                image_path = f"/tmp/jarvis_image_{int(_t.time())}.png"
                try:
                    with open(image_path, "wb") as _f:
                        _f.write(base64.b64decode(image_b64))
                except Exception:
                    image_path = None
            if image_path:
                user_msg = f"[Image attached at: {image_path}] {user_msg}"

            if not user_msg:
                continue

            if not registered:
                # First real message with no prior registration — treat as CLI
                pending_messages.append((user_msg, cwd, source))
                manager.register(websocket, "cli")
                registered = True
                for queued_msg, queued_cwd, queued_src in pending_messages:
                    await _handle_message(websocket, queued_msg, session_id, queued_cwd, queued_src)
                pending_messages.clear()
                continue

            await _handle_message(websocket, user_msg, session_id, cwd, source)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        session_memory.pop(session_id, None)
    except Exception as e:
        await manager.send_to(websocket, {"type": "error", "msg": str(e)})


async def _handle_message(websocket: WebSocket, user_msg: str, session_id: str, cwd: str = None, source: str = "unknown"):
    """Process a single user message and reply only to the originating WebSocket."""
    global active_tasks

    is_voice = (source == "voice")
    sender = SenderSocket(websocket, is_voice=is_voice)

    if user_msg == "SYSTEM_COMMAND_STOP":
        print("\n[!] KILL SWITCH ACTIVATED. NUKE IMMINENT.")
        for task in list(active_tasks.values()):
            if not task.done():
                task.cancel()
        active_tasks.clear()
        await sender.send_json({"type": "final", "msg": "Task aborted by user."})
        return

    task_id = str(uuid.uuid4())

    async def run_task(msg, tid=task_id, sid=session_id, _cwd=cwd):
        try:
            await sender.send_json({"type": "ack", "msg": f"Heard: {msg}", "request_id": tid})
            final_result = await agent_loop(msg, sender, session_id=sid, cwd=_cwd)
            # Only send "final" if the response wasn't already streamed
            # The router sends stream_end when it streams, so check if it's a short/cmd response
            if final_result and not final_result.startswith("Thinking timeout"):
                await sender.send_json({"type": "final", "msg": final_result})
        except asyncio.CancelledError:
            pass
        finally:
            active_tasks.pop(tid, None)

    active_tasks[task_id] = asyncio.create_task(run_task(user_msg))


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/graph")
async def get_graph():
    """Return current knowledge graph data."""
    try:
        return _kg.get_graph_data()
    except Exception as e:
        return {"nodes": [], "edges": [], "stats": {}, "error": str(e)}


@app.post("/graph/touch/{node_id}")
async def touch_graph_node(node_id: str):
    """Mark a node as recently active."""
    try:
        _kg.touch_node(node_id)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == '__main__':
    print('Mission Control V5 WebSocket Server running on ws://127.0.0.1:8001/ws')
    uvicorn.run(app, host='127.0.0.1', port=8001, log_level='warning')
