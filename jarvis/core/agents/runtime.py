"""
runtime.py — Autonomous AgentRuntime with ReAct loop.

Think → Act → Observe → repeat until FINAL_ANSWER or max_steps.
"""
import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Callable

AGENTS_DIR = Path.home() / "cowork" / "agents"

_THINK_SYSTEM = """\
You are an autonomous agent. You solve tasks step by step using tools.

Available tools:
{tool_descriptions}

Response format — you MUST use exactly one of:
  ACTION: tool_name
  ARGS: {{"key": "value", ...}}

  or when done:
  FINAL_ANSWER: [your complete answer here]

Rules:
- Use one tool per step
- ARGS must be valid JSON
- When you have enough information, use FINAL_ANSWER
- Be decisive — don't repeat the same search
"""

_THINK_USER = """\
TASK: {task}

STEP HISTORY:
{history}

CURRENT OBSERVATION:
{observation}

What is your next action? Choose a tool or provide FINAL_ANSWER.
"""


class AgentRuntime:
    def __init__(
        self,
        task: str,
        agent_id: str,
        tools: dict,
        tool_descriptions: str,
        max_steps: int = 20,
        on_step: Optional[Callable] = None,
        planner=None,
        skill_builder=None,
    ):
        self.task             = task
        self.agent_id         = agent_id
        self.tools            = tools
        self.tool_descriptions = tool_descriptions
        self.max_steps        = max_steps
        self.on_step          = on_step   # callback(agent_id, step, action, observation)
        self.planner          = planner
        self.skill_builder    = skill_builder
        self.history: list[dict] = []
        self.result: Optional[str] = None
        self.status: str = "pending"

    async def run(self, websocket=None) -> str:
        self.status = "running"
        AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        agent_dir = AGENTS_DIR / self.agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Save initial plan if planner available
        if self.planner:
            try:
                plan = await asyncio.to_thread(self.planner.plan, self.task)
                (agent_dir / "plan.json").write_text(json.dumps(plan, indent=2))
                initial_obs = f"Plan created: {len(plan.get('steps', []))} steps"
            except Exception as e:
                initial_obs = f"Planning skipped: {e}"
        else:
            initial_obs = "Starting task."

        observation = initial_obs
        await self._publish_update(0, "start", observation)

        for step in range(1, self.max_steps + 1):
            # ── THINK ──────────────────────────────────────────────────────────
            history_text = self._format_history()
            think_prompt = _THINK_USER.format(
                task=self.task,
                history=history_text or "(none)",
                observation=observation,
            )
            system_prompt = _THINK_SYSTEM.format(tool_descriptions=self.tool_descriptions)

            try:
                llm_response = await asyncio.to_thread(
                    self._call_qwen, system_prompt, think_prompt
                )
            except Exception as e:
                observation = f"LLM call failed: {e}"
                self.history.append({"step": step, "action": "think_error", "observation": observation})
                continue

            # ── PARSE RESPONSE ─────────────────────────────────────────────────
            if "FINAL_ANSWER:" in llm_response:
                self.result = llm_response.split("FINAL_ANSWER:", 1)[1].strip()
                self.history.append({"step": step, "action": "FINAL_ANSWER", "observation": self.result})
                await self._publish_update(step, "FINAL_ANSWER", self.result)
                break

            action, args = self._parse_action(llm_response)
            if not action:
                observation = f"Could not parse action from: {llm_response[:200]}"
                self.history.append({"step": step, "action": "parse_error", "observation": observation})
                continue

            # ── ACT ────────────────────────────────────────────────────────────
            await self._publish_update(step, action, f"Calling {action}({args})")
            if self.on_step:
                try:
                    await self.on_step(self.agent_id, step, action, str(args))
                except Exception:
                    pass

            tool_fn = self.tools.get(action)
            if tool_fn is None:
                # Try skill builder
                if self.skill_builder:
                    obs = self.skill_builder.handle_missing_tool(action, args, self.task)
                    if obs.startswith("SKILL_LOADED:"):
                        new_tool_name = obs.split(":", 1)[1].strip()
                        tool_fn = self.tools.get(new_tool_name)
                if tool_fn is None:
                    observation = f"Tool not found: {action}. Available: {', '.join(self.tools)}"
                    self.history.append({"step": step, "action": action, "args": args, "observation": observation})
                    continue

            # Execute
            try:
                if isinstance(args, dict):
                    observation = await asyncio.to_thread(tool_fn, **args)
                else:
                    observation = await asyncio.to_thread(tool_fn, args)
                observation = str(observation)[:3000]
            except Exception as e:
                observation = f"Tool {action} raised: {e}"
                # Let skill builder try to handle
                if self.skill_builder:
                    fix = self.skill_builder.handle_failure(self.task, str(e), {"action": action, "args": args})
                    if fix:
                        observation += f"\nSkillBuilder: {fix}"

            self.history.append({"step": step, "action": action, "args": args, "observation": observation})

            # Send update directly via websocket if available, else publish to bus
            step_payload = {
                "type":        "agent_update",
                "agent_id":    self.agent_id,
                "step":        step,
                "action":      action,
                "observation": observation[:300],
            }
            if websocket:
                try:
                    await websocket.send_json(step_payload)
                except Exception:
                    pass
            else:
                await self._publish_update(step, action, observation[:500])

        else:
            # max_steps reached
            self.result = f"Max steps ({self.max_steps}) reached. Last observation: {observation}"

        self.status = "done"

        # Save full log
        log = {
            "agent_id": self.agent_id,
            "task":     self.task,
            "result":   self.result,
            "steps":    len(self.history),
            "history":  self.history,
            "finished_at": datetime.now().isoformat(),
        }
        (agent_dir / "result.txt").write_text(f"Task: {self.task}\n\nResult:\n{self.result}\n")
        (agent_dir / "log.json").write_text(json.dumps(log, indent=2))

        await self._publish_update(0, "done", self.result or "")
        return self.result or ""

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _format_history(self) -> str:
        lines = []
        for h in self.history[-10:]:  # last 10 steps to keep context manageable
            action = h.get("action", "?")
            args   = h.get("args", "")
            obs    = h.get("observation", "")[:300]
            lines.append(f"Step {h['step']}: {action}({args}) → {obs}")
        return "\n".join(lines)

    def _parse_action(self, text: str) -> tuple[Optional[str], Any]:
        """Parse ACTION/ARGS from LLM response."""
        action_m = re.search(r'ACTION:\s*(\w+)', text)
        args_m   = re.search(r'ARGS:\s*(\{.*?\})', text, re.DOTALL)
        if not action_m:
            return None, {}
        action = action_m.group(1).strip()
        args = {}
        if args_m:
            try:
                args = json.loads(args_m.group(1))
            except json.JSONDecodeError:
                # Try to extract key-value pairs
                args = {}
        return action, args

    def _call_qwen(self, system_prompt: str, user_prompt: str) -> str:
        import requests
        payload = {
            "model": "qwen",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens":  512,
        }
        resp = requests.post(
            "http://localhost:8081/v1/chat/completions",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    async def _publish_update(self, step: int, action: str, observation: str):
        """Publish AGENT_UPDATE to bus. Best-effort."""
        try:
            import websockets as _ws
            msg = json.dumps({
                "type":       "AGENT_UPDATE",
                "agent_id":   self.agent_id,
                "step":       step,
                "action":     action,
                "observation": observation[:500],
            })
            async with _ws.connect("ws://127.0.0.1:8002", open_timeout=2) as ws:
                await ws.send(json.dumps({"register": f"agent-{self.agent_id}"}))
                await ws.recv()
                await ws.send(msg)
        except Exception:
            pass  # bus may not be running; non-fatal


def create_agent(task: str, agent_id: str = None, **kwargs) -> AgentRuntime:
    """Factory: create an AgentRuntime with the default tool set."""
    from .tools import TOOLS, get_tool_descriptions
    if agent_id is None:
        agent_id = f"AGENT-{int(time.time())}"
    return AgentRuntime(
        task=task,
        agent_id=agent_id,
        tools=TOOLS,
        tool_descriptions=get_tool_descriptions(),
        **kwargs,
    )
