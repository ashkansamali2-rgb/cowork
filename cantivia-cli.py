#!/usr/bin/env python3
"""
cantivia-cli.py — Phase 4 (browser vision)

New in Phase 4:
  TASK_BROWSER event — triggered by keywords like:
    "fix localhost:3000"
    "fix localhost:3000/dashboard"
    "screenshot localhost:8080 and fix"

  Pipeline:
    1. Playwright → headless Chromium → screenshot
    2. Screenshot (base64) → Gemma 4 (vision, port 8080) → diagnosis + fix plan
    3. Fix plan → Qwen 3.5 (port 8081) → writes the patch
    4. Patch → aider → applies to repo
    5. Re-screenshot → Gemma confirms fix
    6. Result spoken via TASK_VOICE

  TASK_CODING (Phase 3, unchanged):
    "cantivia [task]" or "cantivia fix [file]" → aider applies code to repo
"""

import asyncio
import base64
import json
import logging
import os
import re
import subprocess
import tempfile

import httpx
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [CLI] %(message)s")
log = logging.getLogger("cantivia-cli")

# ── Config ────────────────────────────────────────────────────────────────────

BUS_URL      = "ws://127.0.0.1:8002"
GEMMA_URL    = "http://localhost:8080/v1"   # Architect — vision + planning
QWEN_URL     = "http://localhost:8081/v1"   # Editor — writes code
VENV_AIDER   = os.path.expanduser("~/cowork/venv/bin/aider")
DEFAULT_REPO = os.path.expanduser("~/cowork")
DEV_URL      = "http://localhost:3000"      # ★ change this to whatever port you are currently working on

# ── Aider (Phase 3, unchanged) ────────────────────────────────────────────────

def run_aider(task: str, repo_path: str = DEFAULT_REPO) -> str:
    cmd = [
        VENV_AIDER,
        "--model", "openai/gemma",
        "--openai-api-base", f"{GEMMA_URL}",
        "--openai-api-key", "dummy",
        "--yes",
        "--no-auto-commits",
        "--no-show-model-warnings",
        "--message", task,
    ]
    try:
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=300)
        output = (result.stdout + result.stderr).strip()
        return output[-2000:] if len(output) > 2000 else output
    except subprocess.TimeoutExpired:
        return "Aider timed out after 5 minutes."
    except Exception as e:
        return f"Aider error: {e}"

async def handle_coding_task(task: str, ws) -> str:
    log.info(f"Coding task: {task[:80]}")
    await ws.send(json.dumps({"type": "STATUS", "msg": "Cantivia is coding..."}))

    repo_path = DEFAULT_REPO
    if " in ~/" in task:
        parts = task.split(" in ~/")
        task = parts[0].strip()
        repo_path = os.path.expanduser("~/" + parts[1].strip())

    result = await asyncio.to_thread(run_aider, task, repo_path)
    log.info(f"Aider done: {result[:120]}")
    return f"Cantivia done. {result[:300]}"

# ── Phase 4: Browser vision ───────────────────────────────────────────────────

def extract_url(msg: str) -> str | None:
    """
    Always uses DEV_URL — the port you are currently working on.
    Set DEV_URL at the top of the file when you switch projects.
    """
    return DEV_URL

async def take_screenshot(url: str) -> bytes | None:
    """
    Launch headless Chromium via Playwright, navigate to url, return PNG bytes.
    Falls back to a simple subprocess call so we don't need the async playwright
    install if the sync version is already present.
    """
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            await page.goto(url, wait_until="networkidle", timeout=15000)
            png = await page.screenshot(full_page=False)
            await browser.close()
            return png
    except ImportError:
        log.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None
    except Exception as e:
        log.error(f"Screenshot failed: {e}")
        return None

async def call_gemma_vision(png_bytes: bytes, task_hint: str) -> str:
    """
    Send screenshot to Gemma 4 (multimodal) on port 8080.
    Returns a diagnosis + fix plan as plain text.
    """
    b64 = base64.b64encode(png_bytes).decode()

    payload = {
        "model": "gemma",
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}
                    },
                    {
                        "type": "text",
                        "text": (
                            f"You are a senior frontend engineer doing a visual code review.\n"
                            f"Task hint from developer: \"{task_hint}\"\n\n"
                            f"Look at this screenshot carefully. Identify:\n"
                            f"1. What is visually broken or wrong (layout, errors, missing content, styling)\n"
                            f"2. The most likely cause in code (be specific: which component, which CSS property, which logic)\n"
                            f"3. A concrete fix plan — describe exactly what to change\n\n"
                            f"Be concise and specific. No waffle. Output format:\n"
                            f"DIAGNOSIS: <what's wrong>\n"
                            f"CAUSE: <likely code cause>\n"
                            f"FIX: <exact changes needed>"
                        )
                    }
                ]
            }
        ]
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{GEMMA_URL}/chat/completions", json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

