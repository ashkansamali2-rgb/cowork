"""
tools.py — Tool registry for the autonomous agent runtime.
Each tool is a callable that returns a str result.
"""
import ast
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

AGENTS_MEM_DIR = Path.home() / "cowork" / "agents" / "memory"

# ── web_search(query: str) ─────────────────────────────────────────────────────
def web_search(query: str) -> str:
    """DuckDuckGo search. Returns top 5 results with titles, URLs, snippets."""
    try:
        try:
            from ddgs import DDGS  # new package name
        except ImportError:
            from duckduckgo_search import DDGS  # legacy fallback
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return f"No results found for: {query}"
        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.get('title', '')}")
            lines.append(f"   URL: {r.get('href', '')}")
            lines.append(f"   {r.get('body', '')[:300]}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"web_search failed: {e}"

# ── fetch_url(url: str) ────────────────────────────────────────────────────────
def fetch_url(url: str) -> str:
    """Fetch webpage and extract clean text using BeautifulSoup."""
    try:
        import requests
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JarvisAgent/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Collapse blank lines
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text[:8000]
    except Exception as e:
        return f"fetch_url failed for {url}: {e}"

# ── run_shell(cmd: str) ────────────────────────────────────────────────────────
_FORBIDDEN = ["rm -rf /", "mkfs", "dd if=", ":(){:|:&};:", "sudo rm -rf /"]

def run_shell(cmd: str) -> str:
    """Execute a shell command and return stdout+stderr. Safety-checked."""
    for bad in _FORBIDDEN:
        if bad in cmd:
            return f"BLOCKED: dangerous command pattern detected: {bad}"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        out = (result.stdout + result.stderr).strip()
        return out if out else "(command ran, no output)"
    except subprocess.TimeoutExpired:
        return "run_shell: command timed out after 30s"
    except Exception as e:
        return f"run_shell failed: {e}"

# ── read_file(path: str) ───────────────────────────────────────────────────────
def read_file(path: str) -> str:
    """Read file contents."""
    try:
        p = Path(os.path.expanduser(path))
        return p.read_text(errors="replace")[:10000]
    except Exception as e:
        return f"read_file failed: {e}"

# ── write_file(path: str, content: str) ───────────────────────────────────────
def write_file(path: str, content: str) -> str:
    """Write content to file, creating parent dirs as needed."""
    try:
        p = Path(os.path.expanduser(path))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Written {len(content)} chars to {p}"
    except Exception as e:
        return f"write_file failed: {e}"

# ── append_file(path: str, content: str) ──────────────────────────────────────
def append_file(path: str, content: str) -> str:
    """Append content to file."""
    try:
        p = Path(os.path.expanduser(path))
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(content)
        return f"Appended {len(content)} chars to {p}"
    except Exception as e:
        return f"append_file failed: {e}"

# ── list_dir(path: str) ────────────────────────────────────────────────────────
def list_dir(path: str = ".") -> str:
    """List directory contents."""
    try:
        p = Path(os.path.expanduser(path))
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        lines = [f"{'[D]' if e.is_dir() else '[F]'} {e.name}" for e in entries]
        return f"Contents of {p}:\n" + "\n".join(lines) if lines else f"{p} is empty"
    except Exception as e:
        return f"list_dir failed: {e}"

# ── open_app(name: str) ────────────────────────────────────────────────────────
def open_app(name: str) -> str:
    """Open a macOS application."""
    try:
        result = subprocess.run(["open", "-a", name], capture_output=True, text=True)
        return f"Opened {name}" if result.returncode == 0 else f"open_app failed: {result.stderr}"
    except Exception as e:
        return f"open_app failed: {e}"

# ── speak(text: str) ──────────────────────────────────────────────────────────
def speak(text: str) -> str:
    """Speak text via Jarvis TTS (bus TASK_VOICE event)."""
    try:
        import asyncio as _asyncio
        async def _send():
            import websockets as _ws
            async with _ws.connect("ws://127.0.0.1:8002") as ws:
                await ws.send(json.dumps({"register": "agent-tools"}))
                await ws.recv()
                await ws.send(json.dumps({"type": "TASK_VOICE", "msg": text[:500]}))
        _asyncio.run(_send())
        return f"Spoke: {text[:100]}"
    except Exception as e:
        return f"speak failed (TTS may be offline): {e}"

# ── create_document(title, content, fmt) ─────────────────────────────────────
def create_document(title: str, content: str, fmt: str = "md") -> str:
    """Create a document on the Desktop."""
    try:
        import re
        safe = re.sub(r'[^a-zA-Z0-9_\- ]', '', title).strip().replace(" ", "-")
        fname = f"{safe}.{fmt}"
        desktop = Path.home() / "Desktop" / fname
        desktop.write_text(content)
        return f"Document created: {desktop} ({len(content)} chars)"
    except Exception as e:
        return f"create_document failed: {e}"

# ── create_word_document(title, content, path) ────────────────────────────────
def create_word_document(title: str, content: str, path: str = None) -> str:
    """Create a properly formatted Word (.docx) document on the Desktop.
    Converts markdown headings (##) to Word heading styles and bullet points
    to proper Word list items. Opens the file automatically."""
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        import re
        from datetime import datetime

        doc = Document()

        # Set document title style
        title_para = doc.add_heading(title, level=0)
        title_para.alignment = WD_ALIGN_PARAGRAPH.LEFT

        # Parse and add content line by line
        for line in content.splitlines():
            stripped = line.rstrip()

            # h3 ###
            if stripped.startswith("### "):
                doc.add_heading(stripped[4:], level=3)

            # h2 ##
            elif stripped.startswith("## "):
                doc.add_heading(stripped[3:], level=2)

            # h1 #
            elif stripped.startswith("# "):
                doc.add_heading(stripped[2:], level=1)

            # Bullet points: - or * or •
            elif re.match(r'^[-*•]\s+', stripped):
                text = re.sub(r'^[-*•]\s+', '', stripped)
                p = doc.add_paragraph(style='List Bullet')
                p.add_run(text)

            # Numbered list: 1. 2. etc
            elif re.match(r'^\d+\.\s+', stripped):
                text = re.sub(r'^\d+\.\s+', '', stripped)
                p = doc.add_paragraph(style='List Number')
                p.add_run(text)

            # Horizontal rule
            elif stripped in ('---', '***', '___'):
                doc.add_paragraph('─' * 60)

            # Empty line
            elif not stripped:
                doc.add_paragraph('')

            # Regular text
            else:
                # Handle inline bold **text**
                p = doc.add_paragraph()
                parts = re.split(r'\*\*(.*?)\*\*', stripped)
                for i, part in enumerate(parts):
                    run = p.add_run(part)
                    if i % 2 == 1:  # odd parts are bold
                        run.bold = True

        # Determine output path
        if path:
            out = Path(os.path.expanduser(path))
        else:
            import re as _re
            safe = _re.sub(r'[^a-zA-Z0-9_\- ]', '', title).strip().replace(" ", "-")
            date_str = datetime.now().strftime("%Y%m%d")
            out = Path.home() / "Desktop" / f"{safe}-{date_str}.docx"

        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out))
        os.system(f"open \"{out}\"")
        return f"Word document created and opened: {out}"
    except Exception as e:
        return f"create_word_document failed: {e}"

