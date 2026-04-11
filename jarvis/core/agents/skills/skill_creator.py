import requests
import ast
import os
import json
from pathlib import Path
from datetime import datetime


def skill_creator(task_description: str) -> str:
    """
    Creates a new skill/tool for the agent to use.
    Call this when you need a capability that doesn't exist yet.
    Args: task_description — describe what the new skill should do
    Returns: name of the newly created skill
    """
    # Ask Qwen to write the skill
    prompt = f"""Write a Python function for this task: {task_description}
Requirements:
- Function name must start with skill_
- Must return a string
- Handle all errors with try/except
- Use only standard library + requests + subprocess
Output ONLY the raw Python function, no explanation, no markdown."""

    try:
        r = requests.post("http://localhost:8081/v1/chat/completions", json={
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 800
        }, timeout=120)
        r.raise_for_status()
        code = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Error: Failed to generate skill code: {e}"

    # Strip markdown fences if present
    code = code.replace("```python", "").replace("```", "").strip()

    # Validate syntax and extract function name
    try:
        tree = ast.parse(code)
        func_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        if not func_names:
            return "Error: No function found in generated code"
        skill_name = func_names[0]
        if not skill_name.startswith("skill_"):
            skill_name = "skill_" + skill_name
    except SyntaxError as e:
        return f"Error: Invalid syntax in generated skill: {e}"

    # Save to skills directory
    skills_dir = Path(__file__).parent
    skill_path = skills_dir / f"{skill_name}.py"
    skill_path.write_text(code)

    # Register immediately in TOOLS
    try:
        import importlib.util, inspect, sys
        # Import the parent tools module to register
        spec = importlib.util.spec_from_file_location(skill_name, skill_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # Try to register in the tools module TOOLS dict
        try:
            from core.agents.tools import TOOLS, TOOL_DESCRIPTIONS
            for name, func in inspect.getmembers(module, inspect.isfunction):
                if name.startswith("skill_"):
                    TOOLS[name] = func
                    TOOL_DESCRIPTIONS[name] = f"Dynamically created skill: {task_description}"
        except ImportError:
            pass
    except Exception as e:
        return f"Skill saved to {skill_path} but failed to load: {e}"

    # Update registry
    registry_path = skills_dir / "registry.json"
    try:
        registry = json.loads(registry_path.read_text()) if registry_path.exists() else []
    except Exception:
        registry = []
    registry.append({
        "name": skill_name,
        "task": task_description,
        "created": str(datetime.now())
    })
    registry_path.write_text(json.dumps(registry, indent=2))

    return f"Created new skill: {skill_name}. It is now available as a tool."
