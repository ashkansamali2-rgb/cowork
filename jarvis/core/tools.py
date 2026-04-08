import subprocess
import os
import urllib.parse

def run_shell(command):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
        return result.stdout if result.stdout else result.stderr
    except Exception as e:
        return f"Shell error: {e}"

def launch_claude_code(ignore_input):
    try:
        apple_script = """
        osascript -e 'tell application "Terminal"
            activate
            do script "source ~/.zshrc && clear && claude"
        end tell'
        """
        subprocess.run(apple_script, shell=True)
        return "Claude Code terminal opened on your screen."
    except Exception as e:
        return f"Launch error: {e}"

def run_openclaw(args):
    PC_USER = "bot"
    PC_IP = "100.83.120.12"
    KEY_PATH = os.path.expanduser("~/.ssh/jarvis_key")
    OPENCLAW_PATH = "/home/bot/.npm-global/bin/openclaw"
    
    try:
        ssh_cmd = f"ssh -i {KEY_PATH} -o StrictHostKeyChecking=accept-new {PC_USER}@{PC_IP} '{OPENCLAW_PATH} \"{args}\"'"
        result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True, timeout=600)
        output = result.stdout.strip() if result.stdout else result.stderr.strip()
        return output if output else "Command executed on Lubuntu, but returned no output."
    except Exception as e:
        return f"Tunnel Error: {e}"

def launch_openclaw_terminal(ignore_input):
    PC_USER = "bot"
    PC_IP = "100.83.120.12"
    KEY_PATH = os.path.expanduser("~/.ssh/jarvis_key")
    
    try:
        ssh_cmd = f"ssh -i {KEY_PATH} -o StrictHostKeyChecking=accept-new -t {PC_USER}@{PC_IP}"
        apple_script = f"""
        osascript -e 'tell application "Terminal"
            activate
            do script "clear && echo \\"=== LIVE OPENCLAW TUNNEL ===\\" && {ssh_cmd}"
        end tell'
        """
        subprocess.run(apple_script, shell=True)
        return "Live OpenClaw terminal opened on your screen."
    except Exception as e:
        return f"Launch error: {e}"

def play_media(query):
    safe_query = query.replace('"', '').replace("'", "").strip()
    try:
        if safe_query.lower() in ["", "none", "play", "resume"]:
            subprocess.run("osascript -e 'tell application \"Music\" to play'", shell=True)
            return "Resumed Apple Music."
            
        script = f"""osascript -e 'tell application "Music"
            if not (exists main window) then activate
            play (first track whose name contains "{safe_query}" or artist contains "{safe_query}")
        end tell'"""
        
        result = subprocess.run(script, shell=True, capture_output=True, text=True)
        
        if "error" in result.stderr.lower():
            url_query = urllib.parse.quote(safe_query)
            subprocess.run(f'open "https://music.youtube.com/search?q={url_query}"', shell=True)
            return f"Apple restricted the track, so I bypassed it and pulled up {safe_query} on YouTube."
            
        return f"Playing {safe_query} on Apple Music."
    except Exception as e:
        return f"Media error: {e}"

AVAILABLE_TOOLS = {
    "run_shell": run_shell,
    "launch_claude_code": launch_claude_code,
    "run_openclaw": run_openclaw,
    "launch_openclaw_terminal": launch_openclaw_terminal,
    "play_media": play_media
}