# ── take_screenshot() ─────────────────────────────────────────────────────────
def take_screenshot() -> str:
    """Take a screenshot and save to Desktop."""
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path.home() / "Desktop" / f"screenshot_{ts}.png"
    result = subprocess.run(["screencapture", "-x", str(path)], capture_output=True)
    return str(path) if result.returncode == 0 else "screenshot failed"

# ── get_clipboard() ───────────────────────────────────────────────────────────
def get_clipboard() -> str:
    """Get clipboard contents."""
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True)
        return result.stdout or "(clipboard empty)"
    except Exception as e:
        return f"get_clipboard failed: {e}"

# ── set_clipboard(text: str) ──────────────────────────────────────────────────
def set_clipboard(text: str) -> str:
    """Set clipboard contents."""
    try:
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(text.encode())
        return "Clipboard set."
    except Exception as e:
        return f"set_clipboard failed: {e}"

# ── http_request(url, method, data) ───────────────────────────────────────────
def http_request(url: str, method: str = "GET", data: dict = None) -> str:
    """Make an HTTP request and return response text."""
    try:
        import requests
        method = method.upper()
        resp = requests.request(method, url, json=data, timeout=15)
        return resp.text[:5000]
    except Exception as e:
        return f"http_request failed: {e}"

# ── summarize(text, instruction) ─────────────────────────────────────────────
def summarize(text: str, instruction: str = "Summarize concisely.") -> str:
    """Use Qwen to summarize or transform text."""
    try:
        import requests
        payload = {
            "model": "qwen",
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": text[:6000]},
            ],
            "temperature": 0.3,
            "max_tokens": 512,
        }
        resp = requests.post("http://localhost:8081/v1/chat/completions", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"summarize failed (Qwen may be offline): {e}"

# ── remember(key, value) ──────────────────────────────────────────────────────
def remember(key: str, value: str) -> str:
    """Store a key-value pair in persistent agent memory."""
    try:
        AGENTS_MEM_DIR.mkdir(parents=True, exist_ok=True)
        p = AGENTS_MEM_DIR / f"{key}.json"
        p.write_text(json.dumps({"key": key, "value": value}))
        return f"Remembered: {key}"
    except Exception as e:
        return f"remember failed: {e}"

# ── recall(key) ───────────────────────────────────────────────────────────────
def recall(key: str) -> str:
    """Retrieve a value from persistent agent memory."""
    try:
        p = AGENTS_MEM_DIR / f"{key}.json"
        if not p.exists():
            return f"No memory found for key: {key}"
        data = json.loads(p.read_text())
        return str(data.get("value", ""))
    except Exception as e:
        return f"recall failed: {e}"

# ── spawn_subagent(task) ──────────────────────────────────────────────────────
def spawn_subagent(task: str) -> str:
    """Spawn a child agent for a subtask. Returns agent_id."""
    try:
        import time
        agent_id = f"SUB-{int(time.time())}"
        import asyncio as _asyncio
        async def _send():
            import websockets as _ws
            async with _ws.connect("ws://127.0.0.1:8002") as ws:
                await ws.send(json.dumps({"register": "subagent-spawner"}))
                await ws.recv()
                await ws.send(json.dumps({
                    "type": "TASK_RESEARCH",
                    "msg": task,
                    "agent_id": agent_id,
                    "cwd": str(Path.home() / "cowork"),
                }))
        _asyncio.run(_send())
        return f"Spawned subagent {agent_id} for: {task}"
    except Exception as e:
        return f"spawn_subagent failed: {e}"

# ── Tool registry ─────────────────────────────────────────────────────────────

TOOLS: dict[str, callable] = {
    "web_search":            web_search,
    "fetch_url":             fetch_url,
    "run_shell":             run_shell,
    "read_file":             read_file,
    "write_file":            write_file,
    "append_file":           append_file,
    "list_dir":              list_dir,
    "open_app":              open_app,
    "speak":                 speak,
    "create_document":       create_document,
    "create_word_document":  create_word_document,
    "take_screenshot":       take_screenshot,
    "get_clipboard":         get_clipboard,
    "set_clipboard":         set_clipboard,
    "http_request":          http_request,
    "summarize":             summarize,
    "remember":              remember,
    "recall":                recall,
    "spawn_subagent":        spawn_subagent,
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    "web_search":            "web_search(query) — DuckDuckGo search, returns top 5 results with snippets",
    "fetch_url":             "fetch_url(url) — Fetch webpage, extract clean text (up to 8000 chars)",
    "run_shell":             "run_shell(cmd) — Run a shell command, returns stdout+stderr",
    "read_file":             "read_file(path) — Read file contents",
    "write_file":            "write_file(path, content) — Write content to file (creates dirs)",
    "append_file":           "append_file(path, content) — Append content to existing file",
    "list_dir":              "list_dir(path) — List directory contents",
    "open_app":              "open_app(name) — Open a macOS application by name",
    "speak":                 "speak(text) — Speak text aloud via Jarvis TTS",
    "create_document":       "create_document(title, content, fmt='md') — Create plain text/markdown document on Desktop",
    "create_word_document":  "create_word_document(title, content, path=None) — Create formatted Word .docx on Desktop, opens it automatically. PREFER THIS over create_document when user says 'create a document', 'write it up', 'document it', or 'write a report'.",
    "take_screenshot":       "take_screenshot() — Take screenshot, returns path",
    "get_clipboard":         "get_clipboard() — Get clipboard text contents",
    "set_clipboard":         "set_clipboard(text) — Copy text to clipboard",
    "http_request":          "http_request(url, method='GET', data=None) — HTTP request, returns response",
    "summarize":             "summarize(text, instruction) — Use Qwen LLM to summarize or transform text",
    "remember":              "remember(key, value) — Persist key-value to ~/cowork/agents/memory/",
    "recall":                "recall(key) — Retrieve persisted value by key",
    "spawn_subagent":        "spawn_subagent(task) — Spawn a child agent for a parallel subtask",
}

def get_tool_descriptions() -> str:
    return "\n".join(f"- {v}" for v in TOOL_DESCRIPTIONS.values())

def register_tool(name: str, fn: callable, description: str = ""):
    """Dynamically register a new tool at runtime."""
    TOOLS[name] = fn
    TOOL_DESCRIPTIONS[name] = description or f"{name}(...) — dynamically loaded skill"
