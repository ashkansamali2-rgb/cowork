"""
skill_builder.py — Runtime skill learning system.

When an agent fails a step or encounters a missing tool, SkillBuilder:
1. Asks Qwen to write a new Python function to handle the situation
2. Validates the code with ast.parse + safety checks
3. Saves it to ~/cowork/jarvis/core/agents/skills/[name].py
4. Registers it in the tool registry (tools.TOOLS)
5. Logs to ~/cowork/jarvis/core/agents/skills/registry.json
"""
import ast
import importlib
import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

SKILLS_DIR   = Path(__file__).parent / "skills"
REGISTRY_FILE = SKILLS_DIR / "registry.json"

# Dangerous patterns we never allow in generated code
_DANGEROUS_PATTERNS = [
    "os.system", "subprocess.call", "__import__", "eval(", "exec(",
    "shutil.rmtree", "os.remove", "open('/etc", "open('/dev",
    "socket.connect", "requests.delete",
]

_SKILL_SYSTEM = """\
You are a Python skill generator for an autonomous agent.
When given a failed tool call or missing capability, you write a new Python function.

Rules:
- Function name must start with skill_
- Must accept keyword or positional arguments
- Must return a string result
- No side effects beyond reading/writing files
- No dangerous operations (no rm -rf, no eval, no exec)
- Use only stdlib + requests + pathlib
- Include a docstring
- Keep it under 50 lines

Output ONLY the Python function code, nothing else. No markdown, no explanation.
"""

_SKILL_PROMPT = """\
A tool called {action} failed with error: {error}
The agent was trying to: {task}

Write a new Python function that solves this problem.
The function must:
1. Have a clear name starting with skill_
2. Accept flexible arguments (*args, **kwargs)
3. Return a string result
4. Handle errors gracefully
5. Use only these imports: os, subprocess, requests, json, pathlib

Think creatively — if the original tool failed, find an alternative approach.
Example: if fetch_url fails with 403, try using curl with a browser user-agent instead.

Output ONLY the Python function code, nothing else.
"""


class SkillBuilder:
    def __init__(self, tools: dict = None):
        self.tools = tools or {}
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_registry()
        self._auto_load_skills()

    def _load_registry(self):
        if REGISTRY_FILE.exists():
            try:
                self._registry = json.loads(REGISTRY_FILE.read_text())
            except Exception:
                self._registry = {}
        else:
            self._registry = {}

    def _save_registry(self):
        REGISTRY_FILE.write_text(json.dumps(self._registry, indent=2))

    def _auto_load_skills(self):
        """Load all skills from the skills/ directory into the tool registry."""
        loaded = 0
        for skill_file in SKILLS_DIR.glob("skill_*.py"):
            try:
                fn = self._load_skill_file(skill_file)
                if fn:
                    self.tools[fn.__name__] = fn
                    loaded += 1
            except Exception:
                pass
        if loaded:
            print(f"[SkillBuilder] Auto-loaded {loaded} skills from {SKILLS_DIR}")

    def _load_skill_file(self, path: Path):
        """Import a skill file and return its primary function."""
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Find the skill_ function
        for name in dir(mod):
            if name.startswith("skill_"):
                fn = getattr(mod, name)
                if callable(fn):
                    return fn
        return None

    def handle_failure(self, task: str, error: str, context: dict) -> Optional[str]:
        """
        Called when a tool raises an exception.
        Tries to generate and register a fix skill.
        Returns a description of what was done, or None.
        """
        action   = context.get("action", "unknown")
        skill_name = re.sub(r'[^a-z0-9_]', '_', action.lower())

        print(f"[SkillBuilder] Handling failure for '{action}': {error[:80]}")

        # Generate skill
        code = self._generate_skill(task, error, action, str(context), skill_name)
        if not code:
            return None

        # Validate
        if not self._validate_code(code):
            print(f"[SkillBuilder] Generated code failed validation")
            return None

        # Save
        skill_file = SKILLS_DIR / f"skill_{skill_name}.py"
        skill_file.write_text(code)

        # Load and register
        try:
            fn = self._load_skill_file(skill_file)
            if fn:
                self.tools[fn.__name__] = fn
                self._registry[fn.__name__] = {
                    "created_at":  datetime.now().isoformat(),
                    "triggered_by": error[:100],
                    "task":         task[:100],
                    "file":         str(skill_file),
                }
                self._save_registry()
                print(f"[SkillBuilder] Registered new skill: {fn.__name__}")
                return f"Learned and registered skill: {fn.__name__}"
        except Exception as e:
            print(f"[SkillBuilder] Failed to load generated skill: {e}")

        return None

    def handle_missing_tool(self, tool_name: str, args: dict, task: str) -> str:
        """
        Called when the agent requests a tool that doesn't exist.
        Returns 'SKILL_LOADED: skill_name' if successful, else error string.
        """
        # Check if we already have a similar skill
        for registered_name in self.tools:
            if tool_name.lower() in registered_name.lower():
                return f"SKILL_LOADED: {registered_name}"

        error = f"Tool '{tool_name}' does not exist"
        skill_name = re.sub(r'[^a-z0-9_]', '_', tool_name.lower())
        code = self._generate_skill(task, error, tool_name, str(args), skill_name)

        if not code or not self._validate_code(code):
            return f"Could not learn tool: {tool_name}"

        skill_file = SKILLS_DIR / f"skill_{skill_name}.py"
        skill_file.write_text(code)

        try:
            fn = self._load_skill_file(skill_file)
            if fn:
                self.tools[fn.__name__] = fn
                self._registry[fn.__name__] = {
                    "created_at":    datetime.now().isoformat(),
                    "triggered_by":  f"missing tool: {tool_name}",
                    "task":          task[:100],
                    "file":          str(skill_file),
                }
                self._save_registry()
                return f"SKILL_LOADED: {fn.__name__}"
        except Exception as e:
            pass

        return f"Could not load generated skill for: {tool_name}"

    def _generate_skill(self, task: str, error: str, action: str, context: str, skill_name: str) -> Optional[str]:
        """Ask Qwen to generate a new skill."""
        try:
            import requests
            prompt = _SKILL_PROMPT.format(
                error=error[:300],
                task=task[:200],
                action=action,
            )
            payload = {
                "model": "qwen",
                "messages": [
                    {"role": "system", "content": _SKILL_SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens":  600,
            }
            resp = requests.post(
                "http://localhost:8081/v1/chat/completions",
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            # Strip markdown fences if present
            raw = re.sub(r'^```[a-z]*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
            return raw.strip()
        except Exception as e:
            print(f"[SkillBuilder] Qwen generation failed: {e}")
            return None

    def _validate_code(self, code: str) -> bool:
        """Validate generated code: parseable Python + no dangerous ops."""
        try:
            ast.parse(code)
        except SyntaxError as e:
            print(f"[SkillBuilder] Syntax error in generated code: {e}")
            return False

        for pattern in _DANGEROUS_PATTERNS:
            if pattern in code:
                print(f"[SkillBuilder] Dangerous pattern found: {pattern}")
                return False

        # Must define at least one skill_ function
        if "def skill_" not in code:
            print("[SkillBuilder] No skill_ function found in generated code")
            return False

        return True

    def list_skills(self) -> list[str]:
        """Return list of all registered skill names."""
        return list(self._registry.keys())
