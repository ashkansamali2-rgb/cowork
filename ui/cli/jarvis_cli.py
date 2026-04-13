#!/usr/bin/env python3
"""
JARVIS CLI — prompt_toolkit + Rich terminal interface
Architecture:
  - prompt_toolkit handles input (real terminal, selectable text, history, keybindings)
  - Rich Console handles output (syntax highlighting, panels, diffs)
  - WebSocket connections run in a background asyncio thread
  - Main thread drives the prompt_toolkit input loop via asyncio
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

# ─── Optional imports ────────────────────────────────────────────────────────

try:
    import pyperclip
    _PYPERCLIP_OK = True
except ImportError:
    _PYPERCLIP_OK = False

try:
    import websockets
    _WS_OK = True
except ImportError:
    _WS_OK = False

# ─── Rich imports ─────────────────────────────────────────────────────────────

from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text
from rich.rule import Rule
from rich.panel import Panel
from rich.theme import Theme

# ─── prompt_toolkit imports ───────────────────────────────────────────────────

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.keys import Keys
from prompt_toolkit.key_binding import KeyBindings

# ─── Constants ────────────────────────────────────────────────────────────────

VERSION      = "0.6.0"
JARVIS_WS    = "ws://127.0.0.1:8001/ws"
BUS_WS       = "ws://127.0.0.1:8002"

COWORK_DIR   = Path.home() / ".cowork"
PROJECT_FILE = COWORK_DIR / "current_project"
CWD_FILE     = COWORK_DIR / "current_cwd"

_ANSI_RE     = re.compile(r'\x1b\[[0-9;]*m')

# Coding intent detection
_CODING_VERBS = re.compile(
    r'\b(write|create|edit|fix|add|implement|refactor|build|debug|update|generate|make)\b',
    re.IGNORECASE,
)
_CODING_NOUNS = re.compile(
    r'(\.[a-z]{1,6}\b|'
    r'\b(function|class|method|script|file|module|component|api|endpoint|'
    r'test|route|model|schema|migration|dockerfile|config|hook|handler|'
    r'controller|service|util|helper|interface|type|enum)\b)',
    re.IGNORECASE,
)

# ─── Rich theme + console ─────────────────────────────────────────────────────

_THEME = Theme({
    "user.prompt": "bold magenta",
    "user.text":   "white",
    "ts":          "dim grey50",
    "status":      "dim steel_blue1",
    "stream":      "white",
    "final":       "white",
    "error":       "bold red",
    "sep":         "dim grey30",
    "dim.text":    "dim grey50",
    "ok":          "green",
    "warn":        "yellow",
    "agent":       "bold yellow",
})

console = Console(theme=_THEME, highlight=False)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _get_cwd() -> str:
    """Return active working directory from file or process cwd."""
    if CWD_FILE.exists():
        try:
            val = CWD_FILE.read_text().strip()
            if val:
                return val
        except Exception:
            pass
    return os.getcwd()


def _short_cwd(cwd: str) -> str:
    home = str(Path.home())
    if cwd.startswith(home):
        return "~" + cwd[len(home):]
    return cwd


def _set_cwd(path: str):
    COWORK_DIR.mkdir(parents=True, exist_ok=True)
    CWD_FILE.write_text(path)


def _is_coding_intent(text: str) -> bool:
    """Return True if the message looks like a coding task."""
    return bool(_CODING_VERBS.search(text) and _CODING_NOUNS.search(text))


def _run_cmd(args: list, cwd: str = None) -> tuple:
    """Run a subprocess, return (returncode, combined output str)."""
    try:
        r = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=cwd or _get_cwd(),
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)


# ─── Output helpers ───────────────────────────────────────────────────────────

def print_separator():
    console.print(Rule(style="sep"))


def print_ts_line(label: str, text: str, style: str = "stream"):
    """Print a single line with dim timestamp prefix."""
    t = Text()
    t.append(f"[{ts()}]  ", style="ts")
    t.append(label, style=style)
    if text:
        t.append(" " + text, style=style)
    console.print(t)


def print_status(msg: str):
    t = Text()
    t.append(f"[{ts()}]  ", style="ts")
    t.append("[...] ", style="status")
    t.append(msg, style="status")
    console.print(t)


def print_error(msg: str):
    t = Text()
    t.append(f"[{ts()}]  ", style="ts")
    t.append("[ERR] ", style="error")
    t.append(msg, style="error")
    console.print(t)


def print_user(text: str):
    t = Text()
    t.append(f"[{ts()}]  ", style="ts")
    t.append("> ", style="user.prompt")
    t.append(text, style="user.text")
    console.print(t)


def print_stream(text: str):
    t = Text()
    t.append(f"[{ts()}]  ", style="ts")
    t.append("      ", style="")
    t.append(text, style="stream")
    console.print(t)


def print_agent(agent_id: str, step: int, action: str, obs: str = ""):
    t = Text()
    t.append(f"[{ts()}]  ", style="ts")
    t.append(f"[AGENT-{agent_id}] ", style="agent")
    t.append(f"Step {step}: ", style="yellow")
    t.append(action, style="bold yellow")
    if obs:
        t.append(f"  {obs[:120]}", style="dim.text")
    console.print(t)


def print_box(title: str, lines: list):
    """Print a simple titled box of lines."""
    content = "\n".join(str(l) for l in (lines or ["(empty)"]))
    panel = Panel(
        content,
        title=f"[bold magenta]{title}[/bold magenta]",
        border_style="grey30",
        padding=(0, 1),
    )
    console.print(panel)


def print_response(raw: str, msg_type: str = "final"):
    """
    Print a Jarvis response:
    - Code blocks rendered with Rich Syntax
    - Plain text printed as white lines
    - Diff lines: green +, red -, dim header
    """
    if "```" not in raw:
        # Check for diff content
        if raw.startswith("---") or "\n---" in raw or "\n+++" in raw:
            _print_diff(raw)
        else:
            for ln in raw.splitlines():
                if ln.strip():
                    console.print(Text(ln, style="final"))
                else:
                    console.print("")
        return

    segments = raw.split("```")
    for i, seg in enumerate(segments):
        if i % 2 == 1:
            # Code block
            first_nl = seg.find("\n")
            lang = seg[:first_nl].strip() if first_nl != -1 else ""
            code = seg[first_nl + 1:] if first_nl != -1 else seg
            if lang:
                console.print(Text(f"  [{lang}]", style="dim.text"))
            try:
                syn = Syntax(code.rstrip(), lang or "text", theme="monokai",
                             line_numbers=False, word_wrap=True)
                console.print(syn)
            except Exception:
                console.print(Text(code, style="stream"))
        else:
            for ln in seg.strip().splitlines():
                if ln.strip():
                    console.print(Text(ln, style="final"))


def _print_diff(raw: str):
    """Print diff output with colored +/- lines."""
    for ln in raw.splitlines():
        if ln.startswith("+++") or ln.startswith("---"):
            console.print(Text(ln, style="dim.text"))
        elif ln.startswith("+"):
            console.print(Text(ln, style="green"))
        elif ln.startswith("-"):
            console.print(Text(ln, style="red"))
        elif ln.startswith("@@"):
            console.print(Text(ln, style="cyan"))
        else:
            console.print(Text(ln, style="stream"))


# ─── Status bar ───────────────────────────────────────────────────────────────

class StatusBar:
    """Tracks and prints the thin status line."""

    def __init__(self):
        self._jarvis_conn = False
        self._bus_conn    = False

    def _render(self):
        cwd = _short_cwd(_get_cwd())
        j_dot   = "[green]●[/green]" if self._jarvis_conn else "[red]●[/red]"
        b_dot   = "[green]●[/green]" if self._bus_conn    else "[red]●[/red]"
        j_state = "connected" if self._jarvis_conn else "disconnected"
        b_state = "connected" if self._bus_conn    else "disconnected"
        return (
            f"[dim]jarvis {j_dot} {j_state}  "
            f"bus {b_dot} {b_state}  "
            f"{cwd}[/dim]"
        )

    def print(self):
        console.rule(self._render(), style="grey23")

    def set_jarvis(self, connected: bool):
        self._jarvis_conn = connected

    def set_bus(self, connected: bool):
        self._bus_conn = connected


status_bar = StatusBar()


# ─── Prompt builder ───────────────────────────────────────────────────────────

def _get_prompt_text() -> HTML:
    cwd = _short_cwd(_get_cwd())
    return HTML(f'<ansimagenta><b>{cwd} ❯ </b></ansimagenta>')


_PT_STYLE = PTStyle.from_dict({
    "": "#ffffff",
    "prompt": "bold #aa55ff",
})

_SLASH_COMPLETER = WordCompleter([
    '/help', '/clear', '/ls', '/cat', '/open', '/mkdir', '/rm',
    '/git', '/start', '/stop', '/status', '/logs', '/agent', '/agents',
    '/kill', '/cantivia', '/research', '/time', '/battery', '/wifi',
    '/volume', '/screenshot', '/cd', '/pwd', '/home', '/projects',
    '/project', '/copy', '/save', '/skills', '/build', '/learn',
    '/memory', '/forget', '/review',
], ignore_case=True)


# ─── WebSocket manager ────────────────────────────────────────────────────────

class WSManager:
    """
    Manages two reconnecting WebSocket connections (Jarvis + Bus) in a
    background asyncio thread. The main thread communicates via thread-safe
    queues and callbacks.
    """

    def __init__(self, on_jarvis_msg, on_bus_msg, on_jarvis_conn, on_jarvis_disc,
                 on_bus_conn, on_bus_disc):
        self._on_jarvis_msg  = on_jarvis_msg
        self._on_bus_msg     = on_bus_msg
        self._on_jarvis_conn = on_jarvis_conn
        self._on_jarvis_disc = on_jarvis_disc
        self._on_bus_conn    = on_bus_conn
        self._on_bus_disc    = on_bus_disc

        self._stopping        = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._jarvis_queue: Optional[asyncio.Queue] = None
        self._bus_queue:    Optional[asyncio.Queue] = None

    def start(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="jarvis-ws",
        )
        self._thread.start()

    def stop(self):
        self._stopping = True
        if self._loop and self._jarvis_queue:
            self._loop.call_soon_threadsafe(self._jarvis_queue.put_nowait, None)
        if self._loop and self._bus_queue:
            self._loop.call_soon_threadsafe(self._bus_queue.put_nowait, None)

    def send_jarvis(self, payload: str):
        if self._loop and self._jarvis_queue:
            self._loop.call_soon_threadsafe(self._jarvis_queue.put_nowait, payload)

    def send_bus(self, payload: str):
        if self._loop and self._bus_queue:
            self._loop.call_soon_threadsafe(self._bus_queue.put_nowait, payload)

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._jarvis_queue = asyncio.Queue()
        self._bus_queue    = asyncio.Queue()

        async def _main():
            await asyncio.gather(
                self._jarvis_worker(),
                self._bus_worker(),
            )

        self._loop.run_until_complete(_main())

    async def _jarvis_worker(self):
        while not self._stopping:
            try:
                if not _WS_OK:
                    await asyncio.sleep(5)
                    continue
                async with websockets.connect(
                    JARVIS_WS,
                    ping_interval=20,
                    ping_timeout=10,
                    open_timeout=5,
                ) as ws:
                    self._on_jarvis_conn()
                    sender   = asyncio.create_task(self._sender(ws, self._jarvis_queue))
                    receiver = asyncio.create_task(self._receiver(ws, self._on_jarvis_msg))
                    _done, pending = await asyncio.wait(
                        [sender, receiver],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()
                        try:
                            await t
                        except asyncio.CancelledError:
                            pass
            except (ConnectionRefusedError, OSError, TimeoutError):
                pass
            except Exception:
                pass
            finally:
                self._on_jarvis_disc()
            if not self._stopping:
                await asyncio.sleep(3)

    async def _bus_worker(self):
        while not self._stopping:
            try:
                if not _WS_OK:
                    await asyncio.sleep(5)
                    continue
                async with websockets.connect(
                    BUS_WS,
                    ping_interval=20,
                    ping_timeout=10,
                    open_timeout=5,
                ) as ws:
                    await ws.send(json.dumps({"register": "cli"}))
                    self._on_bus_conn()
                    sender   = asyncio.create_task(self._sender(ws, self._bus_queue))
                    receiver = asyncio.create_task(self._receiver(ws, self._on_bus_msg))
                    _done, pending = await asyncio.wait(
                        [sender, receiver],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()
                        try:
                            await t
                        except asyncio.CancelledError:
                            pass
            except (ConnectionRefusedError, OSError, TimeoutError):
                pass
            except Exception:
                pass
            finally:
                self._on_bus_disc()
            if not self._stopping:
                await asyncio.sleep(3)

    @staticmethod
    async def _sender(ws, queue: asyncio.Queue):
        while True:
            payload = await queue.get()
            if payload is None:
                return
            try:
                await ws.send(payload)
            except Exception:
                return

    @staticmethod
    async def _receiver(ws, callback):
        async for raw in ws:
            callback(raw)


# ─── Command handler (slash commands) ─────────────────────────────────────────

class CommandHandler:
    """All slash command logic, separated from I/O concerns."""

    def __init__(self, ws_manager: WSManager):
        self._ws         = ws_manager
        self._agents: dict        = {}
        self._agent_counter: int  = 0
        self._pending_rm: str     = ""
        self._last_response: str  = ""
        self._chat_lines: list    = []

    def record_line(self, text: str):
        if text.strip():
            self._chat_lines.append(text)

    def set_last_response(self, text: str):
        self._last_response = text
        self.record_line(text)

    def handle(self, text: str) -> bool:
        """
        Handle a slash command. Returns True if consumed (do not send to Jarvis).
        """
        parts = text.split(None, 1)
        cmd   = parts[0].lower()
        arg   = parts[1].strip() if len(parts) > 1 else ""

        # ── /help ──────────────────────────────────────────────────────────────
        if cmd == "/help":
            lines = [
                ("Files", None),
                ("/ls [path]",            "List files in directory"),
                ("/cat [file]",           "Show file contents"),
                ("/open [file]",          "Open file in default app"),
                ("/mkdir [name]",         "Create directory"),
                ("/rm [file]",            "Delete file (with confirmation)"),
                ("Git", None),
                ("/git status",           "git status"),
                ("/git add",              "git add -A"),
                ("/git commit [msg]",     "git commit -m"),
                ("/git push",             "git push"),
                ("/git log",              "Last 5 commits"),
                ("Cowork", None),
                ("/start",                "Start all cowork services"),
                ("/stop",                 "Stop all cowork services"),
                ("/status",               "Show port status"),
                ("/logs [service]",       "Tail service log (jarvis/bus/gemma/qwen/voice)"),
                ("/research [topic]",     "Spawn background research agent"),
                ("/agent [task]",         "Spawn background agent"),
                ("/agents",              "List running agents"),
                ("/kill [id]",            "Kill agent by id"),
                ("/cantivia [task]",      "Send task to cantivia coding pipeline"),
                ("System", None),
                ("/time",                 "Show current time"),
                ("/battery",              "Show battery status"),
                ("/wifi",                 "Show WiFi network"),
                ("/volume [0-100]",       "Set system volume"),
                ("/screenshot",           "Take screenshot to desktop"),
                ("Navigation", None),
                ("/cd [path]",            "Change working directory"),
                ("/pwd",                  "Show working directory"),
                ("/home",                 "Go to home directory"),
                ("/projects",             "List cowork projects"),
                ("/project [name]",       "Set current project context"),
                ("Memory", None),
                ("/memory",               "List all long-term memories"),
                ("/forget [key]",         "Delete a memory by key"),
                ("General", None),
                ("/clear",                "Clear screen"),
                ("/copy",                 "Copy last Jarvis response to clipboard"),
                ("/save [filename]",      "Save chat history to ~/Desktop/[filename].txt"),
                ("/skills",               "List available skills"),
                ("/build [minutes]",      "Run autonomous MetaAgent build session (default 60 min)"),
                ("/learn [topic]",        "Learn from the web and save to knowledge base"),
                ("/exit",                 "Quit the CLI"),
            ]
            console.print("")
            for item in lines:
                if item[1] is None:
                    console.print(Text(f"\n  ── {item[0]} ──", style="dim.text"))
                else:
                    t = Text()
                    t.append(f"  {item[0]:<30}", style="bold magenta")
                    t.append(item[1], style="dim.text")
                    console.print(t)
            console.print("")
            return True

        # ── /clear ─────────────────────────────────────────────────────────────
        if cmd == "/clear":
            console.clear()
            _print_welcome()
            return True

        # ── /exit ──────────────────────────────────────────────────────────────
        if cmd == "/exit":
            raise SystemExit(0)

        # ── /pwd ───────────────────────────────────────────────────────────────
        if cmd == "/pwd":
            print_status(f"Working dir: {_get_cwd()}")
            return True

        # ── /cd ────────────────────────────────────────────────────────────────
        if cmd == "/cd":
            if not arg:
                print_error("Usage: /cd [path]")
                return True
            expanded = os.path.expanduser(arg)
            if not os.path.isabs(expanded):
                expanded = os.path.join(_get_cwd(), expanded)
            expanded = os.path.normpath(expanded)
            if os.path.isdir(expanded):
                _set_cwd(expanded)
                print_status(f"Working dir: {expanded}")
            else:
                print_error(f"Directory not found: {expanded}")
            return True

        # ── /home ──────────────────────────────────────────────────────────────
        if cmd == "/home":
            home = str(Path.home())
            _set_cwd(home)
            print_status(f"Working dir: {home}")
            return True

        # ── /project ───────────────────────────────────────────────────────────
        if cmd == "/project":
            COWORK_DIR.mkdir(parents=True, exist_ok=True)
            if not arg:
                current = PROJECT_FILE.read_text().strip() if PROJECT_FILE.exists() else "none"
                print_status(f"Current project: {current}")
            else:
                PROJECT_FILE.write_text(arg)
                print_status(f"Project set to: {arg}")
            return True

        # ── /projects ──────────────────────────────────────────────────────────
        if cmd == "/projects":
            projects_dir = Path.home() / "cowork" / "projects"
            if not projects_dir.exists():
                print_status("No projects directory found at ~/cowork/projects/")
                return True
            projects = [p.name for p in projects_dir.iterdir() if p.is_dir()]
            if not projects:
                print_status("No projects found.")
            else:
                current = PROJECT_FILE.read_text().strip() if PROJECT_FILE.exists() else ""
                print_status("Projects:")
                for p in sorted(projects):
                    marker = " ← current" if p == current else ""
                    console.print(Text(f"  {p}{marker}", style="final"))
            return True

        # ── /agent ─────────────────────────────────────────────────────────────
        if cmd == "/agent":
            if not arg:
                print_error("Usage: /agent [task description]")
                return True
            self._agent_counter += 1
            agent_id = f"AGENT-{self._agent_counter}"
            self._agents[agent_id] = {"task": arg, "status": "running"}
            payload = {
                "type": "TASK_CODING",
                "msg": arg,
                "cwd": _get_cwd(),
                "agent_id": agent_id,
            }
            print_status(f"[{agent_id}] Spawned: {arg}")
            self._ws.send_bus(json.dumps(payload))
            return True

        # ── /agents ────────────────────────────────────────────────────────────
        if cmd == "/agents":
            if not self._agents:
                print_status("No agents running.")
            else:
                print_status("Running agents:")
                for aid, info in self._agents.items():
                    console.print(Text(
                        f"  [{aid}]  {info['status']:<8}  {info['task']}", style="final"
                    ))
            return True

        # ── /kill ──────────────────────────────────────────────────────────────
        if cmd == "/kill":
            if not arg:
                print_error("Usage: /kill [agent-id]  e.g. /kill AGENT-1")
                return True
            aid = arg.upper()
            if aid in self._agents:
                self._agents.pop(aid)
                print_status(f"[{aid}] Cancelled.")
            else:
                print_error(f"No agent with id: {aid}")
            return True

        # ── /cantivia ──────────────────────────────────────────────────────────
        if cmd == "/cantivia":
            if not arg:
                print_error("Usage: /cantivia [task description]")
                return True
            cwd = _get_cwd()
            print_status("[Cantivia] Routing to coding agent...")
            payload = {"message": f"cantivia {arg}", "cwd": cwd}
            self._ws.send_jarvis(json.dumps(payload))
            return True

        # ── /ls ────────────────────────────────────────────────────────────────
        if cmd == "/ls":
            target = os.path.expanduser(arg) if arg else _get_cwd()
            try:
                entries = sorted(Path(target).iterdir(), key=lambda p: (p.is_file(), p.name))
                lines = [("  " if e.is_dir() else "   ") + e.name for e in entries]
                print_box(f"/ls {target}", lines or ["(empty)"])
            except Exception as e:
                print_error(str(e))
            return True

        # ── /cat ───────────────────────────────────────────────────────────────
        if cmd == "/cat":
            if not arg:
                print_error("Usage: /cat [file]")
                return True
            path = Path(os.path.expanduser(arg))
            if not path.is_absolute():
                path = Path(_get_cwd()) / arg
            try:
                content = path.read_text(errors="replace")
                ext = path.suffix.lstrip(".") or "text"
                console.print(Text(f"  [{ext}]  {path}", style="dim.text"))
                try:
                    syn = Syntax(content, ext, theme="monokai",
                                 line_numbers=True, word_wrap=False)
                    console.print(syn)
                except Exception:
                    console.print(content)
            except Exception as e:
                print_error(str(e))
            return True

        # ── /open ──────────────────────────────────────────────────────────────
        if cmd == "/open":
            if not arg:
                print_error("Usage: /open [file]")
                return True
            path = os.path.expanduser(arg)
            if not os.path.isabs(path):
                path = os.path.join(_get_cwd(), arg)
            os.system(f'open "{path}"')
            print_status(f"Opened: {path}")
            return True

        # ── /mkdir ─────────────────────────────────────────────────────────────
        if cmd == "/mkdir":
            if not arg:
                print_error("Usage: /mkdir [name]")
                return True
            path = Path(_get_cwd()) / arg
            try:
                path.mkdir(parents=True, exist_ok=True)
                print_status(f"Created: {path}")
            except Exception as e:
                print_error(str(e))
            return True

        # ── /rm ────────────────────────────────────────────────────────────────
        if cmd == "/rm":
            if not arg:
                print_error("Usage: /rm [file]")
                return True
            path_str = arg if os.path.isabs(arg) else os.path.join(_get_cwd(), arg)
            path = Path(path_str)
            if not path.exists():
                print_error(f"Not found: {path}")
                return True
            print_status(f"Type 'yes' and press Enter to delete: {path}")
            self._pending_rm = str(path)
            return True

        # ── /git ───────────────────────────────────────────────────────────────
        if cmd == "/git":
            sub_parts = arg.split(None, 1)
            subcmd    = sub_parts[0].lower() if sub_parts else ""
            sub_arg   = sub_parts[1] if len(sub_parts) > 1 else ""
            cwd       = _get_cwd()

            if subcmd == "status":
                rc, out = _run_cmd(["git", "status"], cwd)
                print_box("/git status", out.splitlines())
            elif subcmd == "add":
                rc, out = _run_cmd(["git", "add", "-A"], cwd)
                print_box("/git add", ["Staged all changes."] if rc == 0 else out.splitlines())
            elif subcmd == "commit":
                if not sub_arg:
                    print_error("Usage: /git commit [message]")
                else:
                    rc, out = _run_cmd(["git", "commit", "-m", sub_arg], cwd)
                    print_box("/git commit", out.splitlines())
            elif subcmd == "push":
                rc, out = _run_cmd(["git", "push"], cwd)
                print_box("/git push", out.splitlines())
            elif subcmd == "log":
                rc, out = _run_cmd(["git", "log", "--oneline", "-5"], cwd)
                print_box("/git log", out.splitlines())
            else:
                print_error("Usage: /git [status|add|commit <msg>|push|log]")
            return True

        # ── /start ─────────────────────────────────────────────────────────────
        if cmd == "/start":
            script = Path.home() / "cowork" / "start.sh"
            if script.exists():
                rc, out = _run_cmd(["bash", str(script)])
                print_box("/start", out.splitlines() or ["Services starting..."])
            else:
                print_error(f"Start script not found: {script}")
            return True

        # ── /stop ──────────────────────────────────────────────────────────────
        if cmd == "/stop":
            script = Path.home() / "cowork" / "stop.sh"
            if script.exists():
                rc, out = _run_cmd(["bash", str(script)])
                print_box("/stop", out.splitlines() or ["Services stopped."])
            else:
                print_error(f"Stop script not found: {script}")
            return True

        # ── /status ────────────────────────────────────────────────────────────
        if cmd == "/status":
            ports = {
                "jarvis": 8001,
                "bus":    8002,
                "gemma":  8080,
                "qwen":   8081,
                "voice":  8082,
            }
            lines = []
            for name, port in ports.items():
                rc, out = _run_cmd(["lsof", "-ti", f":{port}"])
                pid = out.strip().splitlines()[0] if out.strip() else ""
                marker = "[UP]" if pid else "[--]"
                pid_str = f"  pid={pid}" if pid else ""
                lines.append(f"{marker}  {name:<8}  :{port}{pid_str}")
            print_box("/status  port check", lines)
            return True

        # ── /logs ──────────────────────────────────────────────────────────────
        if cmd == "/logs":
            service = arg.lower() if arg else ""
            valid   = ("jarvis", "bus", "gemma", "qwen", "voice")
            if service not in valid:
                print_error(f"Usage: /logs [{'/'.join(valid)}]")
                return True
            log_path = f"/tmp/{service}.log"
            rc, out  = _run_cmd(["tail", "-n", "20", log_path])
            print_box(f"/logs {service}", out.splitlines() if out else [f"No log at {log_path}"])
            return True

        # ── /research ──────────────────────────────────────────────────────────
        if cmd == "/research":
            if not arg:
                print_error("Usage: /research [topic]")
                return True
            self._agent_counter += 1
            agent_id = f"AGENT-{self._agent_counter}"
            self._agents[agent_id] = {"task": f"research: {arg}", "status": "running"}
            payload = {
                "type": "TASK_RESEARCH",
                "msg": arg,
                "cwd": _get_cwd(),
                "agent_id": agent_id,
            }
            print_status(f"[{agent_id}] Research started: {arg}")
            self._ws.send_bus(json.dumps(payload))
            return True

        # ── /time ──────────────────────────────────────────────────────────────
        if cmd == "/time":
            now = datetime.now().strftime("%A, %B %d %Y  %H:%M:%S")
            print_box("/time", [now])
            return True

        # ── /battery ───────────────────────────────────────────────────────────
        if cmd == "/battery":
            rc, out = _run_cmd(["pmset", "-g", "binfo"])
            lines = [l for l in out.splitlines()
                     if "percent" in l.lower() or "charging" in l.lower()]
            print_box("/battery", lines or out.splitlines()[:5] or ["No battery info"])
            return True

        # ── /wifi ──────────────────────────────────────────────────────────────
        if cmd == "/wifi":
            rc, out = _run_cmd(["networksetup", "-getairportnetwork", "en0"])
            print_box("/wifi", out.splitlines())
            return True

        # ── /volume ────────────────────────────────────────────────────────────
        if cmd == "/volume":
            if not arg or not arg.isdigit():
                print_error("Usage: /volume [0-100]")
                return True
            vol = max(0, min(100, int(arg)))
            os.system(f'osascript -e "set volume output volume {vol}"')
            print_status(f"Volume set to {vol}%")
            return True

        # ── /screenshot ────────────────────────────────────────────────────────
        if cmd == "/screenshot":
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest   = os.path.expanduser(f"~/Desktop/screenshot_{ts_str}.png")
            rc, out = _run_cmd(["screencapture", "-i", dest])
            if rc == 0:
                print_status(f"Screenshot saved: {dest}")
            else:
                print_status(out or "Screenshot cancelled.")
            return True

        # ── /copy ──────────────────────────────────────────────────────────────
        if cmd == "/copy":
            if not self._last_response:
                print_error("No Jarvis response to copy yet.")
                return True
            if not _PYPERCLIP_OK:
                print_error("pyperclip not installed. Run: pip install pyperclip")
                return True
            pyperclip.copy(self._last_response)
            print_status("[Copied to clipboard]")
            return True

        # ── /save ──────────────────────────────────────────────────────────────
        if cmd == "/save":
            filename = arg if arg else f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            if not filename.endswith(".txt"):
                filename += ".txt"
            dest = Path.home() / "Desktop" / filename
            try:
                dest.write_text("\n".join(self._chat_lines), encoding="utf-8")
                print_status(f"Chat saved to: {dest}")
            except Exception as e:
                print_error(f"Save failed: {e}")
            return True

        # ── /skills ────────────────────────────────────────────────────────────
        if cmd == "/skills":
            skills_dir = Path.home() / "cowork" / "skills"
            if not skills_dir.exists():
                print_status("No skills directory found at ~/cowork/skills/")
                return True
            skills = list(skills_dir.glob("*.py")) + list(skills_dir.glob("*.json"))
            if not skills:
                print_status("No skills found.")
            else:
                print_status("Available skills:")
                for s in sorted(skills):
                    console.print(Text(f"  {s.name}", style="final"))
            return True

        # ── /build ─────────────────────────────────────────────────────────────
        if cmd == "/build":
            minutes = int(arg) if arg and arg.isdigit() else 60
            import threading
            def _run():
                import asyncio, sys
                sys.path.insert(0, str(Path.home() / "cowork" / "jarvis"))
                from core.agents.meta_agent import MetaAgent
                asyncio.run(MetaAgent().run_build_session(minutes))
            threading.Thread(target=_run, daemon=True).start()
            print_status(f"[MetaAgent] Build session started ({minutes} min). Check ~/cowork/self_improve/build_log.md")
            return True

        # ── /learn ─────────────────────────────────────────────────────────────
        if cmd == "/learn":
            topic = arg if arg else "local LLM inference optimization Apple Silicon"
            import threading
            def _run():
                import asyncio, sys
                sys.path.insert(0, str(Path.home() / "cowork" / "jarvis"))
                from core.learning.web_learner import WebLearner
                asyncio.run(WebLearner().learn_topic(topic))
            threading.Thread(target=_run, daemon=True).start()
            print_status(f"[WebLearner] Learning: {topic}. Results -> ~/cowork/jarvis/knowledge/")
            return True

        # ── /memory ────────────────────────────────────────────────────────────
        if cmd == "/memory":
            try:
                sys.path.insert(0, str(Path.home() / "cowork" / "jarvis"))
                from core.memory.long_term import LongTermMemory
                memories = LongTermMemory().get_all()
                if not memories:
                    print_status("No memories stored.")
                else:
                    lines = [f"{k}: {v.get('value', '')}" for k, v in memories.items()]
                    print_box("Long-term memories", lines)
            except Exception as e:
                print_error(f"Memory unavailable: {e}")
            return True

        # ── /forget ────────────────────────────────────────────────────────────
        if cmd == "/forget":
            if not arg:
                print_error("Usage: /forget [key]")
                return True
            try:
                sys.path.insert(0, str(Path.home() / "cowork" / "jarvis"))
                from core.memory.long_term import LongTermMemory
                removed = LongTermMemory().forget(arg)
                if removed:
                    print_status(f"Forgotten: {arg}")
                else:
                    print_error(f"Key not found: {arg}")
            except Exception as e:
                print_error(f"Memory unavailable: {e}")
            return True

        return False  # not a recognized slash command — send to Jarvis


# ─── Jarvis message handler ───────────────────────────────────────────────────

class MessageHandler:
    """Handles incoming WebSocket messages from Jarvis and Bus."""

    def __init__(self, cmd_handler: CommandHandler):
        self._cmd = cmd_handler

    def handle_jarvis(self, raw: str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            clean = strip_ansi(raw).strip()
            if clean:
                print_stream(clean)
            return

        msg_type = data.get("type", "stream")
        raw_text = data.get("msg", "") or data.get("content", "") or ""
        content  = strip_ansi(str(raw_text)).strip()

        if msg_type == "ack":
            return

        elif msg_type == "status":
            if content:
                print_status(content)

        elif msg_type in ("final", "done"):
            if content:
                self._cmd.set_last_response(content)
                print_response(content, "final")
            print_separator()

        elif msg_type == "error":
            print_error(content or "Error from Jarvis.")

        elif msg_type == "stream":
            if content:
                print_stream(content)

        elif msg_type == "agent_update":
            agent_id = data.get("agent_id", "?")
            step     = data.get("step", 0)
            action   = data.get("action", "?")
            obs      = strip_ansi(str(data.get("observation", ""))).strip()
            print_agent(agent_id, step, action, obs)

    def handle_bus(self, raw: str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        etype = data.get("type", "")

        if etype == "AGENT_STATUS":
            agent_id = data.get("agent_id", "?")
            status   = data.get("status", "")
            message  = data.get("message", "")
            label    = f"[{agent_id}] {status}: {message[:80]}" if message else f"[{agent_id}] {status}"
            print_status(label)

        elif etype in ("STATUS", "RESULT"):
            msg = strip_ansi(str(data.get("msg", "") or data.get("content", ""))).strip()
            if msg:
                t = Text()
                t.append(f"[{ts()}]  ", style="ts")
                t.append("[bus] ", style="dim.text")
                t.append(msg, style="dim.text")
                console.print(t)


# ─── Welcome screen ───────────────────────────────────────────────────────────

def _print_welcome():
    console.print("")
    status_bar.print()
    t = Text()
    t.append("  JARVIS CLI ", style="bold magenta")
    t.append(f"v{VERSION}  ", style="dim.text")
    t.append("ready", style="ok")
    console.print(t)
    console.print(Text(
        "  ctrl+q quit  ctrl+l clear  ctrl+c cancel task  up/dn history  tab complete",
        style="dim.text",
    ))
    console.print("")


# ─── Main input loop ──────────────────────────────────────────────────────────

async def main_loop():
    # ── Initialize state ──────────────────────────────────────────────────────
    COWORK_DIR.mkdir(parents=True, exist_ok=True)

    # ── WebSocket manager ─────────────────────────────────────────────────────
    def _on_jarvis_conn():
        status_bar.set_jarvis(True)

    def _on_jarvis_disc():
        status_bar.set_jarvis(False)

    def _on_bus_conn():
        status_bar.set_bus(True)

    def _on_bus_disc():
        status_bar.set_bus(False)

    ws_manager = WSManager(
        on_jarvis_msg=None,   # patched below
        on_bus_msg=None,      # patched below
        on_jarvis_conn=_on_jarvis_conn,
        on_jarvis_disc=_on_jarvis_disc,
        on_bus_conn=_on_bus_conn,
        on_bus_disc=_on_bus_disc,
    )

    cmd_handler = CommandHandler(ws_manager)
    msg_handler = MessageHandler(cmd_handler)

    # Patch callbacks now that objects exist
    ws_manager._on_jarvis_msg = msg_handler.handle_jarvis
    ws_manager._on_bus_msg    = msg_handler.handle_bus

    ws_manager.start()

    # ── prompt_toolkit session ────────────────────────────────────────────────
    kb = KeyBindings()

    @kb.add("c-c")
    def _ctrl_c(event):
        # Send stop signal to Jarvis; does NOT exit the CLI
        ws_manager.send_jarvis(json.dumps({"message": "stop", "cwd": _get_cwd()}))
        console.print(Text("[...] Task cancelled", style="status"))

    @kb.add("c-q")
    def _ctrl_q(event):
        raise KeyboardInterrupt

    @kb.add("c-l")
    def _ctrl_l(event):
        console.clear()
        _print_welcome()

    session = PromptSession(
        history=InMemoryHistory(),
        auto_suggest=AutoSuggestFromHistory(),
        completer=_SLASH_COMPLETER,
        style=_PT_STYLE,
        key_bindings=kb,
        enable_history_search=True,
        mouse_support=False,
        wrap_lines=True,
    )

    # ── Welcome ───────────────────────────────────────────────────────────────
    _print_welcome()

    # ── Input loop ────────────────────────────────────────────────────────────
    pending_rm = ""

    with patch_stdout(raw=True):
        while True:
            try:
                text = await session.prompt_async(
                    _get_prompt_text,
                    style=_PT_STYLE,
                )
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim grey50]Goodbye.[/dim grey50]")
                break

            text = text.strip()
            if not text:
                continue

            # ── /rm confirmation ──────────────────────────────────────────────
            if pending_rm:
                path = pending_rm
                pending_rm = ""
                if text.lower() == "yes":
                    try:
                        p = Path(path)
                        if p.is_dir():
                            shutil.rmtree(p)
                        else:
                            p.unlink()
                        print_status(f"Deleted: {path}")
                    except Exception as e:
                        print_error(str(e))
                else:
                    print_status("Cancelled.")
                continue

            # ── Exit commands ─────────────────────────────────────────────────
            if text.lower() in ("exit", "quit"):
                console.print("[dim grey50]Goodbye.[/dim grey50]")
                break

            # ── Slash commands ────────────────────────────────────────────────
            if text.startswith("/"):
                print_user(text)
                cmd_handler.record_line(f"> {text}")
                try:
                    consumed = cmd_handler.handle(text)
                    if cmd_handler._pending_rm:
                        pending_rm = cmd_handler._pending_rm
                        cmd_handler._pending_rm = ""
                except SystemExit:
                    console.print("[dim grey50]Goodbye.[/dim grey50]")
                    break
                if not consumed:
                    # Unknown slash command: send to Jarvis anyway
                    ws_manager.send_jarvis(json.dumps({
                        "message": text,
                        "cwd": _get_cwd(),
                    }))
                continue

            # ── Record user message ───────────────────────────────────────────
            print_user(text)
            cmd_handler.record_line(f"> {text}")

            # ── Auto-detect coding intent → route to cantivia ─────────────────
            if _is_coding_intent(text):
                print_status("[Cantivia] Routing to coding agent...")
                payload = {
                    "type": "TASK_CODING",
                    "msg": text,
                    "cwd": _get_cwd(),
                }
                ws_manager.send_bus(json.dumps(payload))
                # Also send to Jarvis so it knows
                ws_manager.send_jarvis(json.dumps({
                    "message": f"cantivia {text}",
                    "cwd": _get_cwd(),
                }))
                continue

            # ── Send to Jarvis ────────────────────────────────────────────────
            ws_manager.send_jarvis(json.dumps({
                "message": text,
                "cwd": _get_cwd(),
            }))

    # ── Shutdown ──────────────────────────────────────────────────────────────
    ws_manager.stop()


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
