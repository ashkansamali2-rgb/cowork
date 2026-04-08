#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import requests
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [CLI] %(message)s")
log = logging.getLogger("cantivia-cli")

BUS_URL       = "ws://127.0.0.1:8002"
ARCHITECT_URL = "http://localhost:8080/v1/chat/completions"
EDITOR_URL    = "http://localhost:8081/v1/chat/completions"

ARCHITECT_SYSTEM = """You are Gemma, the Architect. You receive a coding task and produce a clear, 
concise implementation plan only. No code — just the steps, files to edit, and logic to apply. 
Be brief and precise."""

EDITOR_SYSTEM = """You are Qwen, the Editor. You receive an implementation plan and write the actual 
code to execute it. Output only the final code, no explanation."""

def call_model(url, system, user, max_tokens=1000):
    try:
        r = requests.post(url, json={
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens
        }, timeout=120)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Model error: {e}"

async def handle_coding_task(task, ws):
    log.info(f"Coding task received: {task[:80]}")
    await ws.send(json.dumps({"type": "STATUS", "msg": "Architect is planning..."}))
    plan = await asyncio.to_thread(call_model, ARCHITECT_URL, ARCHITECT_SYSTEM, task)
    log.info(f"Architect plan: {plan[:120]}")
    await ws.send(json.dumps({"type": "STATUS", "msg": "Editor is writing code..."}))
    prompt = f"Task: {task}\n\nPlan:\n{plan}\n\nWrite the code now."
    code = await asyncio.to_thread(call_model, EDITOR_URL, EDITOR_SYSTEM, prompt, 2000)
    log.info(f"Editor output: {code[:120]}")
    out_path = os.path.expanduser("~/cantivia_output.py")
    with open(out_path, "w") as f:
        f.write(f"# Task: {task}\n# Plan:\n")
        for line in plan.splitlines():
            f.write(f"# {line}\n")
        f.write("\n" + code)
    os.system(f"open {out_path}")
    return f"Done. Code saved to ~/cantivia_output.py and opened."

async def main():
    log.info("Cantivia CLI starting, connecting to bus...")
    while True:
        try:
            async with websockets.connect(BUS_URL) as ws:
                await ws.send(json.dumps({"register": "cantivia"}))
                resp = json.loads(await ws.recv())
                log.info(f"Bus: {resp.get('msg')} | Peers: {resp.get('peers')}")
                async for raw in ws:
                    event = json.loads(raw)
                    etype = event.get("type")
                    if etype == "TASK_CODING":
                        task = event.get("msg", "")
                        result = await handle_coding_task(task, ws)
                        await ws.send(json.dumps({"type": "TASK_VOICE", "msg": result}))
                    elif etype == "STATUS":
                        log.info(f"[BUS] {event.get('msg')}")
        except (websockets.ConnectionClosed, OSError) as e:
            log.warning(f"Bus disconnected ({e}), retrying in 3s...")
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
