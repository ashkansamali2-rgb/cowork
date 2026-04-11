import sys, os, uuid
sys.path.insert(0, os.path.expanduser('~/jarvis'))
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
from core.router import agent_loop
from core.bus_client import connect_to_bus

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
    def __init__(self, ws: WebSocket):
        self._ws = ws

    async def send_json(self, data):
        await manager.send_to(self._ws, data)
        # Broadcast to all HUD observers
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


current_task = None


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
                for queued_msg, queued_cwd in pending_messages:
                    await _handle_message(websocket, queued_msg, session_id, queued_cwd)
                pending_messages.clear()
                continue

            user_msg = data.get("message") or data.get("msg", "")
            cwd = data.get("cwd") or None

            if not user_msg:
                continue

            if not registered:
                # First real message with no prior registration — treat as CLI
                pending_messages.append((user_msg, cwd))
                manager.register(websocket, "cli")
                registered = True
                for queued_msg, queued_cwd in pending_messages:
                    await _handle_message(websocket, queued_msg, session_id, queued_cwd)
                pending_messages.clear()
                continue

            await _handle_message(websocket, user_msg, session_id, cwd)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        session_memory.pop(session_id, None)
    except Exception as e:
        await manager.send_to(websocket, {"type": "error", "msg": str(e)})


async def _handle_message(websocket: WebSocket, user_msg: str, session_id: str, cwd: str = None):
    """Process a single user message and reply only to the originating WebSocket."""
    global current_task

    sender = SenderSocket(websocket)

    if user_msg == "SYSTEM_COMMAND_STOP":
        if current_task and not current_task.done():
            print("\n[!] KILL SWITCH ACTIVATED. NUKE IMMINENT.")
            current_task.cancel()
            await sender.send_json({"type": "final", "msg": "Task aborted by user."})
        return

    if current_task and not current_task.done():
        current_task.cancel()

    async def run_task(msg, ws=websocket, sid=session_id, _cwd=cwd):
        try:
            await sender.send_json({"type": "ack", "msg": f"Heard: {msg}"})
            final_result = await agent_loop(msg, sender, session_id=sid, cwd=_cwd)
            await sender.send_json({"type": "final", "msg": final_result})
        except asyncio.CancelledError:
            pass

    current_task = asyncio.create_task(run_task(user_msg))


if __name__ == '__main__':
    print('Mission Control V5 WebSocket Server running on ws://127.0.0.1:8001/ws')
    uvicorn.run(app, host='127.0.0.1', port=8001, log_level='warning')
