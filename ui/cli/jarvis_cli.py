#!/usr/bin/env python3
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
from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text

JARVIS_WS = "ws://127.0.0.1:8001/ws"
console = Console(highlight=False)

CODING_RE = re.compile(
    r'\b(write|create|edit|fix|add|implement|refactor|build|debug|modify)\b'
    r'.{0,50}\b(\.py|\.js|\.ts|\.jsx|\.css|\.html|script|function|class|'
    r'component|module|endpoint|route|model|schema|test)\b',
    re.IGNORECASE
)

class CLIManager:
    def __init__(self):
        self.send_queue = asyncio.Queue()
        self.ws_connected = False
        self.last_status = "Starting..."
        self.agents = {}
        self.last_response = ""
        self.shutdown_event = asyncio.Event()

    def get_toolbar(self):
        cwd = str(Path.cwd()).replace(str(Path.home()), "~")
        time_str = datetime.now().strftime("%H:%M")
        j_dot = "●" if self.ws_connected else "○"
        j_color = "#A855F7" if self.ws_connected else "gray"
        
        status_line = f"   Last: {self.last_status[:60]}" if self.last_status else ""
        return HTML(
            f'<style bg="#1a1a1a"> <style color="{j_color}">JARVIS {j_dot}</style>   '
            f'<style color="#22c55e">bus ●</style>   <style color="#888888">{cwd}</style>   '
            f'{time_str}<style color="#555555">{status_line}</style> </style>'
        )

    def print_welcome(self):
        sys.stdout.write("\033[2J\033[H")
        f = pyfiglet.Figlet(font='slant')
        console.print(f"[bold #A855F7]{f.renderText('JARVIS')}[/]")
        console.print("[dim]v1.0  Gemma 4 31B  ready[/]")
        console.print("[dim]─────────────────────────────────────────────────────────────────[/]\n")

    def print_final(self, msg: str):
        self.last_response = msg
        console.print(f"\n[bold white][JARVIS][/] {msg}")
        console.print("[dim]────────────────────[/]")

    def handle_slash(self, text: str) -> bool:
        cmd = text.split()[0].lower()
        args = text[len(cmd):].strip()
        cwd = Path.cwd()

        if cmd in ("/exit", "/quit"):
            self.shutdown_event.set()
            raise EOFError()
        elif cmd == "/clear":
            self.print_welcome()
        elif cmd == "/help":
            console.print("[dim]Commands: /help, /clear, /exit, /ls, /cat, /open, /mkdir, /rm, /cd, /pwd, /home[/]")
            console.print("[dim]Git: /git status, /git add, /git commit, /git push, /git log[/]")
            console.print("[dim]System: /start, /stop, /status, /logs, /agents, /cantivia, /research, /build, /health, /switchmodel[/]")
            console.print("[dim]Other: /memory, /forget, /skills, /copy, /save, /review[/]")
        elif cmd == "/pwd":
            console.print(f"[dim]{cwd}[/]")
        elif cmd == "/home":
            os.chdir(Path.home())
            console.print(f"[dim]Changed directory to {Path.home()}[/]")
        elif cmd == "/cd":
            if not args: args = str(Path.home())
            p = Path(os.path.expanduser(args)).absolute()
            if p.is_dir():
                os.chdir(p)
                console.print(f"[dim]Changed directory to {p}[/]")
            else:
                console.print(f"[bold red][ERR][/] Directory not found: {p}")
        elif cmd == "/ls":
            try:
                p = Path(os.path.expanduser(args)) if args else cwd
                items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))
                for item in items:
                    color = "blue" if item.is_dir() else "white"
                    console.print(f"[{color}]{item.name}[/]")
            except Exception as e:
                console.print(f"[bold red][ERR][/] {e}")
        elif cmd == "/cat":
            if not args: return True
            try:
                p = Path(os.path.expanduser(args)).absolute()
                ext = p.suffix.lstrip(".") or "txt"
                content = p.read_text()
                console.print(Syntax(content, ext, theme="monokai", padding=1))
            except Exception as e:
                console.print(f"[bold red][ERR][/] {e}")
        elif cmd == "/open":
            if args:
                os.system(f'open "{os.path.expanduser(args)}"')
        elif cmd == "/mkdir":
            Path(os.path.expanduser(args)).mkdir(parents=True, exist_ok=True)
            console.print(f"[dim]Directory created: {args}[/]")
        elif cmd == "/rm":
            p = Path(os.path.expanduser(args)).absolute()
            if p.exists():
                val = input(f"Delete {p}? (y/N): ")
                if val.lower() == "y":
                    if p.is_dir(): shutil.rmtree(p)
                    else: p.unlink()
                    console.print("[dim]Deleted.[/]")
        elif cmd == "/git":
            if args == "add": os.system("git add -A")
            elif args.startswith("commit "): os.system(f'git commit -m "{args[7:]}"')
            elif args == "push": os.system("git push")
            elif args == "status": os.system("git status")
            elif args == "log": os.system("git log -5 --oneline")
        elif cmd == "/cantivia":
            console.print("[dim][Cantivia] Routing to coding pipeline...[/]")
            self.send_queue.put_nowait({"message": f"cantivia {args}", "cwd": str(cwd), "source": "cli"})
        elif cmd == "/start": os.system("source ~/.zshrc && start")
        elif cmd == "/stop": os.system("source ~/.zshrc && stop")
        elif cmd == "/status": os.system("source ~/.zshrc && status")
        elif cmd == "/logs": os.system(f"tail -f /tmp/{args}.log" if args else "ls /tmp/*.log")
        elif cmd == "/build":
            mins = args if args.isdigit() else "60"
            self.send_queue.put_nowait({"message": f"run build session {mins}", "cwd": str(cwd), "source": "cli"})
        elif cmd == "/research":
            self.send_queue.put_nowait({"message": f"research {args}", "cwd": str(cwd), "source": "cli"})
        elif cmd == "/agent":
            self.send_queue.put_nowait({"message": args, "cwd": str(cwd), "source": "cli"})
        elif cmd == "/agents":
            console.print("[dim]Use command station UI for active background agent tracking.[/]")
        elif cmd == "/health": os.system("python3 ~/cowork/jarvis/health_check.py")
        elif cmd == "/switchmodel": os.system("python3 ~/cowork/jarvis/switch_model.py")
        elif cmd == "/copy":
            if HAS_CLIP:
                pyperclip.copy(self.last_response)
                console.print("[dim]Copied to clipboard[/]")
            else:
                console.print("[bold red][ERR] pyperclip not installed.[/]")
        elif cmd == "/save":
            if args:
                p = Path.home() / "Desktop" / f"{args}.txt"
                p.write_text(self.last_response)
                console.print(f"[dim]Saved to {p}[/]")
        else:
            console.print(f"[bold red][ERR][/] Unknown slash command: {cmd}")
        return True

    async def ws_loop(self):
        while not self.shutdown_event.is_set():
            try:
                async with websockets.connect(JARVIS_WS) as ws:
                    self.ws_connected = True
                    # Launch sender and receiver
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
                                
                                if t == "ack":
                                    pass
                                elif t == "status":
                                    # Strip ANSI if necessary implicitly via rich
                                    self.last_status = str(m).strip()
                                    console.print(f"[dim italic][...] {self.last_status}[/]")
                                elif t == "final":
                                    self.print_final(m)
                                elif t == "agent_start":
                                    agent_id = data.get("agent_id", "???")
                                    task = data.get("task", "")
                                    console.print(f"  [bold yellow][Agent-{agent_id}][/] Starting: {task[:60]}")
                                elif t == "agent_update":
                                    agent_id = data.get("agent_id", "???")
                                    step = data.get("step", 0)
                                    action = data.get("action", "")
                                    obs = data.get("observation", "")
                                    console.print(f"  [bold yellow][Agent-{agent_id}][/] Step {step}: {action} -> {obs[:80]}")
                                elif t == "error":
                                    console.print(f"[bold red][ERR][/] {m}")
                            except Exception as e:
                                console.print(f"[bold red]Parse err: {e}[/]")

                    stask = asyncio.create_task(sender())
                    rtask = asyncio.create_task(receiver())
                    done, pending = await asyncio.wait([stask, rtask, asyncio.create_task(self.shutdown_event.wait())], return_when=asyncio.FIRST_COMPLETED)
                    for t in pending: t.cancel()
            except Exception:
                self.ws_connected = False
                if not self.shutdown_event.is_set():
                    await asyncio.sleep(3)


