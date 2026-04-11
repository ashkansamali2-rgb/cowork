#!/usr/bin/env python3
"""
JARVIS CLI — Rich Textual terminal interface
WebSocket runs in a dedicated background thread with its own asyncio loop.
Messages pass through asyncio.Queue objects — no Textual workers involved.
"""

import asyncio
import json
import os
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import websockets
from rich.text import Text

try:
    import pyperclip
    _PYPERCLIP_OK = True
except ImportError:
    _PYPERCLIP_OK = False
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Label, RichLog, Static

# ─── Constants ────────────────────────────────────────────────────────────────

VERSION   = "0.5.0"
JARVIS_WS = "ws://127.0.0.1:8001/ws"
BUS_WS    = "ws://127.0.0.1:8002"

COWORK_DIR   = Path.home() / ".cowork"
PROJECT_FILE = COWORK_DIR / "current_project"
CWD_FILE     = COWORK_DIR / "current_cwd"

_ANSI_RE  = re.compile(r'\x1b\[[0-9;]*m')

def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)

ASCII_LOGO = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
"""

BOOT_FRAMES = [
    "####................  [ 5%]  Initialising core",
    "######..............  [15%]  Loading models",
    "#########...........  [30%]  Connecting bus",
    "############........  [50%]  Mounting agents",
    "##############......  [65%]  Loading memory",
    "################....  [80%]  Starting router",
    "##################..  [92%]  Syncing state",
    "####################  [100%] Ready",
]

# ─── CSS ──────────────────────────────────────────────────────────────────────

CSS = """
Screen {
    background: #0A0A12;
    color: #E8E8F0;
}

#header {
    height: 10;
    background: #0A0A12;
    border-bottom: tall #2D2D3F;
    padding: 0 2;
    layout: horizontal;
}

#logo-container {
    width: 1fr;
    content-align: left middle;
    padding-top: 1;
}

#logo {
    color: #7C3AED;
    text-style: bold;
}

#header-right {
    width: 36;
    content-align: right middle;
    padding: 1 0;
    align: right middle;
}

#version-label {
    color: #6B6B8A;
    text-align: right;
}

#conn-jarvis { text-align: right; }
#conn-bus    { text-align: right; }

#main-split {
    height: 1fr;
    layout: horizontal;
}

#chat-panel {
    width: 70%;
    border-right: tall #2D2D3F;
    layout: vertical;
    scrollbar-gutter: stable;
}

#chat-log {
    height: 1fr;
    background: #0A0A12;
    padding: 1 2;
    scrollbar-color: #2D2D3F #0A0A12;
    scrollbar-size: 1 1;
}

#input-area {
    height: auto;
    background: #0A0A12;
    border-top: tall #7C3AED;
    padding: 0 2;
}

#input-separator-top {
    height: 1;
    background: #0A0A12;
    color: #2D2D3F;
    content-align: left middle;
}

#prompt-row {
    height: 3;
    layout: horizontal;
    background: #0A0A12;
}

#prompt-symbol {
    width: auto;
    color: #7C3AED;
    content-align: left middle;
    text-style: bold;
    padding-right: 1;
}

#cmd-input {
    width: 1fr;
    background: #0A0A12;
    border: none;
    color: #E8E8F0;
    padding: 0 0;
    height: 3;
}

#cmd-input:focus {
    border: none;
    background: #0A0A12;
}

#cmd-input>.input--cursor {
    color: #7C3AED;
    background: #7C3AED;
}

#input-hint {
    height: 1;
    color: #2D2D3F;
    content-align: left middle;
}

#agent-panel {
    width: 30%;
    layout: vertical;
    background: #0A0A12;
}

#agent-panel-title {
    height: 2;
    background: #13131F;
    border-bottom: tall #2D2D3F;
    color: #7C3AED;
    content-align: left middle;
    text-style: bold;
    padding: 0 2;
}

#agents-container {
    height: auto;
    padding: 1 2;
    background: #0A0A12;
}

.agent-card {
    height: auto;
    background: #0A0A12;
    margin-bottom: 1;
}

