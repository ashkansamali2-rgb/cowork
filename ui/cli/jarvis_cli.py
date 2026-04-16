#!/usr/bin/env python3
"""
Jarvis CLI - Gemini-style terminal interface with framed input
"""
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime

try:
    import pyfiglet
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pyfiglet", "--break-system-packages", "-q"])
    import pyfiglet

try:
    import websockets
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "websockets", "--break-system-packages", "-q"])
    import websockets

from prompt_toolkit import Application, print_formatted_text
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window, FormattedTextControl, ScrollablePane
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.widgets import TextArea, Frame
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.document import Document

JARVIS_WS = "ws://localhost:8001"

# Colors
PURPLE     = "\033[38;2;124;58;237m"
PURPLE_LT  = "\033[38;2;167;139;250m"
PINK       = "\033[38;2;192;132;252m"
DIM        = "\033[2;37m"
RED        = "\033[1;31m"
GREEN      = "\033[1;32m"
YELLOW     = "\033[1;33m"
WHITE      = "\033[0;97m"
BOLD       = "\033[1m"
RESET      = "\033[0m"

ws_conn = None
connected = False
last_response = ""
memory_count = 0
output_lines = []
history_list = []
history_pos = -1


def gradient_logo():
    raw = pyfiglet.figlet_format("JARVIS", font="banner3-D")
    lines = raw.split("\n")
    result = []
    for line in lines:
        if not line.strip():
            result.append("")
            continue
        colored = ""
        visible = [c for c in line if c != " "]
        total = max(len(visible), 1)
        vi = 0
        for ch in line:
            if ch == " ":
                colored += " "
            else:
                t = vi / total
                r = int(124 + t * (192 - 124))
                g = int(58  + t * (132 - 58))
                b = int(237 + t * (252 - 237))
                colored += f"\033[38;2;{r};{g};{b}m{ch}"
                vi += 1
        colored += RESET
        result.append(colored)
    return "\n".join(result)


def append_output(text):
    """Add a line to the output buffer."""
    global output_lines
    output_lines.append(text)


def get_output_text():
    """Return all output as ANSI formatted text for the output window."""
    return ANSI("\n".join(output_lines))


async def connect():
    global ws_conn, connected
    try:
        ws_conn = await websockets.connect(JARVIS_WS, ping_interval=20)
        connected = True
        return True
    except Exception:
        connected = False
        return False


async def reconnect_loop():
    global connected
    while True:
        await asyncio.sleep(3)
        if not connected:
            ok = await connect()
            if ok:
                append_output(f"{PURPLE}◆ Connected to Jarvis.{RESET}")


async def send_message(text):
    global ws_conn, connected, last_response
    if not connected or ws_conn is None:
        append_output(f"{RED}⚠ Not connected. Is Jarvis running? Try: /start{RESET}")
        return

    payload = json.dumps({"type": "chat", "message": text, "source": "cli"})
    await ws_conn.send(payload)

    buffer = ""

    try:
        async for raw in ws_conn:
            msg = json.loads(raw)
            mtype = msg.get("type", "")

            if mtype == "agent_update":
                step = msg.get("step", "")
                tool = msg.get("tool", "")
                width = 44
                label = f" AgentStep {step} "
                bar = "─" * (width - len(label) - 2)
                append_output(f"{DIM}┌─{label}{bar}┐{RESET}")
                append_output(f"{DIM}│ ↳ {YELLOW}{tool}{DIM}  {msg.get('description',''):<{width-6}}│{RESET}")
                append_output(f"{DIM}└{'─' * (width)}┘{RESET}")
                continue

            if mtype in ("chunk", "stream"):
                chunk = msg.get("content", msg.get("text", ""))
                buffer += chunk
                continue

            if mtype in ("response", "final", "done"):
                content = msg.get("content", msg.get("message", msg.get("text", "")))
                if content and not buffer:
                    buffer = content
                last_response = buffer
                append_output(f"\n{PURPLE_LT}✦ {RESET}{WHITE}{buffer}{RESET}\n")
                break

            if mtype == "error":
                append_output(f"{RED}✗ {msg.get('message','Unknown error')}{RESET}")
                break

    except websockets.exceptions.ConnectionClosed:
        connected = False
        append_output(f"{RED}⚠ Connection lost.{RESET}")


