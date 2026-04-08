import sys, os
sys.path.insert(0, os.path.expanduser('~/jarvis'))
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
from core.router import agent_loop
from core.bus_client import connect_to_bus

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

class ConnectionManager:
    def __init__(self): self.active_connections = []
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.append(ws)
    def disconnect(self, ws: WebSocket):
        if ws in self.active_connections: self.active_connections.remove(ws)
    async def broadcast(self, message: dict):
        for c in self.active_connections:
            try: await c.send_json(message)
            except: pass

manager = ConnectionManager()
class BroadcastSocket:
    async def send_json(self, data): await manager.broadcast(data)
broadcast_socket = BroadcastSocket()

@app.on_event("startup")
async def startup():
    asyncio.create_task(connect_to_bus())

current_task = None

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global current_task
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            user_msg = data.get("message") or data.get("msg", "")
            
            if user_msg:
                if user_msg == "SYSTEM_COMMAND_STOP":
                    if current_task and not current_task.done():
                        print("\n[!] KILL SWITCH ACTIVATED. NUKE IMMINENT.")
                        current_task.cancel()
                        await manager.broadcast({"type": "final", "msg": "Task aborted by user."})
                    continue

                if current_task and not current_task.done():
                    current_task.cancel()

                async def run_task(msg):
                    try:
                        await manager.broadcast({"type": "ack", "msg": f"Heard: {msg}"})
                        final_result = await agent_loop(msg, broadcast_socket)
                        await manager.broadcast({"type": "final", "msg": final_result})
                    except asyncio.CancelledError:
                        pass

                current_task = asyncio.create_task(run_task(user_msg))
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        await manager.broadcast({"type": "error", "msg": str(e)})

if __name__ == '__main__':
    print('Mission Control V5 WebSocket Server running on ws://127.0.0.1:8001/ws')
    uvicorn.run(app, host='127.0.0.1', port=8001, log_level='warning')
