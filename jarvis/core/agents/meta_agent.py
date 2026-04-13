#!/usr/bin/env python3
"""Meta Agent Director — analyzes system state and spawns improvement agents."""
import asyncio
import json
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

import requests

COWORK       = Path("/Users/ashkansamali/cowork")
BUILD_LOG    = COWORK / "self_improve" / "build_log.md"
PROBLEMS_FILE = COWORK / "self_improve" / "problems.json"
TEST_SUITE   = COWORK / "self_improve" / "test_suite.py"
JARVIS_VENV  = COWORK / "jarvis" / ".venv" / "bin" / "python3"
QWEN_URL     = "http://localhost:8081/v1/chat/completions"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str):
    BUILD_LOG.parent.mkdir(parents=True, exist_ok=True)
    with BUILD_LOG.open("a") as f:
        f.write(f"\n[{_now()}] [MetaAgent] {msg}\n")
    print(f"[MetaAgent] {msg}")


def _qwen(prompt: str, max_tokens: int = 800) -> str:
    try:
        resp = requests.post(QWEN_URL, json={
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "stream": False,
        }, timeout=30)
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[qwen error: {e}]"


class MetaAgent:

    async def analyze_system(self) -> list:
        """Read logs and problems, ask Qwen what to improve next."""
        build_log = BUILD_LOG.read_text()[-3000:] if BUILD_LOG.exists() else "(no log)"
        problems  = json.loads(PROBLEMS_FILE.read_text()) if PROBLEMS_FILE.exists() else []
        open_p    = [p for p in problems if p.get("status") != "resolved"]

        prompt = f"""Analyze this build log and open problems for a local macOS AI system.
Return a JSON array of up to 3 improvement tasks, prioritized by impact.
Each item: {{"task": "description", "file": "path/to/file.py", "priority": "high/medium"}}

Build log (recent):
{build_log[-2000:]}

Open problems:
{json.dumps(open_p, indent=2)}

Return ONLY valid JSON array."""

        raw = _qwen(prompt, max_tokens=400)
        try:
            # Extract JSON array from response
            start = raw.find("[")
            end   = raw.rfind("]") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return []

    async def spawn_improvement(self, task: str) -> bool:
        """Spawn an AgentRuntime to implement one improvement task."""
        _log(f"Spawning improvement agent: {task}")
        try:
            sys.path.insert(0, str(COWORK / "jarvis"))
            from core.agents.runtime import AgentRuntime
            agent = AgentRuntime(task=task, max_steps=20)
            await asyncio.wait_for(agent.run(), timeout=600)
            _log(f"Agent completed: {task[:80]}")
            return True
        except Exception as e:
            _log(f"Agent failed: {e}")
            return False

    def _run_tests(self) -> bool:
        try:
            r = subprocess.run(
                [str(JARVIS_VENV), str(TEST_SUITE)],
                capture_output=True, text=True, timeout=120
            )
            _log(f"Tests: {'PASSED' if r.returncode == 0 else 'FAILED'}")
            if r.stdout:
                _log(r.stdout[-500:])
            return r.returncode == 0
        except Exception as e:
            _log(f"Test error: {e}")
            return False

    async def run_build_session(self, duration_minutes: int = 60):
        """Run autonomous improvement cycles for the specified duration."""
        import time
        deadline = time.time() + duration_minutes * 60
        cycle    = 0

        _log(f"Build session started ({duration_minutes} min)")

        while time.time() < deadline:
            cycle += 1
            _log(f"--- Cycle {cycle} ---")

            try:
                improvements = await self.analyze_system()
                if not improvements:
                    _log("No improvements identified. Sleeping 5 min.")
                    await asyncio.sleep(300)
                    continue

                task_item = improvements[0]
                task_desc = task_item.get("task", str(task_item))
                _log(f"Selected: {task_desc}")

                success = await self.spawn_improvement(task_desc)

                if success and self._run_tests():
                    try:
                        subprocess.run(["git", "-C", str(COWORK), "add", "-A"])
                        msg = f"feat: {task_desc[:60]} (meta agent cycle {cycle})"
                        subprocess.run(["git", "-C", str(COWORK), "commit", "-m", msg])
                        _log(f"Committed: {msg}")
                    except Exception as e:
                        _log(f"Commit failed: {e}")
                else:
                    _log("Reverting changes.")
                    subprocess.run(["git", "-C", str(COWORK), "checkout", "--", "."])

            except Exception as e:
                _log(f"Cycle error: {traceback.format_exc()}")

            await asyncio.sleep(60)

        _log(f"Build session complete after {cycle} cycles.")
        return cycle