.agent-name   { color: #7C3AED; text-style: bold; }
.agent-role   { color: #6B6B8A; }
.agent-status { color: #10B981; }
.agent-status.idle  { color: #6B6B8A; }
.agent-status.error { color: #EF4444; }
.agent-task   { color: #9CA3AF; }
.agent-tokens { color: #6B6B8A; }

#bus-feed-title {
    height: 2;
    background: #13131F;
    border-top: tall #2D2D3F;
    border-bottom: tall #2D2D3F;
    color: #6B6B8A;
    content-align: left middle;
    padding: 0 2;
    text-style: bold;
}

#bus-log {
    height: 1fr;
    background: #0A0A12;
    padding: 0 2;
    scrollbar-color: #2D2D3F #0A0A12;
    scrollbar-size: 1 1;
}

#boot-screen {
    background: #0A0A12;
    layout: vertical;
    align: center middle;
    width: 100%;
    height: 100%;
}

#boot-logo {
    color: #7C3AED;
    content-align: center middle;
    text-align: center;
    text-style: bold;
    width: 100%;
}

#boot-bar {
    width: 60;
    color: #7C3AED;
    content-align: center middle;
    text-align: center;
    margin-top: 2;
}

#boot-msg {
    color: #6B6B8A;
    content-align: center middle;
    text-align: center;
    margin-top: 1;
}
"""

# ─── Helpers ──────────────────────────────────────────────────────────────────

def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def make_user_line(text: str) -> Text:
    t = Text()
    t.append(f"[{ts()}] ", style="dim #6B6B8A")
    t.append("> ", style="bold #7C3AED")
    t.append(text, style="#E8E8F0")
    return t


def make_jarvis_line(text: str, msg_type: str = "stream") -> Text:
    t = Text()
    t.append(f"[{ts()}] ", style="dim #6B6B8A")
    if msg_type == "final":
        t.append("[JARVIS] ", style="bold #E8E8F0")
        t.append(text, style="#E8E8F0")
    elif msg_type == "status":
        t.append("[...] ", style="#5B7FA6")
        t.append(text, style="#8BAFD4")
    elif msg_type == "error":
        t.append("[ERR] ", style="bold #EF4444")
        t.append(text, style="#FCA5A5")
    else:
        t.append("      ", style="")
        t.append(text, style="#C8C8D8")
    return t


def _cmd_line(cmd: str, desc: str) -> Text:
    t = Text()
    t.append(f"  {cmd:<28}", style="bold #7C3AED")
    t.append(desc, style="#9CA3AF")
    return t


def _dim_line(text: str) -> Text:
    t = Text()
    t.append(text, style="#2D2D3F")
    return t


def make_code_block(code: str, lang: str = "") -> list[Text]:
    out = []
    header = Text()
    header.append(f"[{lang or 'code'}]", style="bold #5B7FA6")
    out.append(header)
    for line in code.splitlines():
        t = Text()
        t.append("  " + line, style="#C8C8D8")
        out.append(t)
    out.append(Text(""))
    return out


def parse_and_render(raw: str, msg_type: str = "final") -> list[Text]:
    lines: list[Text] = []
    if "```" in raw:
        segments = raw.split("```")
        for i, seg in enumerate(segments):
            if i % 2 == 1:
                first_nl = seg.find("\n")
                lang = seg[:first_nl].strip() if first_nl != -1 else ""
                code = seg[first_nl + 1:] if first_nl != -1 else seg
                lines += make_code_block(code, lang)
            else:
                for ln in seg.strip().splitlines():
                    if ln.strip():
                        lines.append(make_jarvis_line(ln, msg_type))
        return lines or [make_jarvis_line(raw, msg_type)]
    for ln in raw.splitlines():
        if ln.strip():
            lines.append(make_jarvis_line(ln, msg_type))
        else:
            lines.append(Text(""))
    return lines or [make_jarvis_line(raw, msg_type)]


# ─── Widgets ───────────────────────────────────────────────────────────────────

class AgentCard(Static):
    def __init__(self, agent_name: str, role: str, tag: str, **kwargs):
        super().__init__(**kwargs)
        self._agent_name = agent_name
        self._role = role
        self._tag = tag

    def compose(self) -> ComposeResult:
        key = self._agent_name.lower()
        yield Label(f"{self._tag}  {self._agent_name} / {self._role}", classes="agent-name", id=f"hdr-{key}")
        yield Label("  status : idle", classes="agent-status idle", id=f"status-{key}")
        yield Label("  task   : --",   classes="agent-task",        id=f"task-{key}")
        yield Label("  tok/s  : 0.0",  classes="agent-tokens",      id=f"tps-{key}")

    def update_status(self, status: str, task: str = "", tps: float = 0.0):
        key = self._agent_name.lower()
        try:
            s = self.query_one(f"#status-{key}", Label)
            s.update(f"  status : {status}")
            s.set_classes(
                "agent-status active" if status == "running"
                else "agent-status error" if status == "error"
                else "agent-status idle"
            )
            self.query_one(f"#task-{key}", Label).update(f"  task   : {(task or '--')[:32]}")
            self.query_one(f"#tps-{key}", Label).update(f"  tok/s  : {tps:.1f}")
        except NoMatches:
            pass
        if status == "running":
            self.add_class("active")
        else:
            self.remove_class("active")


class BootScreen(Widget):
    frame: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        yield Static(ASCII_LOGO, id="boot-logo")
        yield Static("", id="boot-bar")
        yield Static("Initialising...", id="boot-msg")

    def on_mount(self):
        # Store timer handle so we can stop it after boot completes
        self._boot_timer = self.set_interval(0.12, self.advance)

    def advance(self):
        if self.frame < len(BOOT_FRAMES):
            try:
                self.query_one("#boot-bar", Static).update(BOOT_FRAMES[self.frame])
            except NoMatches:
                pass
            self.frame += 1
        else:
            # Stop the timer FIRST — prevents any further advance() calls
            self._boot_timer.stop()
            self.app.finish_boot()


# ─── Main App ──────────────────────────────────────────────────────────────────

class JarvisCLI(App):
    CSS   = CSS
    TITLE = "JARVIS CLI"

    BINDINGS = [
        Binding("ctrl+c",       "quit",         "Quit",        show=True),
        Binding("ctrl+q",       "quit",         "Quit",        show=True),
        Binding("ctrl+l",       "clear_chat",   "Clear",       show=True),
        Binding("ctrl+shift+c", "copy_last",    "Copy",        show=False),
        Binding("up",           "history_up",   "Hist-up",     show=False),
        Binding("down",         "history_down", "Hist-dn",     show=False),
    ]

    def __init__(self):
        super().__init__()
        self._history:       list[str] = []
        self._history_idx:   int = -1
        self._stopping:      bool = False
        self._boot_done:     bool = False   # guard: finish_boot runs exactly once
        self._cwd:           str  = os.getcwd()  # capture launch directory
        self._agents:        dict = {}  # {id: {"task": str, "status": str}}
        self._agent_counter: int  = 0
        self._pending_rm:    str  = ""  # path awaiting /rm confirmation
        self._last_response: str  = ""  # last Jarvis response text
        self._chat_lines:    list = []  # plain-text log for /save

        # Background WS thread state (Jarvis)
        self._ws_loop:       Optional[asyncio.AbstractEventLoop] = None
        self._ws_thread:     Optional[threading.Thread] = None
        self._send_queue:    Optional[asyncio.Queue] = None  # lives in _ws_loop
        # Bus send queue (same background loop)
        self._bus_send_queue: Optional[asyncio.Queue] = None

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Container(BootScreen(), id="boot-screen")

        with Container(id="main-ui"):
            with Horizontal(id="header"):
                with Container(id="logo-container"):
                    yield Static(ASCII_LOGO, id="logo")
                with Vertical(id="header-right"):
                    yield Label(f"v{VERSION}", id="version-label")
                    yield Label("[--] Jarvis  disconnected", id="conn-jarvis")
                    yield Label("[--] Bus     disconnected", id="conn-bus")

            with Horizontal(id="main-split"):
                with Vertical(id="chat-panel"):
                    yield RichLog(id="chat-log", highlight=True, markup=True,
                                  auto_scroll=True, wrap=True)
                    with Vertical(id="input-area"):
                        yield Label("─" * 80, id="input-separator-top")
                        with Horizontal(id="prompt-row"):
                            yield Label(">", id="prompt-symbol")
                            yield Input(
                                placeholder="Type a message, or 'exit' to quit...",
                                id="cmd-input",
                            )
                        yield Label(
                            "ctrl+c cancel task  ctrl+l clear  ctrl+q quit  up/dn history",
                            id="input-hint",
                        )

                with Vertical(id="agent-panel"):
                    yield Static("[ AGENTS ]", id="agent-panel-title")
                    with Container(id="agents-container"):
                        yield AgentCard("Gemma",    "Architect", "[GEMMA]",
                                        id="card-gemma",    classes="agent-card")
                        yield AgentCard("Qwen",     "Editor",    "[QWEN]",
                                        id="card-qwen",     classes="agent-card")
                        yield AgentCard("Cantivia", "Runner",    "[TASK]",
                                        id="card-cantivia", classes="agent-card")
                    yield Static("[ BUS ]", id="bus-feed-title")
                    yield RichLog(id="bus-log", highlight=False, markup=False,
                                  auto_scroll=True, wrap=True)

    def on_mount(self):
        try:
            self.query_one("#main-ui").display = False
        except NoMatches:
            pass

    # ── Boot ──────────────────────────────────────────────────────────────────

    def finish_boot(self):
        # Hard guard — must only run once no matter how many times called
        if self._boot_done:
            return
        self._boot_done = True

        try:
            self.query_one("#boot-screen").display = False
            self.query_one("#main-ui").display = True
        except NoMatches:
            pass
        self._print_welcome()
        self._start_ws_thread()
        self._update_cwd_prompt()
        try:
            self.query_one("#cmd-input", Input).focus()
        except NoMatches:
            pass

    def _print_welcome(self):
        log = self._chat_log()
        if not log:
            return
        log.write(Text(""))
        t = Text()
        t.append("  JARVIS CLI ", style="bold #7C3AED")
        t.append(f"v{VERSION}  ", style="#6B6B8A")
        t.append("[OK] ready", style="#10B981")
        log.write(t)
        log.write(Text(
            "  Type a message and press Enter.  "
            "Type 'exit' or press ctrl+q to quit.",
            style="#6B6B8A",
        ))
        log.write(Text(""))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _chat_log(self) -> Optional[RichLog]:
        try:
            return self.query_one("#chat-log", RichLog)
        except NoMatches:
            return None

    def _bus_log(self) -> Optional[RichLog]:
        try:
            return self.query_one("#bus-log", RichLog)
        except NoMatches:
            return None

    def _write_chat(self, line: "Text | str"):
        log = self._chat_log()
        if log:
            log.write(line)
        # record plain text for /save
        plain = line.plain if isinstance(line, Text) else str(line)
        if plain.strip():
            self._chat_lines.append(plain)

    def _write_bus(self, text: str):
        log = self._bus_log()
        if log:
            t = Text()
            t.append(f"[{ts()}] ", style="dim #2D2D3F")
            t.append(text, style="#6B6B8A")
            log.write(t)

    def _get_effective_cwd(self) -> str:
        """Return active working directory: /cd override > launch cwd."""
        if CWD_FILE.exists():
            try:
                val = CWD_FILE.read_text().strip()
                if val:
                    return val
            except Exception:
                pass
        return self._cwd

    def _update_cwd_prompt(self):
        """Update the prompt label to show [~/shortened/path] >"""
        try:
            cwd = self._get_effective_cwd()
            home = str(Path.home())
            if cwd.startswith(home):
                cwd = "~" + cwd[len(home):]
            label = self.query_one("#prompt-symbol", Label)
            label.update(f"[{cwd}] >")
        except NoMatches:
            pass

    # ── WebSocket thread ──────────────────────────────────────────────────────
    #
    # Architecture:
    #   _start_ws_thread()     — creates a new asyncio loop + daemon thread
    #   _run_ws_loop()         — thread entry; creates send_queue, runs _ws_worker
    #   _ws_worker()           — reconnecting loop (in background loop)
    #   _ws_sender(ws)         — reads send_queue, writes to WebSocket
    #   _ws_receiver(ws)       — reads WebSocket, calls back on Textual thread
    #   _enqueue_send(payload) — thread-safe: schedules put_nowait in background loop
    #
    # Textual thread → WS thread:  _enqueue_send  (call_soon_threadsafe)
    # WS thread      → Textual:    call_from_thread(_handle_jarvis_msg)

    def _start_ws_thread(self):
        self._ws_loop = asyncio.new_event_loop()
        self._ws_thread = threading.Thread(
            target=self._run_ws_loop,
            daemon=True,
            name="jarvis-ws",
        )
        self._ws_thread.start()

    def _run_ws_loop(self):
        """Runs entirely in the background daemon thread."""
        asyncio.set_event_loop(self._ws_loop)
        self._send_queue = asyncio.Queue()
        self._bus_send_queue = asyncio.Queue()

        async def _run_both():
            await asyncio.gather(
                self._ws_worker(),
                self._bus_ws_worker(),
            )

        self._ws_loop.run_until_complete(_run_both())

    async def _ws_worker(self):
        """Reconnecting WebSocket loop — background thread only."""
        while not self._stopping:
            try:
                async with websockets.connect(
                    JARVIS_WS,
                    ping_interval=20,
                    ping_timeout=10,
                    open_timeout=5,
                ) as ws:
                    # Notify UI: connected
                    self.call_from_thread(self._on_jarvis_connected)

                    # Run sender + receiver concurrently; stop both when either exits
                    sender   = asyncio.create_task(self._ws_sender(ws))
                    receiver = asyncio.create_task(self._ws_receiver(ws))
                    _done, pending = await asyncio.wait(
                        [sender, receiver],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

            except (ConnectionRefusedError, OSError, TimeoutError):
                pass  # server not up yet — retry silently
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as exc:
                self.call_from_thread(self._write_bus, f"[ERR] Jarvis: {exc}")
            finally:
                # Always notify UI of disconnect (even if we were never connected)
                self.call_from_thread(self._on_jarvis_disconnected)

            if not self._stopping:
                await asyncio.sleep(3)

    async def _ws_sender(self, ws):
        """Read payloads from send_queue and write them to the WebSocket."""
        while True:
            payload = await self._send_queue.get()
            if payload is None:           # shutdown sentinel
                return
            try:
                await ws.send(payload)
            except Exception:
                return                    # let _ws_worker reconnect

    async def _ws_receiver(self, ws):
        """Read every message from WebSocket and dispatch to Textual thread."""
        async for raw in ws:
            self.call_from_thread(self._handle_jarvis_msg, raw)

    def _enqueue_send(self, payload: str):
        """Thread-safe send from Textual thread into the Jarvis WS background loop."""
        if self._ws_loop is not None and self._send_queue is not None:
            self._ws_loop.call_soon_threadsafe(
                self._send_queue.put_nowait, payload
            )

    def _enqueue_bus_send(self, payload: str):
        """Thread-safe send from Textual thread into the bus WS background loop."""
        if self._ws_loop is not None and self._bus_send_queue is not None:
            self._ws_loop.call_soon_threadsafe(
                self._bus_send_queue.put_nowait, payload
            )

    async def _bus_ws_worker(self):
        """Reconnecting bus WebSocket loop — runs in the same background thread."""
        while not self._stopping:
            try:
                async with websockets.connect(
                    BUS_WS,
                    ping_interval=20,
                    ping_timeout=10,
                    open_timeout=5,
                ) as ws:
                    await ws.send(json.dumps({"register": "cli"}))
                    self.call_from_thread(self._on_bus_connected)

                    async def bus_sender():
                        while True:
                            payload = await self._bus_send_queue.get()
                            if payload is None:
                                return
                            try:
                                await ws.send(payload)
                            except Exception:
                                return

                    async def bus_receiver():
                        async for raw in ws:
                            self.call_from_thread(self._handle_bus_msg, raw)

                    sender   = asyncio.create_task(bus_sender())
                    receiver = asyncio.create_task(bus_receiver())
                    _done, pending = await asyncio.wait(
                        [sender, receiver],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

            except (ConnectionRefusedError, OSError, TimeoutError):
                pass
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as exc:
                self.call_from_thread(self._write_bus, f"[ERR] Bus: {exc}")
            finally:
                self.call_from_thread(self._on_bus_disconnected)

            if not self._stopping:
                await asyncio.sleep(3)

    def _on_bus_connected(self):
        self._update_conn_label("bus", True)
        self._write_bus("[OK] Bus connected")

    def _on_bus_disconnected(self):
        self._update_conn_label("bus", False)

    def _handle_bus_msg(self, raw: str):
        """Handle messages received from the bus (e.g. AGENT_STATUS)."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        etype = data.get("type", "")

        if etype == "AGENT_STATUS":
            agent_id = data.get("agent_id", "?")
            status   = data.get("status", "")
            message  = data.get("message", "")
            if agent_id in self._agents:
                self._agents[agent_id]["status"] = "done" if status == "done" else status
            label = f"[{agent_id}] {status}: {message[:80]}" if message else f"[{agent_id}] {status}"
            self._write_chat(make_jarvis_line(label, "status"))

        elif etype in ("STATUS", "RESULT"):
            msg = strip_ansi(str(data.get("msg", "") or data.get("content", ""))).strip()
            if msg:
                self._write_bus(msg)

    # ── WS callbacks (called on Textual thread via call_from_thread) ──────────

    def _on_jarvis_connected(self):
        self._update_conn_label("jarvis", True)
        self._write_bus("[OK] Jarvis connected")

    def _on_jarvis_disconnected(self):
        self._update_conn_label("jarvis", False)

    def _handle_jarvis_msg(self, raw: str):
        """
        Decode and display one message from Jarvis.
        Called on Textual's main thread via call_from_thread — safe to update UI.
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            clean = strip_ansi(raw).strip()
            if clean:
                self._write_chat(make_jarvis_line(clean, "stream"))
            return

        msg_type = data.get("type", "stream")
        raw_text = data.get("msg", "") or data.get("content", "") or ""
        content  = strip_ansi(str(raw_text)).strip()

        if msg_type == "ack":
            return  # ignore entirely

        elif msg_type == "status":
            if content:
                self._write_chat(make_jarvis_line(content, "status"))

        elif msg_type in ("final", "done"):
            if content:
                self._last_response = content
                for line in parse_and_render(content, "final"):
                    self._write_chat(line)
            sep = Text()
            sep.append("  " + "─" * 60, style="#2D2D3F")
            self._write_chat(sep)

        elif msg_type == "error":
            self._write_chat(make_jarvis_line(content or "Error from Jarvis.", "error"))

        elif msg_type == "stream":
            if content:
                self._write_chat(make_jarvis_line(content, "stream"))

        elif msg_type == "agent_update":
            agent_id = data.get("agent_id", "?")
            step     = data.get("step", 0)
            action   = data.get("action", "?")
            obs      = strip_ansi(str(data.get("observation", ""))).strip()
            t = Text()
            t.append(f"[{ts()}] ", style="dim #6B6B8A")
            t.append(f"[AGENT-{agent_id}] ", style="bold #F59E0B")
            t.append(f"Step {step}: ", style="#FCD34D")
            t.append(f"{action}", style="bold #FBBF24")
            if obs:
                t.append(f" — {obs[:100]}", style="#9CA3AF")
            self._write_chat(t)
            self._write_bus(f"[AGENT-{agent_id}] step={step} {action}")

        # all other types: silently ignore

    def _update_conn_label(self, which: str, connected: bool):
        try:
            lbl    = self.query_one(f"#conn-{which}", Label)
            name   = "Jarvis " if which == "jarvis" else "Bus    "
            status = "connected   " if connected else "disconnected"
            color  = "#10B981" if connected else "#EF4444"
            marker = "[OK]" if connected else "[--]"
            t = Text()
            t.append(marker + " ", style=color)
            t.append(name,         style="#9090A8")
            t.append(status,       style=color)
            lbl.update(t)
        except NoMatches:
            pass

    def _update_agent(self, agent: str, status: str, task: str = "", tps: float = 0.0):
        al = agent.lower()
        card_id = (
            "#card-gemma"    if "gemma"    in al else
            "#card-qwen"     if "qwen"     in al else
            "#card-cantivia" if "cantivia" in al or "runner" in al else
            None
        )
        if card_id:
            try:
                self.query_one(card_id, AgentCard).update_status(status, task, tps)
            except NoMatches:
                pass

    # ── Box helper ────────────────────────────────────────────────────────────

    def _write_box(self, title: str, lines: list):
        """Write output in a formatted box to the chat panel."""
        bar = "─" * max(0, 52 - len(title) - 3)
        header = Text()
        header.append(f"┌─ {title} ", style="bold #7C3AED")
        header.append(bar, style="#2D2D3F")
        self._write_chat(header)
        shown = [l for l in lines if l is not None][:80]
        for line in shown:
            t = Text()
            t.append("│ ", style="#2D2D3F")
            t.append(str(line), style="#C8C8D8")
            self._write_chat(t)
        if not shown:
            t = Text()
            t.append("│ ", style="#2D2D3F")
            t.append("(no output)", style="#6B6B8A")
            self._write_chat(t)
        footer = Text()
        footer.append("└" + "─" * 54, style="#2D2D3F")
        self._write_chat(footer)

    def _run_cmd(self, args: list, cwd: str = None) -> tuple[int, str]:
        """Run a subprocess, return (returncode, combined output)."""
        try:
            r = subprocess.run(args, capture_output=True, text=True, cwd=cwd or self._get_effective_cwd())
            out = (r.stdout + r.stderr).strip()
            return r.returncode, out
        except Exception as e:
            return 1, str(e)

    # ── Input handling ────────────────────────────────────────────────────────

    def _handle_slash(self, text: str) -> bool:
        """
        Handle slash commands locally. Returns True if consumed, False if should be sent to Jarvis.
        """
        parts = text.split(None, 1)
        cmd   = parts[0].lower()
        arg   = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/help":
            lines = [
                Text(""),
                _dim_line("─── Files ───────────────────────────────────────────────"),
                _cmd_line("/ls [path]",          "List files in dir"),
                _cmd_line("/cat [file]",          "Show file contents"),
                _cmd_line("/open [file]",         "Open file in default app"),
                _cmd_line("/mkdir [name]",        "Create directory"),
                _cmd_line("/rm [file]",           "Delete file (with confirmation)"),
                _dim_line("─── Git ─────────────────────────────────────────────────"),
                _cmd_line("/git status",          "git status"),
                _cmd_line("/git add",             "git add -A"),
                _cmd_line("/git commit [msg]",    "git commit -m"),
                _cmd_line("/git push",            "git push"),
                _cmd_line("/git log",             "Last 5 commits"),
                _dim_line("─── Cowork ──────────────────────────────────────────────"),
                _cmd_line("/start",               "Start all cowork services"),
                _cmd_line("/stop",                "Stop all cowork services"),
                _cmd_line("/status",              "Show port status"),
                _cmd_line("/logs [service]",      "Tail service log (jarvis/bus/gemma/qwen/voice)"),
                _cmd_line("/research [topic]",    "Spawn background research agent"),
                _cmd_line("/agent [task]",        "Spawn background agent"),
                _cmd_line("/agents",              "List running agents"),
                _cmd_line("/kill [id]",           "Kill agent by id"),
                _cmd_line("/cantivia [task]",     "Send task to cantivia pipeline"),
                _dim_line("─── System ──────────────────────────────────────────────"),
                _cmd_line("/time",                "Show current time"),
                _cmd_line("/battery",             "Show battery status"),
                _cmd_line("/wifi",                "Show WiFi network"),
                _cmd_line("/volume [0-100]",      "Set system volume"),
                _cmd_line("/screenshot",          "Take screenshot to desktop"),
                _dim_line("─── Navigation ──────────────────────────────────────────"),
                _cmd_line("/cd [path]",           "Change working directory"),
                _cmd_line("/pwd",                 "Show working directory"),
                _cmd_line("/home",                "Go to home directory"),
                _cmd_line("/projects",            "List cowork projects"),
                _cmd_line("/project [name]",      "Set current project context"),
                _dim_line("─── General ─────────────────────────────────────────────"),
                _cmd_line("/clear",               "Clear chat panel"),
                _cmd_line("/copy",                "Copy last Jarvis response to clipboard"),
                _cmd_line("/save [filename]",     "Save chat history to ~/Desktop/[filename].txt"),
                _cmd_line("/exit",                "Quit the CLI"),
                Text(""),
            ]
            for l in lines:
                self._write_chat(l)
            return True

        if cmd == "/clear":
            self.action_clear_chat()
            return True

        if cmd == "/exit":
            self._do_exit()
            return True

        if cmd == "/pwd":
            COWORK_DIR.mkdir(parents=True, exist_ok=True)
            cwd = CWD_FILE.read_text().strip() if CWD_FILE.exists() else str(Path.cwd())
            self._write_chat(make_jarvis_line(f"Working dir: {cwd}", "status"))
            return True

        if cmd == "/cd":
            if not arg:
                self._write_chat(make_jarvis_line("Usage: /cd [path]", "error"))
                return True
            expanded = os.path.expanduser(arg)
            if os.path.isdir(expanded):
                COWORK_DIR.mkdir(parents=True, exist_ok=True)
                CWD_FILE.write_text(expanded)
                self._cwd = expanded
                self._update_cwd_prompt()
                self._write_chat(make_jarvis_line(f"Working dir set to: {expanded}", "status"))
            else:
                self._write_chat(make_jarvis_line(f"Directory not found: {expanded}", "error"))
            return True

        if cmd == "/project":
            COWORK_DIR.mkdir(parents=True, exist_ok=True)
            if not arg:
                current = PROJECT_FILE.read_text().strip() if PROJECT_FILE.exists() else "none"
                self._write_chat(make_jarvis_line(f"Current project: {current}", "status"))
            else:
                PROJECT_FILE.write_text(arg)
                self._write_chat(make_jarvis_line(f"Project set to: {arg}", "status"))
            return True

        if cmd == "/projects":
            projects_dir = Path.home() / "cowork" / "projects"
            if not projects_dir.exists():
                self._write_chat(make_jarvis_line("No projects directory found at ~/cowork/projects/", "status"))
                return True
            projects = [p.name for p in projects_dir.iterdir() if p.is_dir()]
            if not projects:
                self._write_chat(make_jarvis_line("No projects found.", "status"))
            else:
                current = PROJECT_FILE.read_text().strip() if PROJECT_FILE.exists() else ""
                self._write_chat(make_jarvis_line("Projects:", "status"))
                for p in sorted(projects):
                    marker = " ← current" if p == current else ""
                    self._write_chat(make_jarvis_line(f"  {p}{marker}", "final"))
            return True

        if cmd == "/agent":
            if not arg:
                self._write_chat(make_jarvis_line("Usage: /agent [task description]", "error"))
                return True
            self._agent_counter += 1
            agent_id = f"AGENT-{self._agent_counter}"
            self._agents[agent_id] = {"task": arg, "status": "running"}
            cwd = self._get_effective_cwd()
            payload = {
                "type": "TASK_CODING",
                "msg": arg,
                "cwd": cwd,
                "agent_id": agent_id,
            }
            self._write_chat(make_jarvis_line(f"[{agent_id}] Spawned: {arg}", "status"))
            self._enqueue_bus_send(json.dumps(payload))
            return True

        if cmd == "/agents":
            if not self._agents:
                self._write_chat(make_jarvis_line("No agents running.", "status"))
            else:
                self._write_chat(make_jarvis_line("Running agents:", "status"))
                for aid, info in self._agents.items():
                    status_style = "final" if info["status"] == "done" else "status"
                    self._write_chat(make_jarvis_line(
                        f"  [{aid}]  {info['status']:<8}  {info['task']}", status_style
                    ))
            return True

        if cmd == "/kill":
            if not arg:
                self._write_chat(make_jarvis_line("Usage: /kill [agent-id]  e.g. /kill AGENT-1", "error"))
                return True
            aid = arg.upper()
            if aid in self._agents:
                self._agents.pop(aid)
                self._write_chat(make_jarvis_line(f"[{aid}] Cancelled.", "status"))
            else:
                self._write_chat(make_jarvis_line(f"No agent with id: {aid}", "error"))
            return True

        if cmd == "/cantivia":
            if not arg:
                self._write_chat(make_jarvis_line("Usage: /cantivia [task description]", "error"))
                return True
            cwd = CWD_FILE.read_text().strip() if CWD_FILE.exists() else str(Path.cwd())
            payload = {"message": f"cantivia {arg}", "cwd": cwd}
            self._write_chat(make_user_line(f"/cantivia {arg}"))
            self._enqueue_send(json.dumps(payload))
            return True

        # ── File & folder ──────────────────────────────────────────────────────

        if cmd == "/ls":
            target = os.path.expanduser(arg) if arg else self._get_effective_cwd()
            try:
                entries = sorted(Path(target).iterdir(), key=lambda p: (p.is_file(), p.name))
                lines = [("📁 " if e.is_dir() else "   ") + e.name for e in entries]
                self._write_box(f"/ls {target}", lines or ["(empty)"])
            except Exception as e:
                self._write_chat(make_jarvis_line(str(e), "error"))
            return True

        if cmd == "/cat":
            if not arg:
                self._write_chat(make_jarvis_line("Usage: /cat [file]", "error"))
                return True
            path = Path(os.path.expanduser(arg))
            if not path.is_absolute():
                path = Path(self._get_effective_cwd()) / arg
            try:
                content = path.read_text(errors="replace")
                ext = path.suffix.lstrip(".") or "txt"
                lines = [f"[{ext}]  {path}"] + content.splitlines()
                self._write_box(f"/cat {path.name}", lines)
            except Exception as e:
                self._write_chat(make_jarvis_line(str(e), "error"))
            return True

        if cmd == "/open":
            if not arg:
                self._write_chat(make_jarvis_line("Usage: /open [file]", "error"))
                return True
            path = os.path.expanduser(arg)
            if not os.path.isabs(path):
                path = os.path.join(self._get_effective_cwd(), arg)
            os.system(f'open "{path}"')
            self._write_chat(make_jarvis_line(f"Opened: {path}", "status"))
            return True

        if cmd == "/mkdir":
            if not arg:
                self._write_chat(make_jarvis_line("Usage: /mkdir [name]", "error"))
                return True
            path = Path(self._get_effective_cwd()) / arg
            try:
                path.mkdir(parents=True, exist_ok=True)
                self._write_chat(make_jarvis_line(f"Created: {path}", "status"))
            except Exception as e:
                self._write_chat(make_jarvis_line(str(e), "error"))
            return True

        if cmd == "/rm":
            if not arg:
                self._write_chat(make_jarvis_line("Usage: /rm [file]", "error"))
                return True
            path = Path(self._get_effective_cwd()) / arg if not os.path.isabs(arg) else Path(arg)
            if not path.exists():
                self._write_chat(make_jarvis_line(f"Not found: {path}", "error"))
                return True
            # Note: confirmation via input widget is async; use a simple inline approach
            self._write_chat(make_jarvis_line(
                f"Type 'yes' and press Enter to delete: {path}", "status"
            ))
            self._pending_rm = str(path)
            return True

        # ── Git shortcuts ──────────────────────────────────────────────────────

        if cmd == "/git":
            sub_parts = arg.split(None, 1)
            subcmd   = sub_parts[0].lower() if sub_parts else ""
            sub_arg  = sub_parts[1] if len(sub_parts) > 1 else ""
            cwd = self._get_effective_cwd()

            if subcmd == "status":
                rc, out = self._run_cmd(["git", "status"], cwd)
                self._write_box("/git status", out.splitlines())
            elif subcmd == "add":
                rc, out = self._run_cmd(["git", "add", "-A"], cwd)
                self._write_box("/git add", ["Staged all changes."] if rc == 0 else out.splitlines())
            elif subcmd == "commit":
                if not sub_arg:
                    self._write_chat(make_jarvis_line("Usage: /git commit [message]", "error"))
                else:
                    rc, out = self._run_cmd(["git", "commit", "-m", sub_arg], cwd)
                    self._write_box("/git commit", out.splitlines())
            elif subcmd == "push":
                rc, out = self._run_cmd(["git", "push"], cwd)
                self._write_box("/git push", out.splitlines())
            elif subcmd == "log":
                rc, out = self._run_cmd(["git", "log", "--oneline", "-5"], cwd)
                self._write_box("/git log", out.splitlines())
            else:
                self._write_chat(make_jarvis_line(
                    "Usage: /git [status|add|commit <msg>|push|log]", "error"
                ))
            return True

        # ── Cowork shortcuts ───────────────────────────────────────────────────

        if cmd == "/start":
            script = Path.home() / "cowork" / "start.sh"
            if script.exists():
                rc, out = self._run_cmd(["bash", str(script)])
                self._write_box("/start", out.splitlines() or ["Services starting..."])
            else:
                self._write_chat(make_jarvis_line(f"Start script not found: {script}", "error"))
            return True

        if cmd == "/stop":
            script = Path.home() / "cowork" / "stop.sh"
            if script.exists():
                rc, out = self._run_cmd(["bash", str(script)])
                self._write_box("/stop", out.splitlines() or ["Services stopped."])
            else:
                self._write_chat(make_jarvis_line(f"Stop script not found: {script}", "error"))
            return True

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
                rc, out = self._run_cmd(["lsof", "-ti", f":{port}"])
                pid = out.strip().splitlines()[0] if out.strip() else ""
                status = f"[UP]  pid={pid}" if pid else "[--]  not running"
                color_marker = "✓" if pid else "✗"
                lines.append(f"{color_marker}  {name:<8}  :{port}  {status}")
            self._write_box("/status  port check", lines)
            return True

        if cmd == "/logs":
            service = arg.lower() if arg else ""
            valid = ("jarvis", "bus", "gemma", "qwen", "voice")
            if service not in valid:
                self._write_chat(make_jarvis_line(
                    f"Usage: /logs [{'/'.join(valid)}]", "error"
                ))
                return True
            log_path = f"/tmp/{service}.log"
            rc, out = self._run_cmd(["tail", "-n", "20", log_path])
            self._write_box(f"/logs {service}", out.splitlines() if out else [f"No log at {log_path}"])
            return True

        if cmd == "/research":
            if not arg:
                self._write_chat(make_jarvis_line("Usage: /research [topic]", "error"))
                return True
            self._agent_counter += 1
            agent_id = f"AGENT-{self._agent_counter}"
            self._agents[agent_id] = {"task": f"research: {arg}", "status": "running"}
            payload = {
                "type": "TASK_RESEARCH",
                "msg": arg,
                "cwd": self._get_effective_cwd(),
                "agent_id": agent_id,
            }
            self._write_chat(make_jarvis_line(f"[{agent_id}] Research started: {arg}", "status"))
            self._enqueue_bus_send(json.dumps(payload))
            return True

        # ── System ─────────────────────────────────────────────────────────────

        if cmd == "/time":
            now = datetime.now().strftime("%A, %B %d %Y  %H:%M:%S")
            self._write_box("/time", [now])
            return True

        if cmd == "/battery":
            rc, out = self._run_cmd(["pmset", "-g", "binfo"])
            lines = [l for l in out.splitlines() if "percent" in l.lower() or "charging" in l.lower()]
            self._write_box("/battery", lines or out.splitlines()[:5] or ["No battery info"])
            return True

        if cmd == "/wifi":
            rc, out = self._run_cmd(["networksetup", "-getairportnetwork", "en0"])
            self._write_box("/wifi", out.splitlines())
            return True

        if cmd == "/volume":
            if not arg or not arg.isdigit():
                self._write_chat(make_jarvis_line("Usage: /volume [0-100]", "error"))
                return True
            vol = max(0, min(100, int(arg)))
            os.system(f'osascript -e "set volume output volume {vol}"')
            self._write_chat(make_jarvis_line(f"Volume set to {vol}%", "status"))
            return True

        if cmd == "/screenshot":
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = os.path.expanduser(f"~/Desktop/screenshot_{ts_str}.png")
            rc, out = self._run_cmd(["screencapture", "-i", dest])
            if rc == 0:
                self._write_chat(make_jarvis_line(f"Screenshot saved: {dest}", "status"))
            else:
                self._write_chat(make_jarvis_line(out or "Screenshot cancelled.", "status"))
            return True

        # ── Navigation ─────────────────────────────────────────────────────────

        if cmd == "/home":
            home = str(Path.home())
            COWORK_DIR.mkdir(parents=True, exist_ok=True)
            CWD_FILE.write_text(home)
            self._cwd = home
            self._update_cwd_prompt()
            self._write_chat(make_jarvis_line(f"Working dir: {home}", "status"))
            return True

        if cmd == "/copy":
            if not self._last_response:
                self._write_chat(make_jarvis_line("No Jarvis response to copy yet.", "error"))
                return True
            if not _PYPERCLIP_OK:
                self._write_chat(make_jarvis_line(
                    "pyperclip not installed. Run: pip install pyperclip", "error"))
                return True
            pyperclip.copy(self._last_response)
            self._write_chat(make_jarvis_line("[Copied to clipboard]", "status"))
            return True

        if cmd == "/save":
            filename = arg if arg else f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            if not filename.endswith(".txt"):
                filename += ".txt"
            dest = Path.home() / "Desktop" / filename
            try:
                dest.write_text("\n".join(self._chat_lines), encoding="utf-8")
                self._write_chat(make_jarvis_line(f"Chat saved to: {dest}", "status"))
            except Exception as e:
                self._write_chat(make_jarvis_line(f"Save failed: {e}", "error"))
            return True

        return False  # unknown slash command — fall through to Jarvis

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "cmd-input":
            return
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""

        if text.lower() in ("exit", "quit"):
            self._do_exit()
            return

        # /rm confirmation check
        if self._pending_rm:
            path = self._pending_rm
            self._pending_rm = ""
            if text.lower() == "yes":
                try:
                    import shutil
                    p = Path(path)
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                    self._write_chat(make_jarvis_line(f"Deleted: {path}", "status"))
                except Exception as e:
                    self._write_chat(make_jarvis_line(str(e), "error"))
            else:
                self._write_chat(make_jarvis_line("Cancelled.", "status"))
            return

        # Slash commands — handled locally, not sent to Jarvis
        if text.startswith("/"):
            self._write_chat(make_user_line(text))
            self._handle_slash(text)
            return

        if not self._history or self._history[-1] != text:
            self._history.append(text)
        self._history_idx = -1

        self._write_chat(make_user_line(text))
        self._enqueue_send(json.dumps({"message": text, "cwd": self._get_effective_cwd()}))

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_quit(self):
        """Ctrl+Q — clean shutdown."""
        self._do_exit()

    def _do_exit(self):
        self._stopping = True
        # Unblock the sender coroutine so the thread can exit cleanly
        if self._ws_loop is not None and self._send_queue is not None:
            self._ws_loop.call_soon_threadsafe(self._send_queue.put_nowait, None)
        self.exit()

    def action_copy_last(self):
        """Ctrl+Shift+C — copy last Jarvis response to clipboard."""
        if not self._last_response:
            self._write_chat(make_jarvis_line("No Jarvis response to copy yet.", "error"))
            return
        if not _PYPERCLIP_OK:
            self._write_chat(make_jarvis_line(
                "pyperclip not installed. Run: pip install pyperclip", "error"))
            return
        pyperclip.copy(self._last_response)
        self._write_chat(make_jarvis_line("[Copied to clipboard]", "status"))

    def action_clear_chat(self):
        log = self._chat_log()
        if log:
            log.clear()
            self._print_welcome()

    def action_history_up(self):
        if not self._history:
            return
        try:
            inp = self.query_one("#cmd-input", Input)
        except NoMatches:
            return
        if self._history_idx == -1:
            self._history_idx = len(self._history) - 1
        elif self._history_idx > 0:
            self._history_idx -= 1
        inp.value = self._history[self._history_idx]
        inp.cursor_position = len(inp.value)

    def action_history_down(self):
        if not self._history or self._history_idx == -1:
            return
        try:
            inp = self.query_one("#cmd-input", Input)
        except NoMatches:
            return
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            inp.value = self._history[self._history_idx]
        else:
            self._history_idx = -1
            inp.value = ""
        inp.cursor_position = len(inp.value)


# ─── Entry point ───────────────────────────────────────────────────────────────

def main():
    JarvisCLI().run()


if __name__ == "__main__":
    main()
