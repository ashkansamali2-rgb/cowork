"""
planner.py — Task planner for the autonomous agent runtime.

Takes a natural language task, sends to Gemma (port 8081),
gets back a structured JSON plan with sequential steps.
"""
import json
import re
from pathlib import Path
from typing import Optional

AGENTS_DIR = Path.home() / "cowork" / "agents"

_PLAN_SYSTEM = """\
You are a task planner for an autonomous agent.

Given a task and a list of available tools, break the task into clear sequential steps.
Each step uses exactly one tool.

Respond with ONLY valid JSON in this exact format:
{
  "task": "original task description",
  "steps": [
    {"step": 1, "action": "tool_name", "args": {"key": "value"}, "description": "why this step"},
    {"step": 2, "action": "tool_name", "args": {"key": "value"}, "description": "why this step"}
  ],
  "estimated_steps": 5
}

Rules:
- Only use tools from the provided list
- Keep args as concrete as possible
- Maximum 10 steps
- Last step should always produce a result (create_document, write_file, speak, or return data)
"""

_PLAN_USER = """\
TASK: {task}

AVAILABLE TOOLS:
{tool_descriptions}

Create a step-by-step plan to accomplish this task.
"""


class TaskPlanner:
    def __init__(self, tool_descriptions: str = ""):
        self.tool_descriptions = tool_descriptions
        self._gemma_url = "http://localhost:8081/v1/chat/completions"
        self._qwen_url  = "http://localhost:8081/v1/chat/completions"

    def plan(self, task: str) -> dict:
        """
        Generate a structured plan for the given task.
        Returns dict with 'task' and 'steps' keys.
        Falls back gracefully if LLM is offline.
        """
        try:
            raw = self._call_llm(task)
            plan = self._parse_plan(raw)
            if plan and plan.get("steps"):
                return plan
        except Exception as e:
            print(f"[TaskPlanner] Planning failed: {e}")

        # Fallback: minimal plan
        return self._fallback_plan(task)

    def _call_llm(self, task: str) -> str:
        import requests
        prompt = _PLAN_USER.format(task=task, tool_descriptions=self.tool_descriptions)

        # Try Gemma first, fall back to Qwen
        for url in [self._gemma_url, self._qwen_url]:
            try:
                payload = {
                    "model": "gemma",
                    "messages": [
                        {"role": "system", "content": _PLAN_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens":  800,
                }
                resp = requests.post(url, json=payload, timeout=60)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                continue

        raise RuntimeError("Both Gemma and Qwen unreachable for planning")

    def _parse_plan(self, raw: str) -> Optional[dict]:
        """Extract JSON plan from LLM response."""
        # Try to find JSON block
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            return None
        try:
            plan = json.loads(json_match.group(0))
            # Validate structure
            if isinstance(plan.get("steps"), list):
                return plan
        except json.JSONDecodeError:
            pass
        return None

    def _fallback_plan(self, task: str) -> dict:
        """
        Simple heuristic fallback plan when LLM is unavailable.
        Inspects task keywords to build a basic plan.
        """
        task_lower = task.lower()
        steps = []

        # Research tasks
        if any(k in task_lower for k in ("research", "find", "look up", "search")):
            query = task
            for prefix in ("research ", "find ", "look up ", "search for "):
                if task_lower.startswith(prefix):
                    query = task[len(prefix):]
                    break
            steps.append({"step": 1, "action": "web_search",
                           "args": {"query": query},
                           "description": "Search for relevant information"})
            steps.append({"step": 2, "action": "summarize",
                           "args": {"text": "{previous_result}", "instruction": "Summarize the key findings"},
                           "description": "Summarize search results"})

        # Document/write tasks
        if any(k in task_lower for k in ("document", "create", "write", "save", "file")):
            steps.append({"step": len(steps) + 1, "action": "create_document",
                           "args": {"title": task[:40], "content": "{previous_result}", "fmt": "md"},
                           "description": "Save results to a document"})

        # URL fetch tasks
        if "http" in task_lower or "website" in task_lower or "download" in task_lower:
            url_match = re.search(r'https?://[^\s]+', task)
            if url_match:
                steps.append({"step": len(steps) + 1, "action": "fetch_url",
                               "args": {"url": url_match.group(0)},
                               "description": "Fetch the webpage"})

        # Default: just do a search
        if not steps:
            steps = [
                {"step": 1, "action": "web_search",
                 "args": {"query": task},
                 "description": "Search for information about the task"},
                {"step": 2, "action": "summarize",
                 "args": {"text": "{previous_result}", "instruction": "Summarize and answer the task"},
                 "description": "Summarize findings"},
            ]

        return {"task": task, "steps": steps, "estimated_steps": len(steps), "fallback": True}

    def save_plan(self, agent_id: str, plan: dict):
        """Save plan to ~/cowork/agents/[agent_id]/plan.json"""
        agent_dir = AGENTS_DIR / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "plan.json").write_text(json.dumps(plan, indent=2))
