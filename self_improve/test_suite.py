#!/usr/bin/env python3
"""Test suite for cowork system health."""
import asyncio
import json
import subprocess
import sys
import time

GREEN = "\033[32m"
RED   = "\033[31m"
RESET = "\033[0m"

results = []

def record(name, passed, detail=""):
    sym = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"  [{sym}] {name}" + (f": {detail}" if detail else ""))
    results.append((name, passed))

async def test_jarvis_responds():
    try:
        import websockets
        t0 = time.time()
        async with websockets.connect("ws://127.0.0.1:8001/ws", open_timeout=3) as ws:
            await ws.send(json.dumps({"message": "hi"}))
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                if data.get("type") in ("final", "done", "error"):
                    elapsed = round((time.time() - t0) * 1000)
                    record("jarvis_responds", elapsed < 5000, f"{elapsed}ms")
                    return
        record("jarvis_responds", False, "no final received")
    except Exception as e:
        record("jarvis_responds", False, str(e))

async def test_bus_routes():
    try:
        import websockets
        async with websockets.connect("ws://127.0.0.1:8002", open_timeout=3) as ws:
            await ws.send(json.dumps({"register": "test_suite"}))
            msg = await asyncio.wait_for(ws.recv(), timeout=3)
            record("bus_routes", True, "connected and registered")
    except Exception as e:
        record("bus_routes", False, str(e))

def test_models_respond():
    import urllib.request
    for name, port in [("gemma", 8080), ("qwen", 8081)]:
        try:
            req = urllib.request.Request(
                f"http://localhost:{port}/v1/chat/completions",
                data=json.dumps({"messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}).encode(),
                headers={"Content-Type": "application/json"}
            )
            resp = urllib.request.urlopen(req, timeout=10)
            record(f"model_{name}", resp.status == 200)
        except Exception as e:
            record(f"model_{name}", False, str(e))

def test_voice_running():
    r = subprocess.run(["pgrep", "-f", "live_voice"], capture_output=True)
    record("voice_running", r.returncode == 0)

def test_ports_up():
    for name, port in [("jarvis", 8001), ("bus", 8002)]:
        r = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
        record(f"port_{name}", bool(r.stdout.strip()))

async def main():
    print("\n--- cowork test suite ---\n")
    await test_jarvis_responds()
    await test_bus_routes()
    test_models_respond()
    test_voice_running()
    test_ports_up()

    passed = sum(1 for _, p in results if p)
    total  = len(results)
    print(f"\n  {passed}/{total} passed")
    sys.exit(0 if passed == total else 1)

if __name__ == "__main__":
    asyncio.run(main())
