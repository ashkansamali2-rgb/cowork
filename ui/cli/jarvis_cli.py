#!/usr/bin/env python3
import asyncio
import json
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path

try:
    import pyperclip
    HAS_CLIP = True
except ImportError:
    HAS_CLIP = False

try:
    import pyfiglet
except ImportError:
    print("Please install pyfiglet: pip install pyfiglet")
    sys.exit(1)

import websockets
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.key_binding import KeyBindings

from rich.console import Console
from rich.syntax import Syntax
from rich.markdown import Markdown

JARVIS_WS = "ws://127.0.0.1:8001/ws"
console = Console(highlight=False)

CODING_RE = re.compile(
    r'\b(write|create|edit|fix|add|implement|refactor|build|debug|modify)\b'
    r'.{0,50}\b(\.py|\.js|\.ts|\.jsx|\.css|\.html|script|function|class|'
    r'component|module|endpoint|route|model|schema|test)\b',
    re.IGNORECASE
)

SLASH_COMMANDS = [
    "/help", "/memory", "/status", "/copy", "/save", "/git", 
    "/clear", "/model", "/voice", "/agents", "/stop", "/exit", "/quit", "/forget"
]
completer = WordCompleter(SLASH_COMMANDS, ignore_case=True)

class CLIManager:
    def __init__(self):
        self.send_queue = asyncio.Queue()
        self.ws_connected = False
        self.shutdown_event = asyncio.Event()
        self.last_response = ""
        self.receiving_stream = False
        self.spinner_task = None
        
        self.user_model_path = Path(os.path.expanduser("~/cowork/jarvis/memory/user_model.json"))
        self.episodes_path = Path(os.path.expanduser("~/cowork/jarvis/memory/episodes.json"))

    def get_memory_facts_count(self):
        try:
            if self.user_model_path.exists():
                data = json.loads(self.user_model_path.read_text())
                c = 0
                for v in data.values():
                    if isinstance(v, dict):
                        c += len(v.keys())
                    elif isinstance(v, list):
                        c += len(v)
                    elif v:
                        c += 1
                return c
        except Exception:
            pass
        return 0

    def print_welcome(self):
        sys.stdout.write("\033[2J\033[H")
        f = pyfiglet.Figlet(font='block')
        console.print(f"[bold #7C3AED]{f.renderText('JARVIS')}[/]")
        count = self.get_memory_facts_count()
        console.print(f"[#F5F0E8]Connected to jarvis://localhost:8001 | Model: Gemma 4 31B | Memory: {count} facts[/]")
        console.print("[dim #7C3AED]─────────────────────────────────────────────────────────────────[/]\n")

    def print_agent_step(self, step: int, action: str, obs: str):
        console.print(f"[dim yellow]  ↳ step {step}:[/] [#F5F0E8]{action} -> {obs[:80]}[/]")

    def handle_slash(self, text: str) -> bool:
        cmd = text.split()[0].lower()
        args = text[len(cmd):].strip()
        cwd = Path.cwd()

        if cmd in ("/exit", "/quit"):
            console.print("[#F5F0E8]Goodbye.[/]")
            self.shutdown_event.set()
            os._exit(0)
        elif cmd == "/clear":
            self.print_welcome()
        elif cmd == "/help":
            console.print("[dim #F5F0E8]Commands: /help, /memory, /memory edit, /memory forget [key], /forget, /status, /copy, /save [name], /git [args], /clear, /model, /voice, /agents, /stop, /exit[/]")
        elif cmd == "/memory":
            if not args:
                try:
                    sys.path.insert(0, os.path.expanduser("~/cowork/jarvis"))
                    from core.memory.user_model import UserModel
                    summary = UserModel().get_profile_summary()
                    console.print(f"[#F5F0E8]{summary}[/]")
                except Exception as e:
                    console.print(f"[bold red]  ✗[/] Could not load memory: {e}")
            elif args == "edit":
                os.system(f"nano {self.user_model_path}")
            elif args.startswith("forget"):
                key = args[6:].strip()
                try:
                    sys.path.insert(0, os.path.expanduser("~/cowork/jarvis"))
                    from core.memory.user_model import UserModel
                    if UserModel().forget(key):
                        console.print(f"[bold green]  ✓[/] Forgot {key}.")
                    else:
                        console.print(f"[dim #F5F0E8]Key {key} not found.[/]")
                except Exception as e:
                    console.print(f"[bold red]  ✗[/] Error forgetting: {e}")
            else:
                console.print("[dim #F5F0E8]Unknown memory arg. Try: /memory, /memory edit, /memory forget [key][/]")
        elif cmd == "/forget":
            try:
                if self.episodes_path.exists():
                    episodes = json.loads(self.episodes_path.read_text())
                    self.episodes_path.write_text(json.dumps(episodes[:-5], indent=2))
                    console.print("[bold green]  ✓[/] Cleared last 5 episodic turns.")
                else:
                    console.print("[dim #F5F0E8]No episodic memory found.[/]")
            except Exception as e:
                console.print(f"[bold red]  ✗[/] Error clearing episodes: {e}")
        elif cmd == "/git":
            if args == "add -A" or args == "add":
                os.system("git add -A")
                console.print("[bold green]  ✓[/] git add -A")
            elif args.startswith("commit "): 
                os.system(f'git commit -m "{args[7:]}"')
                console.print(f"[bold green]  ✓[/] Committed.")
            elif args == "push": 
                os.system("git push")
            else:
                os.system(f"git add -A && git commit -m '{args or 'Auto commit'}'")
                console.print("[bold green]  ✓[/] Auto-committed files.")
        elif cmd == "/status":
            os.system("python3 ~/cowork/jarvis/health_check.py")
        elif cmd == "/model":
            console.print("[#F5F0E8]Active models: E4B (port 8080) fast/voice, 31B (port 8081) coding/agents[/]")
        elif cmd == "/voice":
            console.print("[#F5F0E8]Voice interface toggled. (mocked)[/]")
        elif cmd == "/agents":
            console.print("[#F5F0E8]Running Agents: Please see command-station visual UI.[/]")
        elif cmd == "/stop":
            self.send_queue.put_nowait({"message": "stop", "cwd": str(cwd), "source": "cli"})
            console.print("[dim #F5F0E8]Sent STOP signal.[/]")
        elif cmd == "/copy":
            if HAS_CLIP:
                pyperclip.copy(self.last_response)
                console.print("[dim #F5F0E8]Copied to clipboard[/]")
            else:
                console.print("[bold red]  ✗[/] pyperclip not installed.")
        elif cmd == "/save":
            if args:
                p = Path.home() / "Desktop" / f"{args}.txt"
                p.write_text(self.last_response)
                console.print(f"[dim #F5F0E8]Saved to {p}[/]")
        else:
            console.print(f"[bold red]  ✗[/] Unknown slash command: {cmd}")
        return True

    async def spinner(self):
        chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        sys.stdout.write(f"\n[dim #7C3AED]─── Jarvis ───[/]\n")
        idx = 0
        try:
            while True:
                sys.stdout.write(f"\r\033[K\033[38;2;124;58;237m{chars[idx % len(chars)]}\033[0m thinking...")
                sys.stdout.flush()
                idx += 1
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

    async def ws_loop(self):
        while not self.shutdown_event.is_set():
            try:
                async with websockets.connect(JARVIS_WS) as ws:
                    self.ws_connected = True
                    async def sender():
                        while not self.shutdown_event.is_set():
                            try:
                                msg = await asyncio.wait_for(self.send_queue.get(), timeout=1.0)
                                await ws.send(json.dumps(msg))
                            except asyncio.TimeoutError:
                                continue
                            except Exception:
                                break

                    async def receiver():
                        buffer = ""
                        async for raw in ws:
                            try:
                                data = json.loads(raw)
                                t = data.get("type", "")
                                m = data.get("msg", "")
                                
                                if t == "status":
                                    if self.spinner_task:
                                        self.spinner_task.cancel()
                                        self.spinner_task = None
                                    console.print(f"[dim #F5F0E8]{m}[/]")
                                elif t == "final":
                                    if self.spinner_task:
                                        self.spinner_task.cancel()
                                        self.spinner_task = None
                                    self.last_response = m
                                    # Output markdown correctly
                                    console.print(Markdown(m))
                                    print()
                                elif t == "agent_start":
                                    console.print(f"[dim yellow]  ↳ Agent Starting: {data.get('task', '')[:60]}[/]")
                                elif t == "agent_update":
                                    self.print_agent_step(data.get("step", 0), data.get("action", ""), data.get("observation", ""))
                                elif t == "error":
                                    console.print(f"[bold red]  ✗[/] {m}")
                            except Exception as e:
                                pass

                    stask = asyncio.create_task(sender())
                    rtask = asyncio.create_task(receiver())
                    done, pending = await asyncio.wait([stask, rtask, asyncio.create_task(self.shutdown_event.wait())], return_when=asyncio.FIRST_COMPLETED)
                    for t in pending: t.cancel()
            except Exception:
                self.ws_connected = False
                if not self.shutdown_event.is_set():
                    sys.stdout.write("\r\033[K\033[31m⚠ Not connected. Is Jarvis running? Try: start\033[0m\n")
                    await asyncio.sleep(3)


