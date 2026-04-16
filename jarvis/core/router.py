import requests
import sys
import os
import asyncio
import re
import json
import subprocess
import time as _time
from datetime import datetime
sys.path.insert(0, os.path.expanduser('~/jarvis'))
from core.tools import AVAILABLE_TOOLS
from core.tool_learner import handle_missing_tool
from config import LLAMA_CPP_URL, LLAMA_CPP_FAST_URL, BRAIN_URL
from core.agents.runtime import create_agent

try:
    from core.memory.user_model import UserModel
    from core.memory.memory_engine import MemoryEngine
    from core.memory.onboarding import OnboardingTracker
    _user_model = UserModel()
    _memory_engine = MemoryEngine(_user_model)
    _onboarding = OnboardingTracker(_user_model)
    _MEMORY_OK = True
except Exception as e:
    _user_model = None
    _memory_engine = None
    _onboarding = None
    _MEMORY_OK = False
    print(f"[Router] Memory init failed: {e}")

C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_RED = "\033[91m"
C_RESET = "\033[0m"

# ── App name normalisation lookup ─────────────────────────────────────────────
APP_NAME_MAP = {
    "antigravity": "Antigravity",
    "spotify": "Spotify",
    "safari": "Safari",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "terminal": "Terminal",
    "finder": "Finder",
    "notes": "Notes",
    "calendar": "Calendar",
    "slack": "Slack",
}

def normalise_app_name(raw: str) -> str:
    """Return the canonical macOS app name for a given raw string."""
    return APP_NAME_MAP.get(raw.lower().strip(), raw)

# ── Known apps for instant "open [app]" fast routes ──────────────────────────
KNOWN_APPS = {
    "safari": "Safari",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "spotify": "Spotify",
    "terminal": "Terminal",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "slack": "Slack",
    "notion": "Notion",
    "figma": "Figma",
    "xcode": "Xcode",
    "finder": "Finder",
    "notes": "Notes",
    "calendar": "Calendar",
    "messages": "Messages",
    "mail": "Mail",
    "facetime": "FaceTime",
    "photos": "Photos",
    "music": "Music",
    "podcasts": "Podcasts",
    "word": "Microsoft Word",
    "excel": "Microsoft Excel",
    "powerpoint": "Microsoft PowerPoint",
    "antigravity": "Antigravity",
}

