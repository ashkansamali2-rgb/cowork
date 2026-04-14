#!/usr/bin/env python3
"""Health check for cowork services."""
import asyncio
import json
import subprocess
import sys
import time

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

PORTS = {
    "jarvis":          8001,
    "bus":             8002,
    "gemma-31b":       8081,
    "command-station": 5173,
}

MODEL_URLS = {
    "gemma-31b": "http://localhost:8081/v1/chat/completions",
}


def check_port(port: int) -> bool:
    r = subprocess.run(["lsof", "-ti", f":{port}"],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def check_process(name: str) -> bool:
    r = subprocess.run(["pgrep", "-f", name],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


async def check_ws(url: str, timeout: float = 3.0) -> bool:
    try:
        import websockets
        async with websockets.connect(url, open_timeout=timeout):
            return True
    except Exception:
        return False


async def measure_jarvis_response(timeout: float = 10.0):
    """Send 'hi' to Jarvis and measure time to first final/done response."""
    try:
        import websockets
        t0 = time.time()
        async with websockets.connect("ws://127.0.0.1:8001/ws", open_timeout=3) as ws:
            await ws.send(json.dumps({"message": "hi"}))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                data = json.loads(raw)
                if data.get("type") in ("final", "done", "error"):
                    return round((time.time() - t0) * 1000)
    except Exception:
        return None


async def measure_model_response(url: str, timeout: float = 10.0):
    """Measure HTTP response time for a model."""
    import urllib.request
    payload = json.dumps({
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
        "stream": False,
    }).encode()
    try:
        t0 = time.time()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, urllib.request.urlopen, req),
            timeout=timeout,
        )
        return round((time.time() - t0) * 1000)
    except Exception:
        return None


def _ms_color(ms):
    if ms is None:
        return f"{RED}no response{RESET}"
    if ms < 2000:
        return f"{GREEN}{ms}ms{RESET}"
    if ms < 8000:
        return f"{YELLOW}{ms}ms{RESET}"
    return f"{RED}{ms}ms{RESET}"


async def main():
    all_ok = True

    print(f"\n{BOLD}{'─' * 44}{RESET}")
    print(f"{BOLD}  cowork health check{RESET}")
    print(f"{BOLD}{'─' * 44}{RESET}\n")

    # ── Port checks ───────────────────────────────────────
    print("  Ports:")
    for name, port in PORTS.items():
        up = check_port(port)
        sym = f"{GREEN}✓{RESET}" if up else f"{RED}✗{RESET}"
        print(f"    {sym}  {name:<18} :{port}")
        if not up:
            all_ok = False

    # ── Process checks ────────────────────────────────────
    print("\n  Processes:")
    procs = {
        "live_voice":  "voice",
        "api_server":  "jarvis",
        "cantivia-cli": "cantivia",
        "electron":    "hud",
    }
    for proc, label in procs.items():
        running = check_process(proc)
        sym = f"{GREEN}✓{RESET}" if running else f"{YELLOW}?{RESET}"
        print(f"    {sym}  {label}")

    # ── WebSocket connectivity ─────────────────────────────
    print("\n  WebSocket:")
    jarvis_ok = await check_ws("ws://127.0.0.1:8001/ws")
    bus_ok    = await check_ws("ws://127.0.0.1:8002")
    sym_j = f"{GREEN}✓{RESET}" if jarvis_ok else f"{RED}✗{RESET}"
    sym_b = f"{GREEN}✓{RESET}" if bus_ok    else f"{RED}✗{RESET}"
    print(f"    {sym_j}  jarvis ws://127.0.0.1:8001/ws")
    print(f"    {sym_b}  bus    ws://127.0.0.1:8002")
    if not (jarvis_ok and bus_ok):
        all_ok = False

    # ── Response time ─────────────────────────────────────
    print("\n  Response times:")
    if jarvis_ok:
        ms = await measure_jarvis_response()
        print(f"    Jarvis  {_ms_color(ms)}")
        if ms is None:
            all_ok = False
    else:
        print(f"    Jarvis  {RED}skipped (not connected){RESET}")

    for model_name, model_url in MODEL_URLS.items():
        if check_port(PORTS.get(model_name, 0)):
            ms = await measure_model_response(model_url)
            print(f"    {model_name:<8}{_ms_color(ms)}")
        else:
            print(f"    {model_name:<8}{YELLOW}skipped (port down){RESET}")

    # ── Memory & Metrics ──────────────────────────────────────────────────────────
    import os
    from pathlib import Path
    print("\n  Memory & Metrics:")
    try:
        sys.path.insert(0, os.path.expanduser("~/cowork/jarvis"))
        from core.memory.long_term import LongTermMemory
        mem = LongTermMemory()
        memories = mem._load()
        print(f"    Long-term memories: {len(memories)}")
    except Exception as e:
        print(f"    Memory: {YELLOW}unavailable{RESET}")

    try:
        from core.monitoring import PerformanceMonitor
        mon = PerformanceMonitor()
        avg = mon.get_avg_response()
        rate = mon.get_success_rate()
        print(f"    Avg response: {_ms_color(int(avg * 1000))}")
        print(f"    Success rate: {GREEN if rate > 90 else YELLOW}{rate:.1f}%{RESET}")
    except Exception:
        print(f"    Monitoring: {YELLOW}unavailable{RESET}")

    build_log = Path(os.path.expanduser("~/cowork/self_improve/build_log.md"))
    if build_log.exists():
        lines = build_log.read_text().strip().split("\n")
        last_3 = [l for l in lines if l.strip()][-3:]
        print("\n  Last build log entries:")
        for line in last_3:
            print(f"    {line[:80]}")

    # ── Summary ───────────────────────────────────────────
    print(f"\n{'─' * 44}")
    if all_ok:
        print(f"  {GREEN}{BOLD}All systems healthy{RESET}")
    else:
        print(f"  {RED}{BOLD}Issues detected — check above{RESET}")
    print()

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
