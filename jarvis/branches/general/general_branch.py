import subprocess, os, sys, re
sys.path.insert(0, os.path.expanduser("~/jarvis"))
from core.orchestrator import execute

HOME = os.path.expanduser("~")

def run_shell(cmd: str) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return r.stdout.strip() or r.stderr.strip() or "Done."
    except Exception as e:
        return f"Error: {e}"

def open_app(name: str) -> str:
    return run_shell(f'open -a "{name}"')

def open_url(url: str) -> str:
    if not url.startswith("http"):
        url = "https://" + url
    return run_shell(f'open "{url}"')

def open_chrome_search(query: str) -> str:
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    return run_shell(f'open -a "Google Chrome" "{url}"')

def create_file(path: str, content: str = "") -> str:
    path = path.replace("~", HOME)
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return f"Created {path}"

def open_folder(path: str) -> str:
    path = path.replace("~", HOME)
    return run_shell(f'open "{path}"')

def handle(instruction: str, context: dict = {}) -> str:
    t = instruction.lower()

    # OPEN APP
    if "open blender" in t:
        return open_app("Blender")
    if "open chrome" in t or "open google chrome" in t:
        return open_app("Google Chrome")
    if "open safari" in t:
        return open_app("Safari")
    if "open terminal" in t:
        return open_app("Terminal")
    if "open finder" in t:
        return open_app("Finder")
    if "open spotify" in t:
        return open_app("Spotify")
    if "open slack" in t:
        return open_app("Slack")
    if "open vscode" in t or "open vs code" in t or "open visual studio" in t:
        return open_app("Visual Studio Code")
    if "open antigravity" in t:
        return open_app("antigravity")
    if "open notes" in t:
        return open_app("Notes")
    if "open calendar" in t:
        return open_app("Calendar")
    if "open mail" in t:
        return open_app("Mail")
    if "open messages" in t:
        return open_app("Messages")

    # open generic app by name
    if t.startswith("open "):
        app_name = instruction[5:].strip()
        result = open_app(app_name)
        if "error" not in result.lower():
            return f"Opened {app_name}"
        return result

    # SEARCH / BROWSE
    if "search for" in t or "google" in t or "search the web" in t:
        query = re.sub(r"(search for|google|search the web for?)", "", t, flags=re.IGNORECASE).strip()
        return open_chrome_search(query)

    if "go to " in t or "open website" in t or "navigate to" in t:
        url = re.sub(r"(go to|open website|navigate to)", "", t, flags=re.IGNORECASE).strip()
        return open_url(url)

    # CREATE FILE
    if "create a file" in t or "make a file" in t or "new file" in t:
        match = re.search(r"[\w\-]+\.\w+", instruction)
        filename = match.group(0) if match else "untitled.txt"
        path = os.path.join(HOME, "Desktop", filename)
        return create_file(path)

    # OPEN FOLDER
    if "open folder" in t or "open directory" in t or "show me" in t:
        if "desktop" in t:
            return open_folder("~/Desktop")
        if "downloads" in t:
            return open_folder("~/Downloads")
        if "documents" in t:
            return open_folder("~/Documents")
        if "coding projects" in t or "coding" in t:
            return open_folder("~/coding projects")
        if "jarvis" in t:
            return open_folder("~/jarvis")

    # RUN TERMINAL COMMAND
    if t.startswith("run ") or "execute " in t or "terminal command" in t:
        cmd = re.sub(r"(run|execute|terminal command)", "", instruction, flags=re.IGNORECASE).strip()
        return run_shell(cmd)

    # SYSTEM ACTIONS
    if "take a screenshot" in t:
        return run_shell("screencapture ~/Desktop/screenshot.png && echo Screenshot saved to Desktop")

    if "volume up" in t:
        return run_shell("osascript -e 'set volume output volume (output volume of (get volume settings) + 10)'")
    if "volume down" in t:
        return run_shell("osascript -e 'set volume output volume (output volume of (get volume settings) - 10)'")
    if "mute" in t:
        return run_shell("osascript -e 'set volume output muted true'")

    if "what time is it" in t or "current time" in t:
        return run_shell("date '+%H:%M'")
    if "what day is it" in t or "today\'s date" in t or "what\'s the date" in t:
        return run_shell("date '+%A, %B %d %Y'")

    if "battery" in t:
        return run_shell("pmset -g batt | grep -o '[0-9]*%'")

    if "wifi" in t or "ip address" in t:
        return run_shell("ipconfig getifaddr en0")

    if "empty trash" in t:
        return run_shell("osascript -e 'tell application \"Finder\" to empty trash'")

    if "lock screen" in t or "lock my mac" in t:
        return run_shell("pmset displaysleepnow")

    if "sleep" in t and "mac" in t:
        return run_shell("pmset sleepnow")

    if "restart" in t and "jarvis" in t:
        run_shell("launchctl unload ~/Library/LaunchAgents/com.jarvis.api.plist && launchctl load ~/Library/LaunchAgents/com.jarvis.api.plist")
        return "Restarting Jarvis API..."

    # LIST FILES
    if "list files" in t or "what files" in t or "show files" in t:
        if "desktop" in t:
            return run_shell("ls ~/Desktop")
        if "downloads" in t:
            return run_shell("ls ~/Downloads")
        return run_shell("ls ~/Desktop")

    # PLAY MUSIC
    if "play music" in t or "play spotify" in t:
        return open_app("Spotify")

    # DEFAULT — ask the model
    return execute(instruction, "general")
