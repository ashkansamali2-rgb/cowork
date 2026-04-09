#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import re
import subprocess
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [CLI] %(message)s")
log = logging.getLogger("cantivia-cli")

BUS_URL       = "ws://127.0.0.1:8002"
VENV_AIDER    = os.path.expanduser("~/cowork/venv/bin/aider")
ARCHITECT_URL = "http://localhost:8080/v1"
DEFAULT_REPO  = os.path.expanduser("~/cowork")
MAX_AGENTS    = 3


def parse_tasks(message: str) -> list[str]:
    tasks = re.split(r'\s+AND\s+', message, flags=re.IGNORECASE)
    return [t.strip() for t in tasks if t.strip()]


def extract_file(task: str) -> tuple[str, list[str]]:
    """Extract filename from task if mentioned. Returns (clean_task, [file_args])"""
    # Look for patterns like "in cantivia-bus.py" or "to router.py"
    match = re.search(r'(?:in|to|from|file)\s+([\w\-/]+\.py)', task, re.IGNORECASE)
    if match:
        fname = match.group(1)
        fpath = os.path.expanduser(f"~/cowork/{fname}")
        if os.path.exists(fpath):
            return task, ["--file", fpath]
    return task, []


def run_aider(task: str, repo_path: str, file_args: list[str]) -> str:
    cmd = [
        VENV_AIDER,
        "--model", "openai/gemma",
        "--openai-api-base", ARCHITECT_URL,
        "--openai-api-key", "dummy",
        "--yes",
        "--no-auto-commits",
    ] + file_args + ["--message", task]

    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300
        )
        output = result.stdout + result.stderr
        return output[-1000:] if len(output) > 1000 else output
    except subprocess.TimeoutExpired:
        return f"Agent timed out: {task[:50]}"
    except Exception as e:
        return f"Agent error: {e}"


async def run_agent(task: str, agent_id: str, repo_path: str, ws) -> str:
    clean_task, file_args = extract_file(task)
    log.info(f"[Agent {agent_id}] Task: {clean_task[:60]} | Files: {file_args}")
    await ws.send(json.dumps({
        "type": "STATUS",
        "msg": f"Agent {agent_id}: {clean_task[:60]}"
    }))
    result = await asyncio.to_thread(run_aider, clean_task, repo_path, file_args)
    log.info(f"[Agent {agent_id}] Done")
    return f"[Agent {agent_id}] {clean_task[:40]}\n{result[:300]}"


async def handle_coding_task(message: str, ws) -> str:
    repo_path = DEFAULT_REPO
    if " in ~/" in message:
        parts = message.split(" in ~/")
        message = parts[0].strip()
        repo_path = os.path.expanduser("~/" + parts[1].strip())

    tasks = parse_tasks(message)

    if len(tasks) == 1:
        await ws.send(json.dumps({"type": "STATUS", "msg": "Cantivia coding..."}))
        clean_task, file_args = extract_file(tasks[0])
        result = await asyncio.to_thread(run_aider, clean_task, repo_path, file_args)
        return f"Done. {result[:400]}"

    capped = tasks[:MAX_AGENTS]
    await ws.send(json.dumps({
        "type": "STATUS",
        "msg": f"Spawning {len(capped)} agents in parallel..."
    }))

    results = await asyncio.gather(*[
        run_agent(task, str(i + 1), repo_path, ws)
        for i, task in enumerate(capped)
    ])

    summary = "\n---\n".join(results)
    if len(tasks) > MAX_AGENTS:
        summary += f"\n\n⚠️ {len(tasks) - MAX_AGENTS} task(s) skipped (max {MAX_AGENTS} agents)."
    return summary


async def main():
    log.info("Cantivia CLI starting (multi-agent mode)...")
    while True:
        try:
            async with websockets.connect(BUS_URL) as ws:
                await ws.send(json.dumps({"register": "cantivia"}))
                resp = json.loads(await ws.recv())
                log.info(f"Bus: {resp.get('msg')} | Peers: {resp.get('peers')}")
                async for raw in ws:
                    event = json.loads(raw)
                    if event.get("type") == "TASK_CODING":
                        result = await handle_coding_task(event.get("msg", ""), ws)
                        await ws.send(json.dumps({"type": "TASK_VOICE", "msg": result}))
                    elif event.get("type") == "STATUS":
                        log.info(f"[BUS] {event.get('msg')}")
        except (websockets.ConnectionClosed, OSError) as e:
            log.warning(f"Bus disconnected ({e}), retrying in 3s...")
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