def handle_slash(cmd):
    global last_response
    parts = cmd.strip().split(None, 2)
    command = parts[0].lower()

    if command == "/help":
        append_output(f"\n{PURPLE_LT}Commands:{RESET}")
        cmds = [
            ("/help",          "Show this help"),
            ("/memory",        "Show user profile"),
            ("/memory edit",   "Edit user_model.json"),
            ("/memory forget", "Delete a memory key"),
            ("/status",        "Check all ports"),
            ("/copy",          "Copy last response to clipboard"),
            ("/save [file]",   "Save last response to file"),
            ("/git",           "git add -A && commit"),
            ("/clear",         "Clear screen"),
            ("/model",         "Show active models"),
            ("/start",         "Start Jarvis system"),
            ("/stop",          "Cancel current task"),
            ("/exit",          "Quit"),
        ]
        for c, d in cmds:
            append_output(f"  {PURPLE}{c:<22}{RESET}{DIM}{d}{RESET}")
        append_output("")
        return True

    if command == "/clear":
        output_lines.clear()
        return True

    if command == "/exit" or command == "/quit":
        append_output(f"\n{DIM}Goodbye.{RESET}")
        raise SystemExit(0)

    if command == "/copy":
        if last_response:
            subprocess.run(["pbcopy"], input=last_response.encode())
            append_output(f"{GREEN}✓ Copied to clipboard.{RESET}")
        else:
            append_output(f"{DIM}Nothing to copy yet.{RESET}")
        return True

    if command == "/save":
        fname = parts[1] if len(parts) > 1 else f"jarvis_{datetime.now().strftime('%H%M%S')}.txt"
        if last_response:
            with open(fname, "w") as f:
                f.write(last_response)
            append_output(f"{GREEN}✓ Saved to {fname}{RESET}")
        else:
            append_output(f"{DIM}Nothing to save yet.{RESET}")
        return True

    if command == "/memory":
        sub = parts[1] if len(parts) > 1 else ""
        model_path = os.path.expanduser("~/cowork/jarvis/memory/user_model.json")
        if sub == "edit":
            subprocess.run(["nano", model_path])
        elif sub == "forget" and len(parts) > 2:
            try:
                with open(model_path) as f:
                    data = json.load(f)
                key = parts[2]
                deleted = False
                for section in data:
                    if isinstance(data[section], dict) and key in data[section]:
                        del data[section][key]
                        deleted = True
                        break
                if deleted:
                    with open(model_path, "w") as f:
                        json.dump(data, f, indent=2)
                    append_output(f"{GREEN}✓ Forgot: {key}{RESET}")
                else:
                    append_output(f"{DIM}Key not found: {key}{RESET}")
            except Exception as e:
                append_output(f"{RED}✗ {e}{RESET}")
        else:
            try:
                with open(model_path) as f:
                    data = json.load(f)
                append_output(f"\n{PURPLE_LT}[USER PROFILE]{RESET}")
                for section, val in data.items():
                    if isinstance(val, dict):
                        append_output(f"\n{PURPLE}{section.upper()}{RESET}")
                        for k, v in val.items():
                            if v:
                                append_output(f"  {DIM}{k}:{RESET} {WHITE}{v}{RESET}")
                    elif val:
                        append_output(f"  {DIM}{section}:{RESET} {WHITE}{val}{RESET}")
                append_output("")
            except FileNotFoundError:
                append_output(f"{DIM}No user profile yet. Chat with Jarvis to build one.{RESET}")
            except Exception as e:
                append_output(f"{RED}✗ {e}{RESET}")
        return True

    if command == "/forget":
        episodes_path = os.path.expanduser("~/cowork/jarvis/memory/episodes.json")
        try:
            with open(episodes_path) as f:
                eps = json.load(f)
            eps = eps[:-5] if len(eps) > 5 else []
            with open(episodes_path, "w") as f:
                json.dump(eps, f, indent=2)
            append_output(f"{GREEN}✓ Last 5 episodes cleared.{RESET}")
        except Exception as e:
            append_output(f"{RED}✗ {e}{RESET}")
        return True

    if command == "/status":
        append_output(f"\n{DIM}Checking ports...{RESET}")
        for port, label in [(8080, "E4B (fast)"), (8081, "31B (coding)"), (8001, "Jarvis API"), (8002, "Cantivia Bus")]:
            r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                                 f"http://localhost:{port}/health"], capture_output=True, text=True)
            ok = r.stdout.strip() not in ("", "000")
            symbol = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
            append_output(f"  {symbol} {label} :{port}")
        append_output("")
        return True

    if command == "/git":
        msg = parts[1] if len(parts) > 1 else f"checkpoint {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        r = subprocess.run(
            f'cd ~/cowork && git add -A && git commit -m "{msg}"',
            shell=True, capture_output=True, text=True
        )
        append_output(f"{GREEN if r.returncode == 0 else RED}{r.stdout.strip() or r.stderr.strip()}{RESET}")
        return True

    if command == "/model":
        append_output(f"\n  {DIM}Fast (voice):{RESET}  {WHITE}Gemma 4 E4B · port 8080{RESET}")
        append_output(f"  {DIM}Main:{RESET}         {WHITE}Gemma 4 31B · port 8081{RESET}")
        append_output(f"  {DIM}STT:{RESET}          {WHITE}Whisper large-v3-turbo Q4{RESET}")
        append_output(f"  {DIM}TTS:{RESET}          {WHITE}Qwen3-TTS 0.6B{RESET}\n")
        return True

    if command == "/start":
        subprocess.Popen(["bash", "-c", "source ~/.zshrc && start"], shell=False)
        append_output(f"{DIM}Starting Jarvis system...{RESET}")
        return True

    if command == "/stop":
        if ws_conn:
            asyncio.ensure_future(ws_conn.send(json.dumps({"type": "stop"})))
        append_output(f"{DIM}Stop signal sent.{RESET}")
        return True

    return False


