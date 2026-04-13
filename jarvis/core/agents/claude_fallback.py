#!/usr/bin/env python3
"""Claude web fallback — used when local agents fail 3+ times on same task."""
import asyncio
import base64
import subprocess
import time
from pathlib import Path


async def ask_claude_web(problem: str, context: str) -> str:
    """
    Copy question to clipboard, open Claude.ai, paste and submit,
    wait for response, screenshot it, extract text via Gemma.
    Returns the extracted answer text.
    """
    question = (
        f"I am building a local AI system on macOS. "
        f"Problem: {problem}\n\nContext:\n{context}\n\n"
        f"What is the fix? Be specific and provide code."
    )

    # Copy to clipboard
    proc = subprocess.run(["pbcopy"], input=question.encode(), timeout=5)

    # Open Claude.ai
    subprocess.run([
        "osascript", "-e",
        'tell application "Safari" to open location "https://claude.ai/new"'
    ], timeout=10)
    await asyncio.sleep(4)

    # Paste and submit
    subprocess.run(["osascript", "-e", """
        tell application "System Events"
            tell process "Safari"
                keystroke "v" using command down
                delay 0.8
                key code 36
            end tell
        end tell
    """], timeout=10)

    # Wait for Claude to respond
    await asyncio.sleep(35)

    # Screenshot the response
    screenshot_path = f"/tmp/claude_response_{int(time.time())}.png"
    subprocess.run(["screencapture", "-x", screenshot_path], timeout=10)

    # Extract text via Gemma 4 multimodal
    answer = await _extract_text_from_screenshot(screenshot_path, problem)
    return answer


async def _extract_text_from_screenshot(screenshot_path: str, question: str) -> str:
    """Send screenshot to Gemma 4 via llama.cpp and extract the answer text."""
    import requests

    try:
        with open(screenshot_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        payload = {
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}
                    },
                    {
                        "type": "text",
                        "text": (
                            f"This is a screenshot of an AI assistant response to the question: '{question}'. "
                            f"Extract and return ONLY the answer text from the screenshot. "
                            f"Do not describe the screenshot — just return the actual answer content."
                        )
                    }
                ]
            }],
            "max_tokens": 1000,
            "temperature": 0.1,
        }

        resp = requests.post(
            "http://localhost:8080/v1/chat/completions",
            json=payload,
            timeout=60
        )
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        # Fallback: return the screenshot path so user can view it
        return f"[Screenshot saved at {screenshot_path} — Gemma extraction failed: {e}]"