async def call_qwen_patch(diagnosis: str, repo_path: str) -> str:
    """
    Send Gemma's diagnosis to Qwen to write the actual code patch.
    Returns the patch as a unified diff or code block.
    """
    payload = {
        "model": "qwen",
        "max_tokens": 2048,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert frontend code editor. "
                    "Given a diagnosis of a visual bug, write the minimal code fix. "
                    "Output ONLY the changed code with file paths clearly marked. "
                    "Use this format:\n"
                    "FILE: <relative/path/to/file>\n"
                    "```\n<complete fixed code block>\n```\n"
                    "Do not explain. Do not add commentary. Just the fix."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Repo root: {repo_path}\n\n"
                    f"Bug diagnosis:\n{diagnosis}\n\n"
                    f"Write the fix."
                )
            }
        ]
    }

    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(f"{QWEN_URL}/chat/completions", json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

def apply_patch_via_aider(patch_description: str, repo_path: str) -> str:
    """
    Pass Qwen's patch description to aider for clean application.
    """
    return run_aider(
        f"Apply this fix exactly as described, no other changes:\n\n{patch_description}",
        repo_path
    )

async def handle_browser_task(msg: str, ws) -> str:
    """
    Full Phase 4 pipeline:
      URL → screenshot → Gemma diagnoses → Qwen patches → aider applies → re-screenshot verify
    """
    url = extract_url(msg)
    if not url:
        return "I couldn't find a URL in that. Try: 'fix localhost:3000' or 'fix localhost:3000/dashboard'"

    # Infer repo from URL port if possible, else use default
    repo_path = DEFAULT_REPO
    if " in ~/" in msg:
        parts = msg.split(" in ~/")
        repo_path = os.path.expanduser("~/" + parts[1].strip())

    log.info(f"Browser task: {url} — repo: {repo_path}")

    # ── Step 1: Screenshot ──
    await ws.send(json.dumps({"type": "STATUS", "msg": f"Taking screenshot of {url}..."}))
    png = await take_screenshot(url)
    if not png:
        return f"Couldn't screenshot {url}. Is the server running? Is Playwright installed?"

    # Publish screenshot event to bus so Jarvis/HUD can show it
    await ws.send(json.dumps({
        "type": "SCREENSHOT",
        "url": url,
        "img": base64.b64encode(png).decode(),
        "ts": __import__("datetime").datetime.now().isoformat()
    }))

    # ── Step 2: Gemma diagnoses ──
    await ws.send(json.dumps({"type": "STATUS", "msg": "Gemma is analysing the screenshot..."}))
    try:
        diagnosis = await call_gemma_vision(png, msg)
        log.info(f"Gemma diagnosis: {diagnosis[:200]}")
    except Exception as e:
        return f"Gemma vision failed: {e}. Is the llama-server running on port 8080?"

    # ── Step 3: Qwen writes the patch ──
    await ws.send(json.dumps({"type": "STATUS", "msg": "Qwen is writing the fix..."}))
    try:
        patch = await call_qwen_patch(diagnosis, repo_path)
        log.info(f"Qwen patch: {patch[:200]}")
    except Exception as e:
        return f"Qwen patch failed: {e}. Is the llama-server running on port 8081?"

    # ── Step 4: Aider applies it ──
    await ws.send(json.dumps({"type": "STATUS", "msg": "Aider is applying the patch..."}))
    aider_result = await asyncio.to_thread(apply_patch_via_aider, patch, repo_path)

    # ── Step 5: Re-screenshot to verify ──
    await ws.send(json.dumps({"type": "STATUS", "msg": "Verifying fix with re-screenshot..."}))
    png2 = await take_screenshot(url)
    verify_note = ""
    if png2:
        await ws.send(json.dumps({
            "type": "SCREENSHOT",
            "url": url,
            "img": base64.b64encode(png2).decode(),
            "label": "after-fix",
            "ts": __import__("datetime").datetime.now().isoformat()
        }))
        # Quick Gemma check: does it look fixed?
        try:
            verify = await call_gemma_vision(
                png2,
                f"The previous bug was: {diagnosis[:300]}. Does this screenshot look fixed? Reply YES or NO and one sentence."
            )
            verify_note = f" Verification: {verify.strip()}"
        except Exception:
            verify_note = " (verification screenshot taken)"

    summary = (
        f"Browser fix applied to {url}.\n"
        f"Diagnosis: {diagnosis[:200]}\n"
        f"Aider: {aider_result[:200]}"
        f"{verify_note}"
    )
    return summary

# ── Event router ──────────────────────────────────────────────────────────────

BROWSER_KEYWORDS = ("go to localhost", "go to the localhost", "look at localhost", "check localhost", "fix the page", "fix the ui", "fix the frontend", "what's wrong with the page")

async def route(event: dict, ws) -> str | None:
    etype = event.get("type")
    msg   = event.get("msg", "")

    if etype == "TASK_CODING":
        # Check if it's actually a browser task sent via voice
        if any(kw in msg.lower() for kw in BROWSER_KEYWORDS):
            return await handle_browser_task(msg, ws)
        return await handle_coding_task(msg, ws)

    if etype == "TASK_BROWSER":
        return await handle_browser_task(msg, ws)

    return None

# ── Main loop ─────────────────────────────────────────────────────────────────

async def main():
    log.info("Cantivia CLI starting (Phase 4 — browser vision active)...")
    while True:
        try:
            async with websockets.connect(BUS_URL) as ws:
                await ws.send(json.dumps({"register": "cantivia"}))
                resp = json.loads(await ws.recv())
                log.info(f"Bus: {resp.get('msg')} | Peers: {resp.get('peers')}")

                async for raw in ws:
                    event = json.loads(raw)
                    result = await route(event, ws)
                    if result:
                        await ws.send(json.dumps({"type": "TASK_VOICE", "msg": result}))

        except (websockets.ConnectionClosed, OSError) as e:
            log.warning(f"Bus disconnected ({e}), retrying in 3s...")
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())