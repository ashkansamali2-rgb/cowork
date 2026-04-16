#!/usr/bin/env python3
"""
Jarvis CLI - Gemini-style terminal interface
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

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style

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


def out(text):
    print_formatted_text(ANSI(text))


def gradient_logo():
    raw = pyfiglet.figlet_format("JARVIS", font="big")
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


def print_header():
    os.system("clear")
    out(gradient_logo())
    out("")
    out(f"{DIM}Tips for getting started:{RESET}")
    out(f"{DIM}1. Talk to Jarvis naturally or use voice commands.{RESET}")
    out(f'{DIM}2. Prefix coding tasks with "cantivia" or just describe the code change.{RESET}')
    out(f"{DIM}3. /help for all commands.{RESET}")
    out("")


def print_status():
    status = f"{GREEN}connected{RESET}" if connected else f"{RED}disconnected{RESET}"
    cwd = os.getcwd().replace(os.path.expanduser("~"), "~")
    out(f"{DIM}{cwd} · {status} · Gemma 4 31B · Memory: {memory_count} facts{RESET}")
    out("")


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
                out(f"{PURPLE}◆ Connected to Jarvis.{RESET}")


async def send_message(text):
    global ws_conn, connected, last_response
    if not connected or ws_conn is None:
        out(f"{RED}⚠ Not connected. Is Jarvis running? Try: start{RESET}")
        return

    payload = json.dumps({"type": "chat", "message": text, "source": "cli"})
    await ws_conn.send(payload)

    buffer = ""
    out(f"\n{PURPLE_LT}◆ {RESET}", end="")

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
                out(f"\n{DIM}┌─{label}{bar}┐{RESET}")
                out(f"{DIM}│ ↳ {YELLOW}{tool}{DIM}  {msg.get('description',''):<{width-6}}│{RESET}")
                out(f"{DIM}└{'─' * (width)}┘{RESET}\n")
                continue

            if mtype in ("chunk", "stream"):
                chunk = msg.get("content", msg.get("text", ""))
                buffer += chunk
                sys.stdout.write(f"{WHITE}{chunk}{RESET}")
                sys.stdout.flush()
                continue

            if mtype in ("response", "final", "done"):
                content = msg.get("content", msg.get("message", msg.get("text", "")))
                if content and not buffer:
                    sys.stdout.write(f"{WHITE}{content}{RESET}")
                    sys.stdout.flush()
                    buffer = content
                last_response = buffer
                print()
                print()
                break

            if mtype == "error":
                out(f"\n{RED}✗ {msg.get('message','Unknown error')}{RESET}\n")
                break

    except websockets.exceptions.ConnectionClosed:
        connected = False
        out(f"\n{RED}⚠ Connection lost.{RESET}\n")


def handle_slash(cmd):
    global last_response
    parts = cmd.strip().split(None, 2)
    command = parts[0].lower()

    if command == "/help":
        out(f"\n{PURPLE_LT}Commands:{RESET}")
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
            out(f"  {PURPLE}{c:<22}{RESET}{DIM}{d}{RESET}")
        out("")
        return True

    if command == "/clear":
        print_header()
        print_status()
        return True

    if command == "/exit" or command == "/quit":
        out(f"\n{DIM}Goodbye.{RESET}\n")
        sys.exit(0)

    if command == "/copy":
        if last_response:
            subprocess.run(["pbcopy"], input=last_response.encode())
            out(f"{GREEN}✓ Copied to clipboard.{RESET}")
        else:
            out(f"{DIM}Nothing to copy yet.{RESET}")
        return True

    if command == "/save":
        fname = parts[1] if len(parts) > 1 else f"jarvis_{datetime.now().strftime('%H%M%S')}.txt"
        if last_response:
            with open(fname, "w") as f:
                f.write(last_response)
            out(f"{GREEN}✓ Saved to {fname}{RESET}")
        else:
            out(f"{DIM}Nothing to save yet.{RESET}")
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
                    out(f"{GREEN}✓ Forgot: {key}{RESET}")
                else:
                    out(f"{DIM}Key not found: {key}{RESET}")
            except Exception as e:
                out(f"{RED}✗ {e}{RESET}")
        else:
            try:
                with open(model_path) as f:
                    data = json.load(f)
                out(f"\n{PURPLE_LT}[USER PROFILE]{RESET}")
                for section, val in data.items():
                    if isinstance(val, dict):
                        out(f"\n{PURPLE}{section.upper()}{RESET}")
                        for k, v in val.items():
                            if v:
                                out(f"  {DIM}{k}:{RESET} {WHITE}{v}{RESET}")
                    elif val:
                        out(f"  {DIM}{section}:{RESET} {WHITE}{val}{RESET}")
                out("")
            except FileNotFoundError:
                out(f"{DIM}No user profile yet. Chat with Jarvis to build one.{RESET}")
            except Exception as e:
                out(f"{RED}✗ {e}{RESET}")
        return True

    if command == "/forget":
        episodes_path = os.path.expanduser("~/cowork/jarvis/memory/episodes.json")
        try:
            with open(episodes_path) as f:
                eps = json.load(f)
            eps = eps[:-5] if len(eps) > 5 else []
            with open(episodes_path, "w") as f:
                json.dump(eps, f, indent=2)
            out(f"{GREEN}✓ Last 5 episodes cleared.{RESET}")
        except Exception as e:
            out(f"{RED}✗ {e}{RESET}")
        return True

    if command == "/status":
        out(f"\n{DIM}Checking ports...{RESET}")
        for port, label in [(8080, "E4B (fast)"), (8081, "31B (coding)"), (8001, "Jarvis API"), (8002, "Cantivia Bus")]:
            r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                                 f"http://localhost:{port}/health"], capture_output=True, text=True)
            ok = r.stdout.strip() not in ("", "000")
            symbol = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
            out(f"  {symbol} {label} :{port}")
        out("")
        return True

    if command == "/git":
        msg = parts[1] if len(parts) > 1 else f"checkpoint {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        r = subprocess.run(
            f'cd ~/cowork && git add -A && git commit -m "{msg}"',
            shell=True, capture_output=True, text=True
        )
        out(f"{GREEN if r.returncode == 0 else RED}{r.stdout or r.stderr}{RESET}")
        return True

    if command == "/model":
        out(f"\n  {DIM}Fast (voice):{RESET}  {WHITE}Gemma 4 E4B · port 8080{RESET}")
        out(f"  {DIM}Main:{RESET}         {WHITE}Gemma 4 31B · port 8081{RESET}")
        out(f"  {DIM}STT:{RESET}          {WHITE}Whisper large-v3-turbo Q4{RESET}")
        out(f"  {DIM}TTS:{RESET}          {WHITE}Qwen3-TTS 0.6B{RESET}\n")
        return True

    if command == "/start":
        subprocess.Popen(["bash", "-c", "source ~/.zshrc && start"], shell=False)
        out(f"{DIM}Starting Jarvis system...{RESET}")
        return True

    if command == "/stop":
        if ws_conn:
            asyncio.ensure_future(ws_conn.send(json.dumps({"type": "stop"})))
        out(f"{DIM}Stop signal sent.{RESET}")
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
        out(f"{DIM}→ Routing to Cantivia{RESET}")
        return f"cantivia {text}"
    return text


async def main():
    global connected, memory_count

    print_header()

    ok = await connect()
    if ok:
        out(f"{PURPLE}◆ Connected to Jarvis.{RESET}\n")
    else:
        out(f"{RED}⚠ Not connected. Is Jarvis running? Try: start{RESET}\n")

    try:
        mp = os.path.expanduser("~/cowork/jarvis/memory/user_model.json")
        with open(mp) as f:
            data = json.load(f)
        count = sum(
            len(v) if isinstance(v, dict) else (1 if v else 0)
            for v in data.values()
        )
        memory_count = count
    except Exception:
        memory_count = 0

    print_status()

    asyncio.ensure_future(reconnect_loop())

    session = PromptSession(
        history=InMemoryHistory(),
        style=Style.from_dict({"prompt": "#7c3aed bold"}),
    )

    with patch_stdout():
        while True:
            try:
                user_input = await session.prompt_async(
                    ANSI(f"{PURPLE}>{RESET} ")
                )
            except (EOFError, KeyboardInterrupt):
                out(f"\n{DIM}Goodbye.{RESET}\n")
                break

            text = user_input.strip()
            if not text:
                continue

            if text.startswith("/"):
                handled = handle_slash(text)
                if handled:
                    continue

            routed = maybe_route_cantivia(text)
            await send_message(routed)


if __name__ == "__main__":
    asyncio.run(main())
