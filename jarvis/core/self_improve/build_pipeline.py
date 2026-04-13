import asyncio, json, os, subprocess, time, requests
from pathlib import Path
from datetime import datetime

COWORK = Path("/Users/ashkansamali/cowork")

def _call_qwen(prompt: str) -> str:
    r = requests.post("http://localhost:8081/v1/chat/completions", json={
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1, "max_tokens": 800, "stream": False
    }, timeout=60)
    return r.json()["choices"][0]["message"]["content"].strip()

async def run_pipeline(goal: str, websocket=None) -> str:
    if websocket:
        await websocket.send_json({"type": "status", "msg": f"[BuildPipeline] Planning: {goal[:60]}"})

    # Plan the project
    plan_prompt = f"""Plan a software project for: {goal}
Return JSON only: {{
  "project_name": "name",
  "project_type": "fastapi|flask|python|express",
  "project_path": "~/Desktop/project_name",
  "port": 3000,
  "components": [{{"name": "c", "file": "f.py", "description": "what it does"}}],
  "dependencies": []
}}"""
    try:
        plan = json.loads(await asyncio.to_thread(_call_qwen, plan_prompt))
    except:
        plan = {"project_name": "project", "project_type": "python",
                "project_path": "~/Desktop/project", "port": 3000,
                "components": [{"name": "main", "file": "main.py", "description": goal}],
                "dependencies": []}

    project_path = os.path.expanduser(plan["project_path"])
    os.makedirs(project_path, exist_ok=True)

    if websocket:
        await websocket.send_json({"type": "status", "msg": f"[BuildPipeline] Building {len(plan['components'])} components..."})

    from core.agents.hierarchy import AgentHierarchy
    h = AgentHierarchy()
    build_task = f"Build this project in {project_path}: {goal}. Components: {json.dumps(plan['components'])}"
    result = await h.run(build_task, websocket)

    from core.agents.dev_tools import start_local_server
    launch = await start_local_server(project_path, plan.get("port", 3000))

    return f"Build complete. {launch}\nProject: {project_path}"