CODE_KEYWORDS = {"write", "fix", "create", "build", "update", "add", "refactor",
                 "debug", "implement", "edit", "modify", "delete", "rename"}
FILE_HINTS    = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json",
                 "function", "class", "import", "def ", "const ", "async "}


def maybe_route_cantivia(text):
    lower = text.lower()
    if lower.startswith("cantivia"):
        return text
    has_code_word = any(lower.startswith(w) or f" {w} " in lower for w in CODE_KEYWORDS)
    has_file_hint = any(h in lower for h in FILE_HINTS)
    if has_code_word and has_file_hint:
        append_output(f"{DIM}→ Routing to Cantivia{RESET}")
        return f"cantivia {text}"
    return text


async def main():
    global connected, memory_count, output_lines, history_list, history_pos

    # Build header
    logo = gradient_logo()
    for line in logo.split("\n"):
        append_output(line)
    append_output("")
    append_output(f"{DIM}Tips for getting started:{RESET}")
    append_output(f"{DIM}1. Talk to Jarvis naturally or use voice commands.{RESET}")
    append_output(f'{DIM}2. Prefix coding tasks with "cantivia" or just describe the code change.{RESET}')
    append_output(f"{DIM}3. /help for all commands.{RESET}")
    append_output("")

    # Connect
    ok = await connect()
    if ok:
        append_output(f"{PURPLE}◆ Connected to Jarvis.{RESET}\n")
    else:
        append_output(f"{RED}⚠ Not connected. Is Jarvis running? Try: /start{RESET}\n")

    # Load memory count
    try:
        mp = os.path.expanduser("~/cowork/jarvis/memory/user_model.json")
        with open(mp) as f:
            data = json.load(f)
        memory_count = sum(
            len(v) if isinstance(v, dict) else (1 if v else 0)
            for v in data.values()
        )
    except Exception:
        memory_count = 0

    # Start reconnect loop
    asyncio.ensure_future(reconnect_loop())

    # Output display area
    output_field = FormattedTextControl(get_output_text, focusable=False)
    output_window = Window(content=output_field, wrap_lines=True)

    # Input area with border
    input_area = TextArea(
        height=3,
        prompt=ANSI(f"{PURPLE}> {RESET}"),
        multiline=True,
        wrap_lines=True,
        style="class:input-field",
        dont_extend_height=True,
    )

    # Status bar
    def get_toolbar():
        cwd = os.getcwd().replace(os.path.expanduser("~"), "~")
        status = "connected" if connected else "disconnected"
        return ANSI(f"{DIM} {cwd}  ·  {status}  ·  Gemma 4 31B  ·  Memory: {memory_count} facts{RESET}")

    toolbar_control = FormattedTextControl(get_toolbar)
    toolbar_window = Window(content=toolbar_control, height=1, style="class:toolbar")

    # Key bindings
    kb = KeyBindings()

    @kb.add("enter")
    def on_enter(event):
        text = input_area.text.strip()
        if not text:
            return
        # Add to history
        history_list.append(text)
        global history_pos
        history_pos = -1
        # Clear input
        input_area.text = ""
        # Echo what user said
        append_output(f"{PURPLE}> {RESET}{text}")
        # Handle
        if text.startswith("/"):
            try:
                handle_slash(text)
            except SystemExit:
                event.app.exit()
            return
        routed = maybe_route_cantivia(text)
        asyncio.ensure_future(send_message(routed))

    @kb.add("escape", "enter")
    def on_alt_enter(event):
        input_area.buffer.insert_text("\n")

    @kb.add("c-c")
    def on_ctrl_c(event):
        if ws_conn:
            asyncio.ensure_future(ws_conn.send(json.dumps({"type": "stop"})))
        input_area.text = ""
        append_output(f"{DIM}Cancelled.{RESET}")

    @kb.add("c-d")
    def on_ctrl_d(event):
        append_output(f"\n{DIM}Goodbye.{RESET}")
        event.app.exit()

    @kb.add("up")
    def on_up(event):
        global history_pos
        if not history_list:
            return
        if history_pos == -1:
            history_pos = len(history_list) - 1
        elif history_pos > 0:
            history_pos -= 1
        input_area.text = history_list[history_pos]
        input_area.buffer.cursor_position = len(input_area.text)

    @kb.add("down")
    def on_down(event):
        global history_pos
        if history_pos == -1:
            return
        if history_pos < len(history_list) - 1:
            history_pos += 1
            input_area.text = history_list[history_pos]
            input_area.buffer.cursor_position = len(input_area.text)
        else:
            history_pos = -1
            input_area.text = ""

    # Layout
    root = HSplit([
        ScrollablePane(output_window),
        Frame(input_area, title="", style="class:input-frame"),
        toolbar_window,
    ])

    style = Style.from_dict({
        "input-field": "#f5f0e8",
        "input-frame": "#7c3aed",
        "toolbar": "bg:#1a1a1a #666666",
    })

    app = Application(
        layout=Layout(root, focused_element=input_area),
        key_bindings=kb,
        style=style,
        full_screen=True,
        mouse_support=True,
    )

    await app.run_async()


if __name__ == "__main__":
    asyncio.run(main())
