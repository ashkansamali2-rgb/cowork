import subprocess, os, sys
sys.path.insert(0, os.path.expanduser("~/jarvis"))
from config import JARVIS_ROOT, ANTHROPIC_API_KEY
from core.orchestrator import execute
from core.memory import remember_project, recall_project
from core.search import search_and_browse

CODING_PROJECTS = os.path.expanduser("~/coding projects")

def get_project_path(project_name: str = "general") -> str:
    path = os.path.join(CODING_PROJECTS, project_name)
    os.makedirs(path, exist_ok=True)
    return path

def open_in_antigravity(path: str):
    try:
        subprocess.Popen(["antigravity", path])
        return f"Opened {path} in Antigravity"
    except Exception as e:
        return f"Could not open Antigravity: {e}"

def open_chrome(url: str = None, query: str = None) -> str:
    try:
        target = url if url else f"https://www.google.com/search?q={query.replace(' ', '+')}"
        subprocess.Popen(["open", "-a", "Google Chrome", target])
        return f"Opened Chrome: {target}"
    except Exception as e:
        return f"Chrome error: {e}"

def create_file(filepath: str, content: str = "") -> str:
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write(content)
        return f"Created {filepath}"
    except Exception as e:
        return f"File error: {e}"

def run_terminal(command: str) -> str:
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout or result.stderr or "Done"
    except Exception as e:
        return f"Terminal error: {e}"

def git_push(project_path: str, message: str = "Jarvis: update") -> str:
    try:
        subprocess.run(["git", "add", "."], cwd=project_path, check=True)
        result = subprocess.run(["git", "commit", "-m", message], cwd=project_path, capture_output=True, text=True)
        if "nothing to commit" in result.stdout:
            return "Nothing new to commit"
        push = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=project_path, capture_output=True, text=True)
        return "Pushed to GitHub" if push.returncode == 0 else f"Push error: {push.stderr}"
    except Exception as e:
        return f"Git error: {e}"

def run_claude_code(instruction: str, project_path: str) -> str:
    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
    try:
        result = subprocess.run(
            ["claude", "--print", instruction],
            cwd=project_path, capture_output=True, text=True, env=env, timeout=300
        )
        out = result.stdout or result.stderr or ""
        if "credit balance" in out or "invalid_request" in out:
            return None
        return out.strip() or None
    except:
        return None

def handle(instruction: str, context: dict = {}) -> str:
    t = instruction.lower()
    project_name = context.get("project", "general")
    project_path = get_project_path(project_name)

    # detect project name from instruction
    if "project vision" in t or "vision project" in t:
        project_path = get_project_path("vision")
    elif "general coding" in t or "general project" in t:
        project_path = get_project_path("general")

    # recall memory for context
    memory = recall_project(project_name, instruction)
    if memory:
        print(f"[Coding] Memory: {memory[:80]}")

    # OPEN FILE/FOLDER IN ANTIGRAVITY
    if any(k in t for k in ["open in antigravity", "open antigravity", "open the project", "open project"]):
        return open_in_antigravity(project_path)

    # OPEN CHROME
    if "open chrome" in t or "search the web" in t or "google" in t:
        if "search" in t:
            query = instruction.split("search", 1)[-1].strip().lstrip("for").strip()
            return open_chrome(query=query)
        return open_chrome(url="https://www.google.com")

    # CREATE FILE
    if "create a file" in t or "make a file" in t or "new file" in t:
        # extract filename if mentioned
        import re
        # look for filename with extension first
        match = re.search(r"[\w\-]+\.\w+", instruction)
        if match:
            filename = match.group(0)
        else:
            # fallback: word after called/named
            m2 = re.search(r"(?:called|named|file)\s+(\S+)", instruction, re.IGNORECASE)
            filename = m2.group(1).strip(".,") if m2 else "untitled.py"
        filepath = os.path.join(project_path, filename)
        return create_file(filepath)

    # RUN TERMINAL COMMAND
    if t.startswith("run ") or "run this" in t or "execute" in t or "terminal" in t:
        cmd = instruction.split(" ", 1)[-1] if t.startswith("run ") else instruction
        return run_terminal(cmd)

    # GIT PUSH
    if "push to git" in t or "push to github" in t or "commit and push" in t:
        return git_push(project_path, instruction[:50])

    # WRITE/BUILD CODE — use Claude Code or local model
    if any(k in t for k in ["write", "build", "create", "generate", "code", "implement", "add", "fix", "update"]):
        print("[Coding] Writing code...")
        
        # add memory context
        if memory:
            instruction = f"Project context: {memory[:300]}\n\nTask: {instruction}"

        result = run_claude_code(instruction, project_path)
        if not result:
            result = execute(instruction, "coding")

        # save if looks like code
        if result and ("def " in result or "import " in result or "function " in result or "class " in result):
            out_file = os.path.join(project_path, "main.py")
            with open(out_file, "w") as f:
                f.write(result)
            remember_project(project_name, f"Built: {instruction[:100]}", "code")
            open_in_antigravity(project_path)
            return f"Code written and saved to {out_file}\n\n{result[:400]}"
        return result or "Done"

    # DEFAULT — just execute with local model
    return execute(instruction, "coding")
