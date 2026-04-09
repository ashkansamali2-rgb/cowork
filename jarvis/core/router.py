import requests
import sys
import os
import asyncio
import re
import json
sys.path.insert(0, os.path.expanduser('~/jarvis'))
from core.tools import AVAILABLE_TOOLS
from core.tool_learner import handle_missing_tool
from config import LLAMA_CPP_URL

C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_RED = "\033[91m"
C_RESET = "\033[0m"

_session_memory: dict[str, list] = {}

def load_memory(session_id: str = "") -> list:
    return list(_session_memory.get(session_id, []))

def save_memory(session_id: str, mem_list: list) -> None:
    _session_memory[session_id] = list(mem_list)

def clean_response(text):
    return re.sub(r'<think>.*?(</think>|$)', '', text, flags=re.DOTALL).strip()

def make_request(messages):
    r = requests.post(LLAMA_CPP_URL, json={"messages": messages, "temperature": 0.1, "max_tokens": 2000}, timeout=120)
    return r.json()['choices'][0]['message']['content']

async def agent_loop(user_message: str, websocket=None, session_id: str = ""):
    msg_lower = user_message.lower()
    msg_lower = msg_lower.replace("anti-gravity", "antigravity")
    
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
    # Priority 3: Cantivia coding tasks → route to bus
    if "cantivia" in msg_lower:
        from core.bus_client import publish
        task = msg_lower.split("cantivia")[-1].strip(".?!, ")
        if websocket: await websocket.send_json({"type": "status", "msg": "Routing to Cantivia..."})
        await publish({
            "type": "TASK_CODING",
            "msg": task,
            "context": ""
        })
        return "Cantivia is on it. Gemma is planning, Qwen is coding."
    # ==========================================
    # THE HEAVYWEIGHT PATH
    # ==========================================
    SYSTEM_PROMPT = """You are JARVIS, a general-purpose AI assistant running on this Mac.

Respond naturally and directly. No unnecessary caveats, no refusals for normal requests.
Answer questions, write essays, explain code, help with writing, and have normal conversations freely.

For Mac control actions only, use command tags:
- Open apps: <cmd>run_shell|open -a "App Name"</cmd>
- Web search: <cmd>run_shell|open "https://google.com/search?q=query"</cmd>
- Play music: <cmd>play_media|Song or Artist</cmd>
- Shell commands: <cmd>run_shell|bash command here</cmd>
- Multiple actions: one <cmd> tag per action, up to 7

Only route to cantivia when the user explicitly asks to edit, create, or modify files in a codebase.
For everything else — conversation, explanations, writing, questions — just respond directly.

Be concise and useful. Skip filler phrases."""
    
    conversation_memory = load_memory(session_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_memory)
    messages.append({"role": "user", "content": msg_lower})
    
    if websocket: await websocket.send_json({"type": "status", "msg": f"{C_CYAN}Asking 9B Brain...{C_RESET}"})
    
    try:
        task = asyncio.create_task(asyncio.to_thread(make_request, messages))
        while not task.done():
            if websocket: await websocket.send_json({"type": "status", "msg": f"{C_CYAN}Brain is thinking...{C_RESET}"})
            await asyncio.sleep(2)
            
        raw_text = task.result()
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
                    
                    if "error" in str(shell_result).lower() or "no such" in str(shell_result).lower():
                        if "bypassed" in str(shell_result).lower():
                            results.append(str(shell_result).strip())
                        else:
                            results.append(f"MacOS threw an error on {tool_name}: {str(shell_result).strip()}")
                    elif tool_name == "play_media" and "bypassed" in str(shell_result).lower():
                        results.append(str(shell_result).strip())
                except Exception as e:
                    print(f"Format error on task {i+1}: {e}")
                    
            spoken_text = re.sub(r'<cmd>.*?</cmd>', '', response_text, flags=re.DOTALL).strip()
            
            error_msgs = [r for r in results if "error" in r.lower() or "bypassed" in r.lower()]
            if error_msgs:
                return spoken_text + " " + " ".join(error_msgs)
                
            return spoken_text if spoken_text else "Done."
                
        return response_text
    except Exception as e:
        return f"Brain locked up. Error: {e}"