async def main():
    cli = CLIManager()
    cli.print_welcome()
    ws_thread = threading.Thread(target=lambda: asyncio.run(cli.ws_loop()), daemon=True)
    ws_thread.start()

    kb = KeyBindings()
    
    @kb.add('c-c')
    def _(event):
        cli.send_queue.put_nowait({"message": "stop", "cwd": str(Path.cwd()), "source": "cli"})
        event.app.exit(result="")

    @kb.add('c-d')
    def _(event):
        console.print("[#F5F0E8]Goodbye.[/]")
        os._exit(0)

    prompt_style = PTStyle.from_dict({"bottom-toolbar": "bg:#111111 #F5F0E8"})
    session = PromptSession(completer=completer, key_bindings=kb, style=prompt_style)

    with patch_stdout():
        while True:
            try:
                if not cli.ws_connected:
                    await asyncio.sleep(1)
                    
                text = await session.prompt_async(HTML('\n<style color="#7C3AED"><b> jarvis > </b></style>'))
                text = text.strip()
                if not text: continue
                
                if text.startswith("/"):
                    cli.handle_slash(text)
                    continue

                if CODING_RE.search(text):
                    console.print("[dim #7C3AED]→ Routing to Cantivia[/]")
                    cli.send_queue.put_nowait({"message": f"cantivia {text}", "cwd": str(Path.cwd()), "source": "cli"})
                else:
                    cli.send_queue.put_nowait({"message": text, "cwd": str(Path.cwd()), "source": "cli"})
                
                cli.spinner_task = asyncio.create_task(cli.spinner())

            except EOFError:
                break
            except KeyboardInterrupt:
                pass
            except Exception as e:
                console.print(f"[bold red]  ✗[/] CLI Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
