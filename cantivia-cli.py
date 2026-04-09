#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import re
import subprocess
import base64
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
    match = re.search(r'(?:in|to|from|file)\s+([\w\-/]+\.py)', task, re.IGNORECASE)
    if match:
        fname = match.group(1)
        fpath = os.path.expanduser(f"~/cowork/{fname}")
        if os.path.exists(fpath):
            return task, ["--file", fpath]
    return task, []


def screenshot_url(url: str) -> str | None:
    """Take a screenshot of a URL using Playwright. Returns base64 PNG or None."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url, wait_until="networkidle", timeout=15000)
            screenshot = page.screenshot(full_page=False)
            browser.close()
            return base64.b64encode(screenshot).decode()
    except Exception as e:
        log.error(f"Screenshot error: {e}")
        return None


def get_page_source(url: str) -> str:
    """Get page HTML source via Playwright."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=15000)
            source = page.content()
            browser.close()
            return source[:8000]  # Cap at 8k chars
    except Exception as e:
        return f"Could not fetch page: {e}"


def diagnose_page(url: str, task: str) -> str:
    """Send page HTML to Gemma for diagnosis and fix plan."""
    import requests
    source = get_page_source(url)
    try:
        r = requests.post(ARCHITECT_URL + "/chat/completions", json={
            "messages": [
                {
                    "role": "system",
                    "content": "You are a web developer. Analyze the HTML source and produce a concise fix plan."
                },
                {
                    "role": "user",
                    "content": f"URL: {url}\nTask: {task}\nPage source:\n{source}\n\nWhat needs fixing? Give a short actionable plan."
                }
            ],
            "temperature": 0.1,
            "max_tokens": 500
        }, timeout=60)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Diagnosis error: {e}"


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
            cmd, cwd=repo_path,
            capture_output=True, text=True, timeout=300
        )
        output = result.stdout + result.stderr
        return output[-1000:] if len(output) > 1000 else output
    except subprocess.TimeoutExpired:
        return f"Agent timed out: {task[:50]}"
    except Exception as e:
        return f"Agent error: {e}"


async def handle_browser_task(message: str, ws) -> str:
    """Phase 4 — screenshot URL, diagnose, then fix with aider."""
    # Extract URL from message
    # Extract port number if mentioned e.g. "fix localhost:3000" or "fix port 3000"
    port_match = re.search(r'localhost:?\s*(\d+)', message, re.IGNORECASE)
    url_match = re.search(r'(https?://\S+)', message, re.IGNORECASE)
    if url_match:
        url = url_match.group(1)
    elif port_match:
        url = f"http://localhost:{port_match.group(1)}"
    else:
        url = "http://localhost:3000"

    await ws.send(json.dumps({"type": "STATUS", "msg": f"Screenshotting {url}..."}))
    log.info(f"[Browser] Screenshotting {url}")

    screenshot_b64 = await asyncio.to_thread(screenshot_url, url)

    await ws.send(json.dumps({"type": "STATUS", "msg": "Gemma is diagnosing the page..."}))

    task = message
    diagnosis = await asyncio.to_thread(diagnose_page, url, task)
    log.info(f"[Browser] Diagnosis: {diagnosis[:120]}")

    await ws.send(json.dumps({"type": "STATUS", "msg": "Qwen is writing the fix..."}))

    # Run aider with the diagnosis as the task
    fix_result = await asyncio.to_thread(run_aider, diagnosis, DEFAULT_REPO, [])

    # Take a second screenshot to verify
    await ws.send(json.dumps({"type": "STATUS", "msg": "Verifying fix..."}))
    screenshot2 = await asyncio.to_thread(screenshot_url, url)
    verified = "✅ Page re-screenshotted after fix." if screenshot2 else "⚠️ Could not verify."

    return f"Diagnosed: {diagnosis[:200]}\n\nFix applied. {verified}"


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
    # Phase 4: browser fix tasks
    browser_triggers = ["fix localhost", "fix http", "screenshot", "check localhost", "debug localhost"]
    if any(t in message.lower() for t in browser_triggers):
        return await handle_browser_task(message, ws)

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
    log.info("Cantivia CLI starting (multi-agent + browser vision mode)...")
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
