"""
runtime.py — Autonomous AgentRuntime with ReAct loop.

Think → Act → Observe → repeat until FINAL_ANSWER or max_steps.
"""
import asyncio
import importlib.util
import inspect
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Callable

AGENTS_DIR = Path.home() / "cowork" / "agents"

try:
    from .claude_fallback import ask_claude_web
    _CLAUDE_FALLBACK_OK = True
except ImportError:
    _CLAUDE_FALLBACK_OK = False

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

STEP BUDGET:
You have {remaining_steps} steps remaining.
RULES:
- Do web_search MAX 2 times
- Do fetch_url MAX 3 times total
- After 5 steps of research, you MUST synthesize and create the output
- Never fetch the same URL twice
- If a URL returns 403, skip it immediately
- After collecting enough data, call create_keynote_presentation or create_word_document immediately

{force_finish_warning}STEP HISTORY:
{history}

CURRENT OBSERVATION:
{observation}

What is your next action? Choose a tool or provide FINAL_ANSWER.
"""

OUTPUT_TOOLS = {
    "create_keynote_presentation", "create_word_document", "create_document",
    "create_pages_document", "write_file", "speak",
}


class AgentRuntime:
    _global_failure_counts: dict = {}  # task_hash -> int

    def __init__(
        self,
        task: str,
        agent_id: str,
        tools: dict,
        tool_descriptions: str,
        max_steps: int = 30,
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

        # Load persistent skills from skills/ directory
        skills_dir = Path(__file__).parent / "skills"
        if skills_dir.exists():
            for skill_file in skills_dir.glob("skill_*.py"):
                try:
                    spec = importlib.util.spec_from_file_location(skill_file.stem, skill_file)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    for name, func in inspect.getmembers(module, inspect.isfunction):
                        if name.startswith("skill_"):
                            self.tools[name] = func
                            print(f"[Skills] Loaded: {name}")
                except Exception as e:
                    print(f"[Skills] Failed to load {skill_file.name}: {e}")

        # Wire up SkillBuilder if not provided
        if self.skill_builder is None:
            try:
                from core.agents.skill_builder import SkillBuilder
                self.skill_builder = SkillBuilder(tools=self.tools)
            except Exception:
                pass

    async def run(self, websocket=None) -> str:
        self.status = "running"
        self.websocket = websocket

        # Announce agent start immediately so the UI panel shows it
        if websocket:
            try:
                await websocket.send_json({
                    "type": "agent_start",
                    "agent_id": self.agent_id,
                    "task": self.task,
                })
            except Exception:
                pass

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

        # Tracking state for smart step budgeting
        called_tools: set[str] = set()
        completed_tools: set[str] = set()   # output tools that already succeeded
        fetched_urls: set[str] = set()
        web_search_count: int = 0
        fetch_url_count: int = 0

        for step in range(1, self.max_steps + 1):
            # ── THINK ──────────────────────────────────────────────────────────
            print(f"[AGENT {self.agent_id}] STEP {step}/{self.max_steps} — thinking...")
            history_text = self._format_history()
            remaining_steps = self.max_steps - step + 1

            # Build force_finish warning if needed
            force_finish_warning = ""
            output_tool_called = bool(called_tools & OUTPUT_TOOLS)
            if step > 20 and completed_tools:
                # Output already succeeded — stop immediately
                self.result = observation
                self.history.append({"step": step, "action": "FINAL_ANSWER", "observation": self.result})
                await self._publish_update(step, "FINAL_ANSWER", self.result)
                break
            elif step > 20 and not output_tool_called:
                force_finish_warning = (
                    "CRITICAL: You must create the output NOW. "
                    "Stop researching. Call create_keynote_presentation with what you have.\n\n"
                )

            # Inject warnings for exceeded tool limits
            warnings = []
            if web_search_count >= 2:
                warnings.append("WARNING: web_search limit reached (2/2). Do NOT call web_search again.")
            if fetch_url_count >= 3:
                warnings.append("WARNING: fetch_url limit reached (3/3). Do NOT call fetch_url again.")
            if warnings:
                force_finish_warning += "\n".join(warnings) + "\n\n"

            think_prompt = _THINK_USER.format(
                task=self.task,
                remaining_steps=remaining_steps,
                force_finish_warning=force_finish_warning,
                history=history_text or "(none)",
                observation=observation,
            )
            system_prompt = _THINK_SYSTEM.format(tool_descriptions=self.tool_descriptions)

            try:
                combined_prompt = system_prompt + "\n\n" + think_prompt
                llm_response = await asyncio.to_thread(
                    self._think, combined_prompt
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

            # Prevent re-running an output tool that already completed
            if action in completed_tools:
                self.result = f"Task already completed via {action}. {observation}"
                self.history.append({"step": step, "action": "FINAL_ANSWER", "observation": self.result})
                await self._publish_update(step, "FINAL_ANSWER", self.result)
                break

            # ── Duplicate URL guard ─────────────────────────────────────────────
            if action == "fetch_url":
                url_arg = args if isinstance(args, str) else (args.get("url", "") if isinstance(args, dict) else "")
                if url_arg and url_arg in fetched_urls:
                    observation = f"Skipped: URL already fetched: {url_arg}"
                    self.history.append({"step": step, "action": action, "args": args, "observation": observation})
                    continue
                if url_arg:
                    fetched_urls.add(url_arg)
                fetch_url_count += 1

            if action == "web_search":
                web_search_count += 1

            # ── ACT ────────────────────────────────────────────────────────────
            print(f"[AGENT {self.agent_id}] ACT: {action}({args})")
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
            tool_name = action
            try:
                if isinstance(args, dict):
                    observation = await asyncio.to_thread(tool_fn, **args)
                else:
                    observation = await asyncio.to_thread(tool_fn, args)
                observation = str(observation)[:3000]
                called_tools.add(tool_name)
            except Exception as e:
                observation = f"Tool {action} raised: {e}"
                # Let skill builder try to handle the failure
                if self.skill_builder:
                    try:
                        new_skill = await asyncio.to_thread(
                            self.skill_builder.handle_failure, self.task, str(e), {"action": action, "args": args}
                        )
                        if new_skill and isinstance(new_skill, str):
                            observation += f"\nSkillBuilder: {new_skill}"
                        elif new_skill and isinstance(new_skill, dict):
                            from core.agents import tools as tools_module
                            setattr(tools_module, new_skill['name'], new_skill['func'])
                            self.tools[new_skill['name']] = new_skill['func']
                            if 'description' in new_skill:
                                tools_module.TOOL_DESCRIPTIONS[new_skill['name']] = new_skill['description']
                    except Exception as sb_err:
                        pass  # skill builder failure is non-fatal

                # Track failures per task and invoke Claude web fallback after 3rd failure
                task_hash = str(hash(self.task))
                AgentRuntime._global_failure_counts[task_hash] = (
                    AgentRuntime._global_failure_counts.get(task_hash, 0) + 1
                )
                fail_count = AgentRuntime._global_failure_counts[task_hash]
                if fail_count >= 3 and _CLAUDE_FALLBACK_OK:
                    print(f"[Fallback] Asking Claude for help with: {self.task}")
                    try:
                        fallback_context = "\n".join(
                            f"Step {h['step']}: {h['action']} -> {h.get('observation','')[:200]}"
                            for h in self.history[-5:]
                        )
                        claude_answer = await ask_claude_web(
                            problem=f"{self.task} (failed tool: {action}, error: {e})",
                            context=fallback_context,
                        )
                        observation += f"\n[Claude Fallback Answer]: {claude_answer}"
                        # Reset counter so we don't re-trigger on every subsequent step
                        AgentRuntime._global_failure_counts[task_hash] = 0
                    except Exception as fb_err:
                        observation += f"\n[Claude Fallback failed: {fb_err}]"

            print(f"[AGENT {self.agent_id}] OBSERVE: {observation[:200]}")
            self.history.append({"step": step, "action": action, "args": args, "observation": observation})

            # ── Output tool success → end loop immediately ──────────────────
            if tool_name in OUTPUT_TOOLS and not observation.startswith("Tool ") and "Error" not in observation[:100]:
                completed_tools.add(tool_name)
                self._done = True
                self.result = observation
                await self._publish_update(step, "FINAL_ANSWER", observation)
                if websocket:
                    try:
                        await websocket.send_json({
                            "type": "agent_update",
                            "agent_id": self.agent_id,
                            "step": step,
                            "action": "FINAL_ANSWER",
                            "observation": observation[:300],
                            "task": self.task,
                        })
                    except Exception:
                        pass
                break

            # Send update directly via websocket if available, else publish to bus
            step_payload = {
                "type":        "agent_update",
                "agent_id":    self.agent_id,
                "step":        step,
                "action":      action,
                "observation": observation[:300],
                "task":        self.task,
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
        """Parse tool call from LLM response. Handles multiple formats:
          - ACTION: tool_name\nARGS: {"key": "value"}
          - TOOL: tool_name\nARGS: {"key": "value"}
          - ACTION: tool_name\nINPUT: value
          - tool_name({"key": "value"})
          - tool_name("simple string arg")
          - tool_name: simple string arg
        For single-argument tools, unwraps dict to the plain value.
        """
        SINGLE_ARG_TOOLS = {"web_search", "fetch_url", "open_app", "speak",
                            "run_shell", "read_file", "list_dir", "set_clipboard",
                            "spawn_subagent", "focus_app", "recall", "summarize"}

        def _unwrap_single(tool_name: str, args):
            """If tool takes a single arg and args is a 1-key dict, extract the value."""
            if tool_name in SINGLE_ARG_TOOLS and isinstance(args, dict) and len(args) == 1:
                return next(iter(args.values()))
            return args

        # 1. ACTION/TOOL: name  +  ARGS/INPUT: json-or-string
        action_m = re.search(r'(?:ACTION|TOOL):\s*(\w+)', text)
        if action_m:
            action = action_m.group(1).strip()
            # Try ARGS: {...}  (JSON object)
            args_m = re.search(r'ARGS:\s*(\{.*?\})', text, re.DOTALL)
            if args_m:
                try:
                    args = json.loads(args_m.group(1))
                    return action, _unwrap_single(action, args)
                except json.JSONDecodeError:
                    pass
            # Try ARGS: <plain string>  (non-JSON)
            args_plain_m = re.search(r'ARGS:\s*(.+)', text)
            if args_plain_m:
                args_str = args_plain_m.group(1).strip()
                # Try json.loads first; if it fails, use the raw string
                try:
                    args = json.loads(args_str)
                    return action, _unwrap_single(action, args)
                except (json.JSONDecodeError, ValueError):
                    return action, args_str
            # Try INPUT: value
            input_m = re.search(r'INPUT:\s*(.+)', text)
            if input_m:
                val = input_m.group(1).strip()
                # Try to parse as JSON
                try:
                    args = json.loads(val)
                    return action, _unwrap_single(action, args)
                except (json.JSONDecodeError, ValueError):
                    return action, val
            return action, {}

        # 2. tool_name({"key": "value"})  or  tool_name("string")
        call_m = re.search(r'(\w+)\s*\(\s*(.*?)\s*\)\s*$', text, re.DOTALL)
        if call_m:
            action = call_m.group(1).strip()
            raw    = call_m.group(2).strip()
            if raw:
                # Try JSON object
                try:
                    args = json.loads(raw)
                    return action, _unwrap_single(action, args)
                except (json.JSONDecodeError, ValueError):
                    pass
                # Try quoted string
                if (raw.startswith('"') and raw.endswith('"')) or \
                   (raw.startswith("'") and raw.endswith("'")):
                    return action, raw[1:-1]
                return action, raw
            return action, {}

        # 3. tool_name: simple string arg  (no parens)
        colon_m = re.match(r'(\w+)\s*:\s*(.+)', text.strip())
        if colon_m:
            action = colon_m.group(1).strip()
            val    = colon_m.group(2).strip()
            # Only treat as tool call if action is a known keyword-free identifier
            if action not in ("FINAL_ANSWER", "OBSERVE", "THOUGHT", "THINK"):
                try:
                    args = json.loads(val)
                    return action, _unwrap_single(action, args)
                except (json.JSONDecodeError, ValueError):
                    return action, val

        return None, {}

    def _think(self, prompt: str) -> str:
        """Call local Qwen for ReAct Think steps (tool selection).
        Retries once on failure; falls back to a simpler prompt on second failure.
        """
        import requests

        def _call(p: str) -> str:
            r = requests.post("http://localhost:8081/v1/chat/completions", json={
                "messages": [{"role": "user", "content": p}],
                "temperature": 0.1,
                "max_tokens": 500
            }, timeout=120)
            return r.json()["choices"][0]["message"]["content"].strip()

        # First attempt
        try:
            return _call(prompt)
        except Exception as first_err:
            pass  # fall through to retry

        # Retry with same prompt
        try:
            return _call(prompt)
        except Exception:
            pass  # fall through to fallback

        # Fallback: simpler prompt
        tool_list = ", ".join(self.tools.keys())
        fallback_prompt = (
            f"You are helping with the task: {self.task}. "
            f"Available tools: {tool_list}. "
            "What single action should be taken next? "
            "Reply with TOOL: <name> ARGS: <args> or FINAL: <answer>"
        )
        try:
            return _call(fallback_prompt)
        except Exception as final_err:
            raise RuntimeError(
                f"_think failed after retry and fallback: {final_err}"
            ) from final_err

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