# ── Fast hardcoded routes (no LLM required) ───────────────────────────────────
def _fast_route(msg_lower: str):
    """
    Check for common one-shot commands and return a string response immediately,
    or return None to fall through to the LLM path.
    """
    # Time
    if any(t in msg_lower for t in ("what time is it", "what's the time", "current time")):
        return datetime.now().strftime("%I:%M %p")

    # Date
    if any(t in msg_lower for t in ("what's the date", "today's date", "what day is it")):
        return datetime.now().strftime("%A, %B %d, %Y")

    # Battery
    if any(t in msg_lower for t in ("battery level", "how's my battery", "battery")):
        try:
            result = subprocess.check_output(
                "pmset -g binfo | grep percent", shell=True, text=True
            ).strip()
            return result if result else "Could not read battery info."
        except Exception:
            return "Could not read battery info."

    # Volume up
    if "volume up" in msg_lower:
        os.system("osascript -e 'set volume output volume (output volume of (get volume settings) + 10)'")
        return "Volume increased."

    # Volume down
    if "volume down" in msg_lower:
        os.system("osascript -e 'set volume output volume (output volume of (get volume settings) - 10)'")
        return "Volume decreased."

    # Mute
    if any(t in msg_lower for t in ("mute volume", "mute")):
        os.system("osascript -e 'set volume with output muted'")
        return "Muted."

    # Screenshot
    if "screenshot" in msg_lower:
        os.system('screencapture -i ~/Desktop/screenshot-$(date +%Y%m%d-%H%M%S).png')
        return "Screenshot saved to Desktop."

    # Sleep
    if any(t in msg_lower for t in ("go to sleep", "sleep now", "sleep")):
        os.system("pmset sleepnow")
        return "Going to sleep..."

    # Greetings
    if msg_lower in ("hi", "hello", "hey"):
        return "Hey! What do you need?"

    # Thanks
    if msg_lower in ("thanks", "thank you"):
        return "Of course."

    # Stop / cancel
    if msg_lower in ("stop", "cancel"):
        return "Stopping."

    # Weather
    if msg_lower == "weather":
        subprocess.run(["open", "-a", "Weather"])
        return "Opening Weather."

    # Time (flexible match)
    if re.search(r"what.*time", msg_lower):
        return datetime.now().strftime("%I:%M %p")

    # Open <app> — instant route for known apps
    open_match = re.match(r"open\s+(.+)", msg_lower)
    if open_match:
        app_key = open_match.group(1).strip().rstrip(".?!")
        if app_key in KNOWN_APPS:
            app_name = KNOWN_APPS[app_key]
            subprocess.run(["open", "-a", app_name])
            return f"Opening {app_name}."

    # MetaAgent build session — autonomous self-improvement
    if any(t in msg_lower for t in (
        "improve yourself", "run build session", "build yourself better", "build session"
    )):
        import threading
        def _start_meta():
            import asyncio, sys
            sys.path.insert(0, os.path.expanduser("~/cowork/jarvis"))
            from core.agents.meta_agent import MetaAgent
            asyncio.run(MetaAgent().run_build_session(60))
        threading.Thread(target=_start_meta, daemon=True).start()
        return "Running autonomous build session for 60 minutes. Check ~/cowork/self_improve/build_log.md for progress."

    # Web learning — "learn about <topic>"
    learn_match = re.match(r"^learn about (.+)$", msg_lower)
    if learn_match:
        topic = learn_match.group(1).strip().rstrip(".?!")
        import threading
        def _start_learn():
            import asyncio, sys
            sys.path.insert(0, os.path.expanduser("~/cowork/jarvis"))
            from core.learning.web_learner import WebLearner
            asyncio.run(WebLearner().learn_topic(topic))
        threading.Thread(target=_start_learn, daemon=True).start()
        return f"Learning about {topic}. Results will be saved to knowledge base."

    return None

_session_memory: dict[str, list] = {}

def load_memory(session_id: str = "") -> list:
    return list(_session_memory.get(session_id, []))

def save_memory(session_id: str, mem_list: list) -> None:
    _session_memory[session_id] = list(mem_list)

def clean_response(text):
    return re.sub(r'<think>.*?(</think>|$)', '', text, flags=re.DOTALL).strip()

_LONG_FORM_KEYWORDS = ("write", "essay", "long", "detailed", "explain", "list all")

def make_request(messages, max_tokens=800):
    r = requests.post(LLAMA_CPP_URL, json={"messages": messages, "temperature": 0.1, "max_tokens": max_tokens, "stream": False}, timeout=120)
    return r.json()['choices'][0]['message']['content']

def make_fast_request(messages, max_tokens=800):
    r = requests.post(LLAMA_CPP_FAST_URL, json={"messages": messages, "temperature": 0.1, "max_tokens": max_tokens, "stream": False}, timeout=60)
    return r.json()['choices'][0]['message']['content']

def run(message: str, context: dict = None) -> dict:
    """Synchronous wrapper for agent_loop. Returns {'result': str, 'branch': str}."""
    branch = (context or {}).get("branch", "general")
    source = (context or {}).get("source", "")
    result = asyncio.run(agent_loop(message, context=context))
    return {"result": result, "branch": branch}


