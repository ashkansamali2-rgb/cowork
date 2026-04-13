import asyncio, os, subprocess, time
import urllib.request
from pathlib import Path

async def start_local_server(project_path: str, port: int = 3000) -> str:
    project_path = os.path.expanduser(project_path)
    subprocess.run(f"lsof -ti:{port} | xargs kill -9 2>/dev/null", shell=True)

    if os.path.exists(f"{project_path}/package.json"):
        import json
        pkg = json.loads(open(f"{project_path}/package.json").read())
        run_cmd = pkg.get("scripts", {}).get("dev") or pkg.get("scripts", {}).get("start") or "npm start"
    elif os.path.exists(f"{project_path}/app.py"):
        run_cmd = "python3 app.py"
    else:
        run_cmd = "python3 main.py"

    script = f'tell application "Terminal" to do script "cd {project_path} && {run_cmd}"'
    subprocess.run(["osascript", "-e", script])
    await asyncio.sleep(4)

    try:
        urllib.request.urlopen(f"http://localhost:{port}", timeout=5)
        subprocess.run(["open", f"http://localhost:{port}"])
        return f"Server running at http://localhost:{port}"
    except:
        return f"Server starting at http://localhost:{port} — check Terminal"

async def fix_localhost_error(port: int = 3000) -> str:
    subprocess.run(["open", f"http://localhost:{port}"])
    await asyncio.sleep(2)
    path = f"/tmp/localhost_{port}.png"
    subprocess.run(["screencapture", "-x", path])
    from core.agents.runtime import create_agent
    agent = create_agent(f"Fix the error visible at http://localhost:{port}. Screenshot at {path}.", agent_id=f"FIX-{int(time.time())}")
    return await agent.run(None)
