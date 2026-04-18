#!/usr/bin/env python3
"""Autonomous Self-Improvement — runs for N hours, improving the Cowork system.

Triggered by `/improve` in the Command Station or CLI.
The agent can ADD new files and MODIFY non-protected files.
It CANNOT delete or overwrite any core files or UI.
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

COWORK = Path("/Users/ashkansamali/cowork")
BUILD_LOG = COWORK / "self_improve" / "build_log.md"
JARVIS_VENV = COWORK / "jarvis" / ".venv" / "bin" / "python3"

# ── PROTECTED FILES — the agent CANNOT delete or overwrite these ─────────────
PROTECTED_PATHS = {
    # Core backend
    "jarvis/api_server.py",
    "jarvis/core/router.py",
    "jarvis/core/agents/runtime.py",
    "jarvis/core/agents/tools.py",
    "jarvis/core/agents/hierarchy.py",
    "jarvis/core/bus_client.py",
    "jarvis/config.py",
    # Memory (protect existing, allow new)
    "jarvis/core/memory/user_model.py",
    "jarvis/core/memory/onboarding.py",
    "jarvis/core/memory/knowledge_graph.py",
    # UI — entire folders
    "ui/command-station/src/App.jsx",
    "ui/command-station/src/main.jsx",
    "ui/command-station/src/index.css",
    "ui/command-station/preload.js",
    "ui/command-station/main.js",
    "ui/cli/jarvis_cli.py",
    "ui/hud/main.js",
    # Infrastructure
    "start_cowork.sh",
    "cantivia-bus.py",
    "cantivia-cli.py",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str):
    BUILD_LOG.parent.mkdir(parents=True, exist_ok=True)
    with BUILD_LOG.open("a") as f:
        f.write(f"\n[{_now()}] {msg}\n")
    print(f"[IMPROVE] {msg}")


def is_protected(filepath: str) -> bool:
    """Check if a file path is in the protected list."""
    rel = filepath.replace(str(COWORK) + "/", "")
    # Direct match
    if rel in PROTECTED_PATHS:
        return True
    # Component-level protection (all files in UI src dirs)
    for prefix in ["ui/command-station/src/components/", "ui/cli-web/src/"]:
        if rel.startswith(prefix):
            return True
    return False


async def run_improvement(duration_hours: float = 2.0, websocket=None):
    """Main improvement loop. Runs for `duration_hours`."""
    end_time = time.time() + (duration_hours * 3600)
    cycle = 0

    _log(f"=== IMPROVEMENT SESSION STARTED ({duration_hours}h) ===")
    if websocket:
        try:
            await websocket.send_json({
                "type": "status",
                "msg": f"Self-improvement started for {duration_hours} hours..."
            })
        except Exception:
            pass

    sys.path.insert(0, str(COWORK / "jarvis"))

    while time.time() < end_time:
        cycle += 1
        _log(f"--- Cycle {cycle} ---")
        remaining = (end_time - time.time()) / 60
        _log(f"  Time remaining: {remaining:.0f} minutes")

        try:
            # ── Phase 1: AUDIT ────────────────────────────────────────────
            _log("  [AUDIT] Scanning codebase for improvement opportunities...")
            audit_result = await _run_agent(
                "Scan the ~/cowork codebase. Look at the build_log.md, existing code, "
                "and memory files. Identify 3 specific things that could be improved "
                "(e.g., missing error handling, missing features, better prompts, "
                "new tools that could be added). Return a numbered list.",
                max_steps=10
            )
            _log(f"  [AUDIT] Found: {audit_result[:200]}")

            # ── Phase 2: RESEARCH ─────────────────────────────────────────
            _log("  [RESEARCH] Checking latest techniques...")
            research_result = await _run_agent(
                f"Based on these improvement areas: {audit_result[:300]}. "
                f"Use web_search to find the latest best practices for local AI agent "
                f"systems in April 2026. Focus on practical code patterns. "
                f"Return specific implementation approaches.",
                max_steps=8
            )
            _log(f"  [RESEARCH] Findings: {research_result[:200]}")

            # ── Phase 3: BUILD ────────────────────────────────────────────
            _log("  [BUILD] Implementing improvements...")
            build_result = await _run_agent(
                f"Implement one specific improvement in ~/cowork based on: "
                f"{audit_result[:200]}. Research: {research_result[:200]}. "
                f"\nCRITICAL RULES:\n"
                f"1. You can CREATE new files anywhere in ~/cowork.\n"
                f"2. You can MODIFY files that are NOT in the protected list.\n"
                f"3. You CANNOT delete any files.\n"
                f"4. You CANNOT modify these protected files: {', '.join(sorted(list(PROTECTED_PATHS))[:10])}...\n"
                f"5. Focus on adding NEW capabilities, not rewriting existing ones.\n"
                f"6. Write clean, tested code.",
                max_steps=20
            )
            _log(f"  [BUILD] Result: {build_result[:200]}")

            # ── Phase 4: COMMIT ───────────────────────────────────────────
            _log("  [COMMIT] Auto-committing improvements...")
            try:
                subprocess.run(["git", "-C", str(COWORK), "add", "-A"],
                             capture_output=True, check=True)
                commit_msg = f"improve: cycle {cycle} — {audit_result[:50]}"
                subprocess.run(["git", "-C", str(COWORK), "commit", "-m", commit_msg],
                             capture_output=True, check=True)
                _log(f"  [COMMIT] Committed: {commit_msg}")

                # Push to GitHub
                subprocess.run(["git", "-C", str(COWORK), "push"],
                             capture_output=True, timeout=30)
                _log("  [COMMIT] Pushed to GitHub.")
            except Exception as e:
                _log(f"  [COMMIT] Git error (non-fatal): {e}")

            # Status update
            if websocket:
                try:
                    await websocket.send_json({
                        "type": "status",
                        "msg": f"Cycle {cycle} complete. {remaining:.0f}m remaining..."
                    })
                except Exception:
                    pass

        except Exception as e:
            _log(f"  [ERROR] Cycle {cycle} failed: {traceback.format_exc()}")

        # Wait between cycles
        await asyncio.sleep(60)

    _log(f"=== IMPROVEMENT SESSION COMPLETE ({cycle} cycles) ===")
    if websocket:
        try:
            await websocket.send_json({
                "type": "final",
                "msg": f"Self-improvement complete. Ran {cycle} cycles over {duration_hours}h. Check build_log.md for details."
            })
        except Exception:
            pass

    return f"Improvement complete. {cycle} cycles."


async def _run_agent(task: str, max_steps: int = 15) -> str:
    """Spawn an AgentRuntime for a specific improvement task."""
    try:
        from core.agents.runtime import AgentRuntime
        agent = AgentRuntime(task=task, max_steps=max_steps)
        result = await asyncio.wait_for(agent.run(), timeout=300)
        return str(result)[:500]
    except asyncio.TimeoutError:
        return "[Agent timed out after 300s]"
    except Exception as e:
        return f"[Agent error: {e}]"


if __name__ == "__main__":
    hours = 2.0
    if len(sys.argv) > 1:
        try:
            hours = float(sys.argv[1])
        except ValueError:
            pass
    asyncio.run(run_improvement(hours))
