#!/usr/bin/env python3
"""Self-improvement daemon — runs continuously, picks problems and attempts fixes."""
import asyncio
import json
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

COWORK = Path("/Users/ashkansamali/cowork")
PROBLEMS_FILE = COWORK / "self_improve" / "problems.json"
BUILD_LOG     = COWORK / "self_improve" / "build_log.md"
TEST_SUITE    = COWORK / "self_improve" / "test_suite.py"
JARVIS_VENV   = COWORK / "jarvis" / ".venv" / "bin" / "python3"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str):
    BUILD_LOG.parent.mkdir(parents=True, exist_ok=True)
    with BUILD_LOG.open("a") as f:
        f.write(f"\n[{_now()}] {msg}\n")
    print(f"[SelfImprove] {msg}")


def _load_problems() -> list:
    if not PROBLEMS_FILE.exists():
        return []
    return json.loads(PROBLEMS_FILE.read_text())


def _save_problems(problems: list):
    PROBLEMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROBLEMS_FILE.write_text(json.dumps(problems, indent=2))


def pick_next_problem(problems: list) -> dict | None:
    open_problems = [p for p in problems if p.get("status") != "resolved" and p.get("attempts", 0) < 3]
    if not open_problems:
        return None
    return sorted(open_problems, key=lambda p: (p.get("attempts", 0), 0 if p.get("priority") == "high" else 1))[0]


def _run_tests() -> bool:
    try:
        r = subprocess.run(
            [str(JARVIS_VENV), str(TEST_SUITE)],
            capture_output=True, text=True, timeout=120
        )
        _log(f"Test output:\n{r.stdout[-1000:]}")
        return r.returncode == 0
    except Exception as e:
        _log(f"Test suite error: {e}")
        return False


async def attempt_fix(problem: dict) -> bool:
    _log(f"Attempting fix for: {problem['description']} (attempt {problem['attempts'] + 1})")

    file_path = COWORK / problem["file"]
    if not file_path.exists():
        _log(f"  File not found: {file_path}")
        return False

    try:
        sys.path.insert(0, str(COWORK / "jarvis"))
        from core.agents.runtime import AgentRuntime

        task = (
            f"Fix this problem in {problem['file']}: {problem['description']}. "
            f"Read the file first, identify the root cause, and apply a minimal targeted fix. "
            f"Do not rewrite the whole file. Only fix the specific issue."
        )
        agent = AgentRuntime(task=task, max_steps=15)
        result = await asyncio.wait_for(agent.run(), timeout=300)
        _log(f"  Agent result: {str(result)[:200]}")
    except Exception as e:
        _log(f"  Agent failed: {e}")
        return False

    # Run tests
    passed = _run_tests()
    if passed:
        _log(f"  Tests PASSED after fix for: {problem['description']}")
        # Commit
        try:
            subprocess.run(["git", "-C", str(COWORK), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(COWORK), "commit", "-m",
                          f"fix: {problem['description']} (self-improve daemon)"], check=True)
            _log("  Committed fix.")
        except Exception as e:
            _log(f"  Commit failed: {e}")
    else:
        _log(f"  Tests FAILED after fix attempt.")

    return passed


async def run_forever():
    _log("Self-improve daemon started.")
    while True:
        try:
            problems = _load_problems()
            problem = pick_next_problem(problems)

            if problem:
                success = await attempt_fix(problem)
                # Update problem state
                for p in problems:
                    if p["id"] == problem["id"]:
                        p["attempts"] = p.get("attempts", 0) + 1
                        if success:
                            p["status"] = "resolved"
                        elif p["attempts"] >= 3:
                            p["status"] = "needs_claude"
                            _log(f"  Problem {p['id']} needs Claude fallback after 3 failures.")
                _save_problems(problems)
            else:
                _log("No open problems. Sleeping 30 minutes.")
        except Exception as e:
            _log(f"Daemon error: {traceback.format_exc()}")

        await asyncio.sleep(300)


if __name__ == "__main__":
    asyncio.run(run_forever())
