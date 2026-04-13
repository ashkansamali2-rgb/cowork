#!/usr/bin/env python3
"""Project builder — scaffold, implement, and launch projects from templates."""
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

COWORK = Path("/Users/ashkansamali/cowork")

PROJECT_TEMPLATES = {
    "fastapi": {
        "files": {
            "main.py": (
                "from fastapi import FastAPI\n"
                "from fastapi.middleware.cors import CORSMiddleware\n\n"
                "app = FastAPI(title='{name}')\n"
                "app.add_middleware(CORSMiddleware, allow_origins=['*'], "
                "allow_methods=['*'], allow_headers=['*'])\n\n"
                "@app.get('/')\ndef root():\n"
                "    return {{'name': '{name}', 'status': 'running'}}\n"
            ),
            "requirements.txt": "fastapi\nuvicorn\n",
        },
        "install": ["pip", "install", "-r", "requirements.txt"],
        "run": "uvicorn main:app --reload --port {port}",
    },
    "flask": {
        "files": {
            "app.py": (
                "from flask import Flask, jsonify\n"
                "from flask_cors import CORS\n\n"
                "app = Flask('{name}')\n"
                "CORS(app)\n\n"
                "@app.route('/')\n"
                "def index():\n"
                "    return jsonify({{'name': '{name}', 'status': 'running'}})\n\n"
                "if __name__ == '__main__':\n"
                "    app.run(debug=True, port={port})\n"
            ),
            "requirements.txt": "flask\nflask-cors\n",
        },
        "install": ["pip", "install", "-r", "requirements.txt"],
        "run": "python3 app.py",
    },
    "python": {
        "files": {
            "main.py": (
                "def main():\n"
                "    print('Running {name}')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
            "requirements.txt": "",
        },
        "run": "python3 main.py",
    },
    "express": {
        "files": {
            "index.js": (
                "const express = require('express');\n"
                "const app = express();\n"
                "app.use(express.json());\n"
                "app.get('/', (req,res) => res.json({{name:'{name}',status:'running'}}));\n"
                "app.listen({port}, () => console.log('{name} running on port {port}'));\n"
            ),
            "package.json": (
                '{{"name":"{name}","version":"1.0.0",'
                '"scripts":{{"start":"node index.js"}},'
                '"dependencies":{{"express":"^4.18.0"}}}}'
            ),
        },
        "install": ["npm", "install"],
        "run": "node index.js",
    },
}


async def build_project(
    name: str,
    project_type: str,
    description: str = "",
    location: str = "~/Desktop",
    port: int = 3000,
) -> str:
    location     = os.path.expanduser(location)
    project_path = os.path.join(location, name)
    os.makedirs(project_path, exist_ok=True)

    template = PROJECT_TEMPLATES.get(project_type.lower(), PROJECT_TEMPLATES["python"])

    # Write template files
    for filename, content in template["files"].items():
        content = content.replace("{name}", name).replace("{port}", str(port))
        with open(os.path.join(project_path, filename), "w") as f:
            f.write(content)

    # Install dependencies
    if "install" in template:
        try:
            subprocess.run(
                template["install"], cwd=project_path,
                capture_output=True, timeout=120
            )
        except Exception:
            pass

    # Use Qwen to implement the actual functionality if description given
    if description:
        try:
            sys.path.insert(0, str(COWORK / "jarvis"))
            from core.agents.runtime import AgentRuntime
            build_task = (
                f"Implement this functionality in {project_path}: {description}. "
                f"The scaffold files already exist. Write the actual working code. "
                f"Read existing files first, then modify them."
            )
            agent  = AgentRuntime(task=build_task, max_steps=25)
            await asyncio.wait_for(agent.run(None), timeout=300)
        except Exception:
            pass

    # Add to knowledge graph
    try:
        from core.memory.knowledge_graph import KnowledgeGraph
        KnowledgeGraph().add_node(
            name, name, "project",
            {"path": project_path, "type": project_type, "port": port}
        )
    except Exception:
        pass

    return project_path


async def launch_project(project_path: str, port: int = 3000) -> str:
    project_path = os.path.expanduser(project_path)

    # Determine run command
    if os.path.exists(f"{project_path}/package.json"):
        try:
            pkg = json.loads(open(f"{project_path}/package.json").read())
            scripts = pkg.get("scripts", {})
            run_cmd = scripts.get("dev") or scripts.get("start") or "npm start"
        except Exception:
            run_cmd = "npm start"
    elif os.path.exists(f"{project_path}/app.py"):
        run_cmd = "python3 app.py"
    elif os.path.exists(f"{project_path}/main.py"):
        run_cmd = "python3 main.py"
    else:
        run_cmd = f"ls {project_path}"

    script = f'tell application "Terminal" to do script "cd {project_path} && {run_cmd}"'
    subprocess.run(["osascript", "-e", script])
    await asyncio.sleep(3)

    try:
        import urllib.request
        urllib.request.urlopen(f"http://localhost:{port}", timeout=5)
        subprocess.run(["open", f"http://localhost:{port}"])
        return f"Launched at http://localhost:{port}"
    except Exception:
        return f"Launched in Terminal. Check http://localhost:{port}"
