import asyncio, json, os, subprocess, sys, time
import requests
from pathlib import Path

TEMPLATES = {
    "fastapi": {
        "files": {
            "main.py": "from fastapi import FastAPI\nfrom fastapi.middleware.cors import CORSMiddleware\n\napp = FastAPI(title='{name}')\napp.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])\n\n@app.get('/')\ndef root():\n    return {{'name': '{name}', 'status': 'running'}}\n",
            "requirements.txt": "fastapi\nuvicorn\n"
        },
        "install": ["pip", "install", "-r", "requirements.txt"],
        "run": "uvicorn main:app --reload --port {port}"
    },
    "flask": {
        "files": {
            "app.py": "from flask import Flask, jsonify\napp = Flask(__name__)\n\n@app.route('/')\ndef index():\n    return jsonify({{'name': '{name}', 'status': 'running'}})\n\nif __name__ == '__main__':\n    app.run(debug=True, port={port})\n",
            "requirements.txt": "flask\n"
        },
        "install": ["pip", "install", "-r", "requirements.txt"],
        "run": "python3 app.py"
    },
    "python": {
        "files": {
            "main.py": "def main():\n    print('Running {name}')\n\nif __name__ == '__main__':\n    main()\n",
            "requirements.txt": ""
        },
        "run": "python3 main.py"
    },
    "express": {
        "files": {
            "index.js": "const express = require('express');\nconst app = express();\napp.get('/', (req,res) => res.json({{name:'{name}',status:'running'}}));\napp.listen({port}, () => console.log('running on {port}'));\n",
            "package.json": '{{"name":"{name}","scripts":{{"start":"node index.js"}},"dependencies":{{"express":"^4"}}}}'
        },
        "install": ["npm", "install"],
        "run": "node index.js"
    }
}

async def build_project(name: str, project_type: str = "python",
                        description: str = "", location: str = "~/Desktop",
                        port: int = 3000) -> str:
    location = os.path.expanduser(location)
    project_path = os.path.join(location, name)
    os.makedirs(project_path, exist_ok=True)

    template = TEMPLATES.get(project_type.lower(), TEMPLATES["python"])

    for filename, content in template["files"].items():
        content = content.replace("{name}", name).replace("{port}", str(port))
        with open(os.path.join(project_path, filename), "w") as f:
            f.write(content)

    if "install" in template:
        subprocess.run(template["install"], cwd=project_path,
                      capture_output=True, timeout=120)

    if description:
        from core.agents.hierarchy import AgentHierarchy
        h = AgentHierarchy()
        await h.run(f"Implement this in {project_path}: {description}. Scaffold exists. Write working code.")

    return project_path

async def launch_project(project_path: str, port: int = 3000) -> str:
    project_path = os.path.expanduser(project_path)
    if os.path.exists(f"{project_path}/package.json"):
        run_cmd = "npm start"
    elif os.path.exists(f"{project_path}/app.py"):
        run_cmd = "python3 app.py"
    else:
        run_cmd = "python3 main.py"

    script = f'tell application "Terminal" to do script "cd {project_path} && {run_cmd}"'
    subprocess.run(["osascript", "-e", script])
    await asyncio.sleep(3)

    try:
        import urllib.request
        urllib.request.urlopen(f"http://localhost:{port}", timeout=5)
        subprocess.run(["open", f"http://localhost:{port}"])
        return f"Launched at http://localhost:{port}"
    except:
        return f"Launched in Terminal — check http://localhost:{port}"
