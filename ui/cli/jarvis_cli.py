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
    import subprocess
    from rich.console import Console
    _c = Console(force_terminal=True, force_jupyter=False, highlight=False)
    _c.print("Installing pyfiglet...")
    subprocess.run(["pip3", "install", "pyfiglet", "--break-system-packages"])
    import pyfiglet

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
from rich.panel import Panel

JARVIS_WS = "ws://127.0.0.1:8001/ws"
console = Console(force_terminal=True, force_jupyter=False, highlight=False)

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

def interpolate_color(color1, color2, factor):
    c1 = (int(color1[1:3], 16), int(color1[3:5], 16), int(color1[5:7], 16))
    c2 = (int(color2[1:3], 16), int(color2[3:5], 16), int(color2[5:7], 16))
    r = int(c1[0] + (c2[0] - c1[0]) * factor)
    g = int(c1[1] + (c2[1] - c1[1]) * factor)
    b = int(c1[2] + (c2[2] - c1[2]) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"

def get_gradient_color(progress):
    if progress < 0.5:
        return interpolate_color("#7C3AED", "#9F67F5", progress * 2)
    else:
        return interpolate_color("#9F67F5", "#C084FC", (progress - 0.5) * 2)

class CLIManager:
    def __init__(self):
        self.send_queue = asyncio.Queue()
        self.ws_connected = False
        self.shutdown_event = asyncio.Event()
        self.last_response = ""
        self.receiving_stream = False
        self.spinner_task = None
        self.reconnect_message_shown = False
        
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
        console.clear()
        try:
            f = pyfiglet.Figlet(font='banner3')
        except Exception:
            f = pyfiglet.Figlet(font='block')
            
        lines = f.renderText('JARVIS').splitlines()
        max_len = max((len(line) for line in lines), default=1)
        
        for line in lines:
            colored_line = ""
            for i, char in enumerate(line):
                if char != " ":
                    color = get_gradient_color(i / max_len if max_len > 0 else 0)
                    colored_line += f"[{color}]{char}[/]"
                else:
                    colored_line += " "
            console.print(colored_line)
            
        console.print("\nTips for getting started:", style="dim white")
        console.print("1. Talk to Jarvis naturally or use voice commands.", style="dim white")
        console.print('2. Prefix coding tasks with "cantivia" or just describe the code change.', style="dim white")
        console.print("3. /help for all commands.\n", style="dim white")

    def print_agent_step(self, step: int, action: str, obs: str):
        content = f"[bold white]↳ {action}[/]\n[dim white]{obs.strip()[:100]}[/]"
        console.print(Panel(content, title=f"AgentStep {step}", title_align="left", border_style="dim white", expand=False))

    def handle_slash(self, text: str) -> bool:
        cmd = text.split()[0].lower()
        args = text[len(cmd):].strip()
        cwd = Path.cwd()

        if cmd in ("/exit", "/quit"):
            console.print("[dim white]Goodbye.[/]")
            self.shutdown_event.set()
            os._exit(0)
        elif cmd == "/clear":
            self.print_welcome()
        elif cmd == "/help":
            console.print("[dim white]Commands: /help, /memory, /memory edit, /memory forget [key], /forget, /status, /copy, /save [name], /git [args], /clear, /model, /voice, /agents, /stop, /exit[/]")
        elif cmd == "/memory":
            if not args:
                try:
                    sys.path.insert(0, os.path.expanduser("~/cowork/jarvis"))
                    from core.memory.user_model import UserModel
                    summary = UserModel().get_profile_summary()
                    console.print(f"[dim white]{summary}[/]")
                except Exception as e:
                    console.print(f"[bold red]✗ Could not load memory: {e}[/]")
            elif args == "edit":
                os.system(f"nano {self.user_model_path}")
            elif args.startswith("forget"):
                key = args[6:].strip()
                try:
                    sys.path.insert(0, os.path.expanduser("~/cowork/jarvis"))
                    from core.memory.user_model import UserModel
                    if UserModel().forget(key):
                        console.print(f"[bold #10B981]✦ Forgot {key}.[/]")
                    else:
                        console.print(f"[dim white]Key {key} not found.[/]")
                except Exception as e:
                    console.print(f"[bold red]✗ Error forgetting: {e}[/]")
            else:
                console.print("[dim white]Unknown memory arg. Try: /memory, /memory edit, /memory forget [key][/]")
        elif cmd == "/forget":
            try:
                if self.episodes_path.exists():
                    episodes = json.loads(self.episodes_path.read_text())
                    self.episodes_path.write_text(json.dumps(episodes[:-5], indent=2))
                    console.print("[bold #10B981]✦ Cleared last 5 episodic turns.[/]")
                else:
                    console.print("[dim white]No episodic memory found.[/]")
            except Exception as e:
                console.print(f"[bold red]✗ Error clearing episodes: {e}[/]")
        elif cmd == "/git":
            if args == "add -A" or args == "add":
                os.system("git add -A")
                console.print("[bold #10B981]✦ git add -A[/]")
            elif args.startswith("commit "): 
                os.system(f'git commit -m "{args[7:]}"')
                console.print(f"[bold #10B981]✦ Committed.[/]")
            elif args == "push": 
                os.system("git push")
            else:
                os.system(f"git add -A && git commit -m '{args or 'Auto commit'}'")
                console.print("[bold #10B981]✦ Auto-committed files.[/]")
        elif cmd == "/status":
            os.system("python3 ~/cowork/jarvis/health_check.py")
        elif cmd == "/model":
            console.print("[dim white]Active models: E4B (port 8080) fast/voice, 31B (port 8081) coding/agents[/]")
        elif cmd == "/voice":
            console.print("[dim white]Voice interface toggled. (mocked)[/]")
        elif cmd == "/agents":
            console.print("[dim white]Running Agents: Please see command-station visual UI.[/]")
        elif cmd == "/stop":
            self.send_queue.put_nowait({"message": "stop", "cwd": str(cwd), "source": "cli"})
            console.print("[dim white]Sent STOP signal.[/]")
        elif cmd == "/copy":
            if HAS_CLIP:
                pyperclip.copy(self.last_response)
                console.print("[dim white]Copied to clipboard[/]")
            else:
                console.print("[bold red]✗ pyperclip not installed.[/]")
        elif cmd == "/save":
            if args:
                p = Path.home() / "Desktop" / f"{args}.txt"
                p.write_text(self.last_response)
                console.print(f"[dim white]Saved to {p}[/]")
        else:
            console.print(f"[bold red]✗ Unknown slash command: {cmd}[/]")
        return True

    async def spinner(self):
        chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        idx = 0
        try:
            while True:
                console.print(f"\r[bold #7C3AED]◆[/] [dim white]{chars[idx % len(chars)]} thinking...[/]          ", end="")
                sys.stdout.flush()
                idx += 1
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            console.print("\r                           \r", end="")
            sys.stdout.flush()

    async def ws_loop(self):
        was_connected = False
        while not self.shutdown_event.is_set():
            try:
                async with websockets.connect(JARVIS_WS) as ws:
                    self.ws_connected = True
                    if not was_connected and self.reconnect_message_shown:
                        console.print("[bold #10B981]◆ Connected.[/]")
                    was_connected = True
                    self.reconnect_message_shown = False
                    
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
                        async for raw in ws:
                            try:
                                data = json.loads(raw)
                                t = data.get("type", "")
                                m = data.get("msg", "")
                                
                                if t == "status":
                                    if self.spinner_task:
                                        self.spinner_task.cancel()
                                        self.spinner_task = None
                                    console.print(f"[dim white]◆ {m}[/]")
                                elif t == "final":
                                    if self.spinner_task:
                                        self.spinner_task.cancel()
                                        self.spinner_task = None
                                    self.last_response = m
                                    console.print("[bold #7C3AED]◆ [/]", end="")
                                    console.print(Markdown(m))
                                    console.print()
                                elif t == "agent_start":
                                    console.print(f"[dim yellow]↳ Agent Starting: {data.get('task', '')[:60]}[/]")
                                elif t == "agent_update":
                                    self.print_agent_step(data.get("step", 0), data.get("action", ""), data.get("observation", ""))
                                elif t == "error":
                                    console.print(f"[bold red]✗ {m}[/]")
                            except Exception as e:
                                pass

                    stask = asyncio.create_task(sender())
                    rtask = asyncio.create_task(receiver())
                    done, pending = await asyncio.wait([stask, rtask, asyncio.create_task(self.shutdown_event.wait())], return_when=asyncio.FIRST_COMPLETED)
                    for t in pending: t.cancel()
            except Exception:
                self.ws_connected = False
                was_connected = False
                if not self.shutdown_event.is_set():
                    if not self.reconnect_message_shown:
                        console.print("\n[bold red]⚠ Not connected. Is Jarvis running? Try: /start[/]")
                        self.reconnect_message_shown = True
                    await asyncio.sleep(3)

    def get_toolbar(self):
        cwd = str(Path.cwd()).replace(str(Path.home()), "~")
        status = "connected" if self.ws_connected else "disconnected"
        facts = self.get_memory_facts_count()
        return HTML(
            f'<style bg="#1A1A1A" color="#888888"> {cwd} | {status} | Gemma 4 31B | Memory: {facts} facts </style>'
        )

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
        console.print("[dim white]Goodbye.[/]")
        os._exit(0)

    prompt_style = PTStyle.from_dict({"bottom-toolbar": "bg:#f5f0e8"})
    session = PromptSession(completer=completer, key_bindings=kb, style=prompt_style)

    with patch_stdout():
        while True:
            try:
                text = await session.prompt_async(HTML('\n<style color="#9F67F5">> </style>'), bottom_toolbar=cli.get_toolbar)
                text = text.strip()
                if not text: continue
                
                if text.startswith("/"):
                    cli.handle_slash(text)
                    continue

                if not cli.ws_connected:
                    console.print("[bold red]⚠ Not connected. Is Jarvis running? Try: /start[/]")
                    cli.reconnect_message_shown = True
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
                console.print(f"[bold red]✗ CLI Error: {e}[/]")

if __name__ == "__main__":
    asyncio.run(main())