async def main():
    cli = CLIManager()
    cli.print_welcome()
    ws_thread = threading.Thread(target=lambda: asyncio.run(cli.ws_loop()), daemon=True)
    ws_thread.start()

    prompt_style = PTStyle.from_dict({"bottom-toolbar": "bg:#111111 #F5F5DC"})
    session = PromptSession(style=prompt_style)

    with patch_stdout():
        while True:
            try:
                d = str(Path.cwd()).replace(str(Path.home()), "~")
                text = await session.prompt_async(HTML(f'\n<style color="#A855F7"><b>{d}</b></style> > '), bottom_toolbar=cli.get_toolbar)
                text = text.strip()
                if not text: continue
                
                if text.startswith("/"):
                    cli.handle_slash(text)
                    continue

                if CODING_RE.search(text):
                    console.print("[dim][Cantivia] Routing to coding pipeline...[/]")
                    cli.send_queue.put_nowait({"message": f"cantivia {text}", "cwd": str(Path.cwd()), "source": "cli"})
                else:
                    cli.send_queue.put_nowait({"message": text, "cwd": str(Path.cwd()), "source": "cli"})

            except KeyboardInterrupt:
                cli.send_queue.put_nowait({"message": "stop", "cwd": str(Path.cwd()), "source": "cli"})
                console.print("[dim]Sent STOP signal.[/]")
            except EOFError:
                break
            except Exception as e:
                console.print(f"[bold red][ERR][/] CLI Error: {e}")

    cli.shutdown_event.set()

if __name__ == "__main__":
    asyncio.run(main())