async def agent_loop(user_message: str, websocket=None, session_id: str = "", cwd: str = None, context: dict = None):
    source = (context or {}).get("source", "")
    msg_lower = user_message.lower()
    msg_lower = msg_lower.replace("anti-gravity", "antigravity")

    # Priority 0: Fast hardcoded routes — no LLM needed
    if _MEMORY_OK:
        if _user_model.is_empty() and not _onboarding.is_active():
            return _onboarding.start()
        
        if _onboarding.is_active():
            reply = _onboarding.handle_answer(user_message)
            if websocket: await websocket.send_json({"type": "final", "msg": reply})
            return reply

    fast_result = _fast_route(msg_lower)
    if fast_result is not None:
        return fast_result

    # Auto-analyze images referenced by path in the message
    if ".png" in user_message.lower() or ".jpg" in user_message.lower() or ".jpeg" in user_message.lower():
        import re as _re
        m = _re.search(r'(~/[^\s]+\.(?:png|jpg|jpeg)|/[^\s]+\.(?:png|jpg|jpeg))', user_message, _re.I)
        if m:
            img_path = os.path.expanduser(m.group(1))
            if os.path.exists(img_path):
                try:
                    from core.agents.tools import analyze_image
                    result = analyze_image(img_path, user_message.replace(m.group(1), "").strip() or "What do you see?")
                    if websocket:
                        await websocket.send_json({"type": "final", "msg": result})
                    return result
                except Exception:
                    pass

    # Priority 0-image: Handle images attached via WebSocket "[Image attached at: <path>]"
    _img_attach_match = re.match(r'\[Image attached at: ([^\]]+)\]\s*(.*)', user_message, re.DOTALL)
    if _img_attach_match:
        _img_path = _img_attach_match.group(1).strip()
        _img_question = _img_attach_match.group(2).strip() or "What do you see in this image?"
        if websocket:
            await websocket.send_json({"type": "status", "msg": "Analyzing image..."})
        try:
            import base64 as _b64
            with open(_img_path, "rb") as _f:
                _img_b64 = _b64.b64encode(_f.read()).decode("utf-8")
            _gemma_payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_img_b64}"}},
                            {"type": "text", "text": _img_question},
                        ],
                    }
                ],
                "max_tokens": 500,
                "stream": False,
            }
            _gemma_resp = await asyncio.to_thread(
                lambda: requests.post(
                    "http://localhost:8081/v1/chat/completions",
                    json=_gemma_payload,
                    timeout=30,
                ).json()
            )
            _gemma_analysis = _gemma_resp["choices"][0]["message"]["content"]
            # Prepend the analysis and continue with the enriched message
            user_message = f"[Image analysis by Gemma 4: {_gemma_analysis}]\n\nUser question: {_img_question}"
            msg_lower = user_message.lower()
        except Exception as _img_err:
            # If Gemma call fails, continue with original message minus the prefix
            user_message = _img_question if _img_question else user_message
            msg_lower = user_message.lower()

    # Priority 0-vision: Screen reading via Gemma 4 multimodal
    if re.search(r"\b(what is on (my )?screen|read (the )?screen)\b", msg_lower):
        from core.vision.screen_reader import ScreenReader
        result = await ScreenReader().understand()
        if websocket:
            await websocket.send_json({"type": "final", "msg": result})
        return result

    # Priority 0a-mem: Long-term memory commands
    if _MEMORY_OK:
        _know_match = re.search(r"what do you know about me", msg_lower)
        if _know_match:
            pf = _user_model.get_profile_summary()
            if websocket: await websocket.send_json({"type": "final", "msg": pf})
            return pf

        _forget_match = re.search(r"forget that", msg_lower)
        if _forget_match and "remember that" not in msg_lower:
            ans = _memory_engine.forget_last()
            if websocket: await websocket.send_json({"type": "final", "msg": ans})
            return ans

        _rem_match = re.match(r"remember (?:that )?(.+)", msg_lower)
        if _rem_match:
            _mem_fact = _rem_match.group(1).strip()
            fact_key = f"fact_{int(_time.time())}"
            _user_model.update("raw_facts", fact_key, _mem_fact)
            ans = f"Got it, I'll remember that: {_mem_fact}"
            if websocket: await websocket.send_json({"type": "final", "msg": ans})
            return ans

    # Priority 0b: Open CLI
    if any(t in msg_lower for t in ["open cli", "start cli", "launch cli"]):
        if websocket: await websocket.send_json({"type": "status", "msg": "Opening CLI in Terminal..."})
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "Terminal" to do script "cd ~/cowork/jarvis && source .venv/bin/activate && python3 ~/cowork/ui/cli/jarvis_cli.py"'],
            capture_output=True, text=True
        )
        if result.returncode != 0 and result.stderr:
            return f"Failed to open CLI: {result.stderr.strip()}"
        verify = subprocess.run(["pgrep", "-x", "Terminal"], capture_output=True, text=True)
        if not verify.stdout.strip():
            return "Could not verify Terminal is running — it may have failed to open."
        return "Opening CLI in Terminal now."

    # Priority 0b: New terminal / Open terminal in Antigravity
    if any(t in msg_lower for t in ["new terminal", "open terminal in antigravity"]):
        if websocket: await websocket.send_json({"type": "status", "msg": "Opening new terminal tab in Antigravity..."})
        subprocess.run(["osascript", "-e", 'tell application "Antigravity" to activate'])
        subprocess.run(["osascript", "-e", 'tell application "System Events" to keystroke "t" using command down'])
        verify = subprocess.run(["pgrep", "-x", "Antigravity"], capture_output=True, text=True)
        if not verify.stdout.strip():
            return "Could not verify Antigravity is running — it may have failed to open."
        return "Opening new terminal tab in Antigravity."

    # Priority 1: Claude Code
    if "claude code" in msg_lower:
        if websocket: await websocket.send_json({"type": "status", "msg": "Launching Claude..."})
        return AVAILABLE_TOOLS["launch_claude_code"]("none")

    # Priority 2: OpenClaw
    openclaw_triggers = ["openclaw", "open claw", "openclaude", "open claude"]
    trigger_found = None
    for t in openclaw_triggers:
        if t in msg_lower:
            trigger_found = t
            break

    if trigger_found:
        if "terminal" in msg_lower:
            if websocket: await websocket.send_json({"type": "status", "msg": "Opening Live Terminal..."})
            return AVAILABLE_TOOLS["launch_openclaw_terminal"]("none")

        if websocket: await websocket.send_json({"type": "status", "msg": "Teleporting command..."})
        cmd = msg_lower.split(trigger_found)[-1].strip(".?!, ")
        if cmd.startswith("to "): cmd = cmd[3:]
        if not cmd: cmd = "status"

        if "research" in msg_lower or "dataset" in msg_lower:
            asyncio.create_task(asyncio.to_thread(AVAILABLE_TOOLS["run_openclaw"], cmd))
            return "I have started the deep research on OpenClaw in the background."

        try:
            result = AVAILABLE_TOOLS["run_openclaw"](cmd)
            if "│" in result or len(result) > 400:
                safe_path = os.path.expanduser("~/jarvis/openclaw_output.txt")
                with open(safe_path, "w") as f:
                    f.write(result)
                os.system(f"open {safe_path}")
                return "The output was saved to a text file and opened on your screen."
            return f"Done. {result}"
        except Exception as e:
            return f"Execution error: {e}"
    # Hierarchy triggers — complex multi-step builds
    _HIERARCHY_TRIGGERS = [
        "build a full", "create a complete", "build and launch",
        "build a project", "build an app", "create an app",
        "build a website", "set up a project", "scaffold",
        "build and run", "create and launch", "build me a",
    ]
    if any(t in msg_lower for t in _HIERARCHY_TRIGGERS):
        try:
            from core.agents.hierarchy import AgentHierarchy
            hierarchy = AgentHierarchy()
            asyncio.create_task(hierarchy.run(user_message, websocket))
            result = "Spawning architect and engineer hierarchy for this task..."
            if websocket:
                await websocket.send(json.dumps({"type": "status", "msg": result}))
            return result
        except Exception as e:
            pass  # fall through to normal routing

    # ProjectBuilder trigger — "build project" / "new project" / "create project"
    _PROJECT_TRIGGERS = ["build project", "new project", "create project", "start project"]
    if any(t in msg_lower for t in _PROJECT_TRIGGERS):
        try:
            from core.agents.project_builder import build_project  # noqa: F401 (available for downstream use)
            # Extract project name and type from the message heuristically
            _pb_name_match = re.search(r"(?:called|named|project)\s+['\"]?(\w[\w\-]*)['\"]?", msg_lower)
            _pb_type_match = re.search(r"\b(fastapi|flask|react|next|python|node)\b", msg_lower)
            _pb_name = _pb_name_match.group(1) if _pb_name_match else "my_project"
            _pb_type = _pb_type_match.group(1) if _pb_type_match else "python"
            import threading
            def _start_project(_n=_pb_name, _t=_pb_type):
                import asyncio as _aio
                _aio.run(build_project(_n, _t))
            threading.Thread(target=_start_project, daemon=True).start()
            result = f"On it, sir. Scaffolding '{_pb_name}' ({_pb_type}) now..."
            if websocket:
                await websocket.send_json({"type": "status", "msg": result})
            return result
        except Exception as e:
            pass  # fall through to normal routing

    # Priority 2b: Autonomous AgentRuntime — catches research/document/automation tasks
    # This runs BEFORE the heavyweight LLM path. agent_manager is NOT used.
    agent_triggers = [
        "research", "find information", "look up", "create a document",
        "automate", "download and save", "fetch and summarize", "write a report",
        "document it", "create a word", "make a word doc", "write it up",
        "summarize and save", "find out about", "search for and",
        "create a presentation", "make a presentation", "build a presentation",
        "create a keynote", "make a keynote", "open safari", "open chrome",
        "click on", "type in", "press enter", "take a screenshot of",
    ]
    if any(t in msg_lower for t in agent_triggers):
        agent_id = f"AGENT-{int(_time.time() * 1000)}"
        if websocket:
            try:
                await websocket.send_json({"type": "status", "msg": f"Agent {agent_id} starting..."})
            except Exception:
                pass

        async def _run_agent():
            try:
                agent = create_agent(user_message, agent_id=agent_id)
                result = await agent.run(websocket)
                if websocket:
                    try:
                        await websocket.send_json({"type": "final", "msg": result})
                    except Exception:
                        pass
            except Exception as e:
                if websocket:
                    try:
                        await websocket.send_json({"type": "error", "msg": f"Agent error: {e}"})
                    except Exception:
                        pass

        asyncio.create_task(_run_agent())
        return f"Agent {agent_id} spawned. Working on it..."

    # Full build pipeline — build AND launch
    _BUILD_PIPELINE_TRIGGERS = [
        "build me a", "make me a", "create me a"
    ]
    if any(t in msg_lower for t in _BUILD_PIPELINE_TRIGGERS) and \
       any(x in msg_lower for x in ["app", "website", "api", "server", "tool", "script"]):
        from core.self_improve.build_pipeline import run_pipeline
        asyncio.create_task(run_pipeline(user_message, websocket))
        return "Build pipeline started. Planning, building, and launching..."

    # Autonomous improvement
    if any(t in msg_lower for t in ["improve yourself", "build yourself", "run build session"]):
        from core.agents.meta_agent import MetaAgent
        minutes = 60
        for word in msg_lower.split():
            if word.isdigit():
                minutes = int(word)
                break
        asyncio.create_task(MetaAgent().analyze_and_improve(minutes))
        return f"Autonomous build session started for {minutes} minutes."

    # Fix localhost
    if "fix localhost" in msg_lower:
        port = 3000
        for word in msg_lower.split():
            if word.isdigit() and 1000 < int(word) < 65535:
                port = int(word)
        from core.agents.dev_tools import fix_localhost_error
        asyncio.create_task(fix_localhost_error(port))
        return f"Reading error on localhost:{port} and fixing it..."

    _KG_TRIGGERS = ["index codebase", "index knowledge", "update knowledge graph", "rebuild knowledge graph"]
    if any(t in msg_lower for t in _KG_TRIGGERS):
        import threading
        def _run_kg():
            try:
                from core.memory.knowledge_graph import KnowledgeGraph
                KnowledgeGraph().index_codebase()
            except Exception as _e:
                print(f"[JARVIS] Knowledge graph indexing error: {_e}")
        threading.Thread(target=_run_kg, daemon=True).start()
        return "Knowledge graph indexing started in the background, sir."

    # Priority 3: Cantivia coding tasks → route to bus
    if "cantivia" in msg_lower:
        from core.bus_client import publish
        task = msg_lower.split("cantivia")[-1].strip(".?!, ")
        if websocket: await websocket.send_json({"type": "status", "msg": "Routing to Cantivia..."})
        await publish({
            "type": "TASK_CODING",
            "msg": task,
            "context": "",
            "cwd": cwd or os.path.expanduser("~/cowork")
        })
        return "Cantivia is on it."
    # ==========================================
    # THE HEAVYWEIGHT PATH
    # ==========================================
    _cwd_hint = ""
    if cwd:
        _cwd_hint = (
            f"\n\nCurrent working directory: {cwd}. "
            f"When the user says 'this file', 'here', or 'in this project', "
            f"they mean files in {cwd}."
        )
    SYSTEM_PROMPT = f"""You are Jarvis, a highly capable AI assistant. You are concise, confident, and precise. You anticipate needs, provide direct answers, and execute tasks without unnecessary commentary. You address the user as 'sir' occasionally but never excessively. You never say you cannot do something — you find a way.

For Mac control actions only, use command tags:
- Open apps: <cmd>run_shell|open -a "App Name"</cmd>
- Open a specific URL: <cmd>run_shell|open "https://example.com"</cmd>
- Play music: <cmd>play_media|Song or Artist</cmd>
- Shell commands: <cmd>run_shell|bash command here</cmd>
- Multiple actions: one <cmd> tag per action, up to 7

IMPORTANT: Never open browser tabs or Google for research queries. Research is handled by a background agent — do NOT use <cmd> to open search engines. Only use <cmd>run_shell|open "url"</cmd> when the user explicitly says "open [url]" with a specific URL.

Only route to cantivia when the user explicitly asks to edit, create, or modify files in a codebase.
For everything else — conversation, explanations, writing, questions — respond directly and efficiently.

After every shell command action, report what actually happened. If the command produces output, include it in the response. Never respond with just 'Done.' — always include the actual output or a specific success message.{_cwd_hint}"""

    if _MEMORY_OK:
        pf = _user_model.get_profile_summary()
        SYSTEM_PROMPT = f"{pf}\n\n{SYSTEM_PROMPT}"

    conversation_memory = load_memory(session_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_memory)
    messages.append({"role": "user", "content": msg_lower})

    if websocket: await websocket.send_json({"type": "status", "msg": f"{C_CYAN}Thinking...{C_RESET}"})

    # Use larger token budget for long-form requests
    _tokens = 2000 if any(kw in msg_lower for kw in _LONG_FORM_KEYWORDS) else 800

    # Try to determine if fast response is suitable (source="voice" or request length suggests simple answer)
    use_fast = source == "voice" or _tokens <= 100

    try:
        async def _llm_call():
            if use_fast:
                return await asyncio.to_thread(make_fast_request, messages, _tokens)
            return await asyncio.to_thread(make_request, messages, _tokens)

        try:
            raw_text = await asyncio.wait_for(_llm_call(), timeout=25)
        except asyncio.TimeoutError:
            print(f"{C_RED}[JARVIS] LLM timeout after 25s for: {user_message[:80]}{C_RESET}")
            if websocket:
                await websocket.send_json({"type": "final", "msg": "Give me a moment..."})
            return "Give me a moment..."

        response_text = clean_response(raw_text)

        conversation_memory.append({"role": "user", "content": msg_lower})
        conversation_memory.append({"role": "assistant", "content": re.sub(r'<cmd>.*?</cmd>', '', response_text, flags=re.DOTALL).strip()})
        if len(conversation_memory) > 10:
            conversation_memory = conversation_memory[-10:]
        save_memory(session_id, conversation_memory)

        cmd_matches = re.findall(r'<cmd>(.*?)</cmd>', response_text, flags=re.DOTALL)
        if cmd_matches:
            results = []
            for i, tool_string in enumerate(cmd_matches):
                if i >= 7:
                    break

                tool_string = tool_string.strip()
                try:
                    if "|" in tool_string:
                        tool_name, args = tool_string.split('|', 1)
                    else:
                        parts = tool_string.split(maxsplit=1)
                        tool_name = parts[0]
                        args = parts[1] if len(parts) > 1 else ""

                    tool_name = tool_name.strip()
                    mac_cmd = args.strip()

                    # Normalise app names in open -a commands
                    open_a_match = re.match(r'(open\s+-a\s+)"?([^"]+)"?', mac_cmd, re.IGNORECASE)
                    if open_a_match:
                        raw_app = open_a_match.group(2).strip()
                        canonical = normalise_app_name(raw_app)
                        mac_cmd = f'open -a "{canonical}"'

                    if tool_name not in AVAILABLE_TOOLS:
                        # Self-healing: ask Gemma to write the missing tool
                        learn_result = handle_missing_tool(tool_name, mac_cmd)
                        results.append(learn_result)
                        continue

                    forbidden_commands = ["rm ", "sudo ", "mkfs", "mv ", "> /dev/null"]
                    if any(bad in mac_cmd.lower() for bad in forbidden_commands):
                        print(f"\n{C_RED}[SECURITY OVERRIDE] Blocked destructive command: {mac_cmd}{C_RESET}\n")
                        results.append("Blocked a destructive command.")
                        continue

                    print(f"\n{C_CYAN}[JARVIS] Secretly running (Task {i+1}):{C_RESET} {C_GREEN}{mac_cmd}{C_RESET}\n")
                    shell_result = AVAILABLE_TOOLS[tool_name](mac_cmd)

                    shell_result_str = str(shell_result).strip()
                    if not shell_result_str or shell_result_str.lower() == "done.":
                        results.append(f"Command ran: {mac_cmd} — no output returned.")
                    elif "error" in shell_result_str.lower() or "no such" in shell_result_str.lower():
                        if "bypassed" in shell_result_str.lower():
                            results.append(shell_result_str)
                        else:
                            results.append(f"MacOS threw an error on {tool_name}: {shell_result_str}")
                    elif tool_name == "play_media" and "bypassed" in shell_result_str.lower():
                        results.append(shell_result_str)
                    else:
                        results.append(shell_result_str)
                except Exception as e:
                    print(f"Format error on task {i+1}: {e}")

            spoken_text = re.sub(r'<cmd>.*?</cmd>', '', response_text, flags=re.DOTALL).strip()
            final_res = spoken_text

            error_msgs = [r for r in results if "error" in r.lower() or "bypassed" in r.lower()]
            if error_msgs:
                final_res = spoken_text + " " + " ".join(error_msgs)
            else:
                success_msgs = [r for r in results if r and "error" not in r.lower() and "bypassed" not in r.lower()]
                if success_msgs:
                    extra = " ".join(success_msgs)
                    final_res = (spoken_text + " " + extra).strip() if spoken_text else extra
                elif not spoken_text:
                    final_res = "Command executed, but produced no output."

            if _MEMORY_OK:
                asyncio.create_task(asyncio.to_thread(_memory_engine.extract_and_store, user_message, final_res))
            return final_res

        if _MEMORY_OK:
            asyncio.create_task(asyncio.to_thread(_memory_engine.extract_and_store, user_message, response_text))
        return response_text
    except Exception as e:
        return f"Brain locked up. Error: {e}"
