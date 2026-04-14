"""
tool_learner.py — Self-healing tool registry.
When Jarvis encounters a capability it doesn't have,
it asks Gemma to write the function and hot-reloads tools.py.
"""
import os
import re
import sys
import json
import requests
import importlib
import logging

log = logging.getLogger("jarvis.tool_learner")

TOOLS_PATH = os.path.expanduser("~/cowork/jarvis/core/tools.py")
GEMMA_URL  = "http://localhost:8081/v1/chat/completions"

SYSTEM_PROMPT = """You are a Python tool writer for a macOS AI assistant called Jarvis.
When given a tool name and description of what it should do, write a single Python function.
Rules:
- Function name must match the tool name exactly
- Use subprocess, os, or applescript to control the Mac
- Must return a string result
- No imports inside the function — assume subprocess, os, urllib.parse are available
- Output ONLY the function code, nothing else, no markdown fences"""


def ask_gemma(tool_name: str, context: str) -> str:
    prompt = f"Write a Python function called '{tool_name}' that does: {context}\nThe Mac home directory is /Users/ashkansamali."
    try:
        r = requests.post(GEMMA_URL, json={
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 500
        }, timeout=60)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"# Gemma error: {e}"


def extract_function(code: str, tool_name: str) -> str:
    # Strip markdown fences if Gemma adds them
    code = re.sub(r"```python|```", "", code).strip()
    # Make sure it starts with def
    if not code.startswith("def "):
        match = re.search(r"(def " + tool_name + r".*)", code, re.DOTALL)
        if match:
            code = match.group(1)
    return code


def add_tool(tool_name: str, context: str) -> bool:
    """Ask Gemma to write a new tool and add it to tools.py"""
    log.info(f"[ToolLearner] Learning new tool: {tool_name}")

    code = ask_gemma(tool_name, context)
    func_code = extract_function(code, tool_name)

    if not func_code.startswith("def "):
        log.error(f"[ToolLearner] Gemma didn't return a valid function: {func_code[:100]}")
        return False

    # Read current tools.py
    with open(TOOLS_PATH, "r") as f:
        content = f.read()

    # Don't add duplicates
    if f"def {tool_name}(" in content:
        log.info(f"[ToolLearner] Tool '{tool_name}' already exists.")
        return True

    # Insert function before AVAILABLE_TOOLS dict
    insert_point = content.rfind("AVAILABLE_TOOLS = {")
    if insert_point == -1:
        log.error("[ToolLearner] Could not find AVAILABLE_TOOLS in tools.py")
        return False

    new_content = (
        content[:insert_point]
        + func_code + "\n\n"
        + content[insert_point:]
    )

    # Add to AVAILABLE_TOOLS dict
    new_content = new_content.replace(
        "AVAILABLE_TOOLS = {",
        f'AVAILABLE_TOOLS = {{\n    "{tool_name}": {tool_name},'
    )

    # Save
    with open(TOOLS_PATH, "w") as f:
        f.write(new_content)

    # Hot-reload
    try:
        import core.tools as tools_module
        importlib.reload(tools_module)
        log.info(f"[ToolLearner] Tool '{tool_name}' added and reloaded successfully.")
        return True
    except Exception as e:
        log.error(f"[ToolLearner] Reload failed: {e}")
        return False


def handle_missing_tool(tool_name: str, args: str) -> str:
    """Called by router when a tool doesn't exist. Learns it then runs it."""
    log.info(f"[ToolLearner] Missing tool: '{tool_name}' with args: '{args}'")
    context = f"open or launch '{args}' on macOS" if not args else f"run '{tool_name}' with argument: {args}"
    
    success = add_tool(tool_name, context)
    if success:
        # Try running the newly learned tool
        try:
            import core.tools as tools_module
            importlib.reload(tools_module)
            if tool_name in tools_module.AVAILABLE_TOOLS:
                result = tools_module.AVAILABLE_TOOLS[tool_name](args)
                return f"I just learned how to '{tool_name}' and did it. {result}"
        except Exception as e:
            return f"Learned '{tool_name}' but failed to run it: {e}"
    
    return f"I tried to learn '{tool_name}' but Gemma couldn't write it."
