"""
agent_manager.py — Background agent manager for Jarvis.

Agents run as asyncio tasks. Each agent can perform web research,
run shell commands, or handle general tasks. Results are saved to
~/cowork/agents/[agent_id]/result.txt.
"""

import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

AGENTS_DIR = Path.home() / "cowork" / "agents"

# Agent statuses
PENDING = "pending"
RUNNING = "running"
DONE    = "done"
FAILED  = "failed"


class AgentManager:
    def __init__(self):
        self._agents: dict[str, dict] = {}  # id → {task, status, result, asyncio_task}

    def spawn(self, task: str, agent_id: str) -> str:
        """Spawn a background agent for the given task. Returns agent_id."""
        if agent_id in self._agents:
            return agent_id

        self._agents[agent_id] = {
            "task":   task,
            "status": PENDING,
            "result": None,
            "started_at": datetime.now().isoformat(),
            "asyncio_task": None,
        }

        loop = asyncio.get_event_loop()
        t = loop.create_task(self._run_agent(agent_id, task))
        self._agents[agent_id]["asyncio_task"] = t
        return agent_id

    def get_status(self, agent_id: str) -> Optional[dict]:
        info = self._agents.get(agent_id)
        if not info:
            return None
        return {
            "id":     agent_id,
            "task":   info["task"],
            "status": info["status"],
            "result": info["result"],
        }

    def get_all_statuses(self) -> list[dict]:
        return [
            {
                "id":     aid,
                "task":   info["task"],
                "status": info["status"],
                "result": info["result"],
            }
            for aid, info in self._agents.items()
        ]

    def cancel(self, agent_id: str) -> bool:
        info = self._agents.get(agent_id)
        if not info:
            return False
        t = info.get("asyncio_task")
        if t and not t.done():
            t.cancel()
        info["status"] = FAILED
        return True

    async def _run_agent(self, agent_id: str, task: str):
        self._agents[agent_id]["status"] = RUNNING
        await _publish_agent_status(agent_id, RUNNING, f"Starting task: {task[:80]}")
        try:
            task_lower = task.lower()

            if _is_research_task(task_lower):
                query = _extract_research_query(task)
                result = await _research(query)
            else:
                result = f"Agent {agent_id} received task: {task}\n(No handler matched — general task noted.)"

            self._agents[agent_id]["status"] = DONE
            self._agents[agent_id]["result"] = result
            _save_result(agent_id, task, result)
            await _publish_agent_status(agent_id, DONE, result[:200])

        except asyncio.CancelledError:
            self._agents[agent_id]["status"] = FAILED
            _save_result(agent_id, task, "Agent cancelled.")
            await _publish_agent_status(agent_id, FAILED, "Agent cancelled.")
        except Exception as exc:
            self._agents[agent_id]["status"] = FAILED
            self._agents[agent_id]["result"] = str(exc)
            _save_result(agent_id, task, f"Error: {exc}")
            await _publish_agent_status(agent_id, FAILED, str(exc)[:200])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _publish_agent_status(agent_id: str, status: str, message: str):
    """Best-effort publish of AGENT_STATUS to the cantivia bus."""
    try:
        import websockets as _ws
        async with _ws.connect("ws://127.0.0.1:8002") as ws:
            await ws.send(json.dumps({"register": "agent-manager"}))
            await ws.recv()  # consume the ack
            await ws.send(json.dumps({
                "type": "AGENT_STATUS",
                "agent_id": agent_id,
                "status": status,
                "message": message,
            }))
    except Exception:
        pass  # bus may not be running; non-fatal

def _is_research_task(task_lower: str) -> bool:
    return any(kw in task_lower for kw in ("research", "find out", "look up", "search for", "what is", "who is"))


def _extract_research_query(task: str) -> str:
    for prefix in ("research ", "look up ", "find out about ", "search for ", "find "):
        if task.lower().startswith(prefix):
            return task[len(prefix):]
    return task


async def _research(query: str) -> str:
    """Search DuckDuckGo and return a summary of the top results."""
    import requests

    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    params = {"q": query}

    try:
        resp = await asyncio.to_thread(
            lambda: requests.get(url, params=params, headers=headers, timeout=10)
        )
        resp.raise_for_status()
        html = resp.text

        # Extract result snippets from DuckDuckGo HTML
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
        titles   = re.findall(r'class="result__title"[^>]*>.*?<a[^>]*>(.*?)</a>', html, re.DOTALL)

        def clean(s):
            return re.sub(r'<[^>]+>', '', s).strip()

        lines = [f"Research results for: {query}\n"]
        for i, (title, snippet) in enumerate(zip(titles[:5], snippets[:5]), 1):
            lines.append(f"{i}. {clean(title)}")
            lines.append(f"   {clean(snippet)}\n")

        if not lines[1:]:
            return f"No results found for: {query}"

        return "\n".join(lines)

    except Exception as e:
        return f"Research failed for '{query}': {e}"


def _save_result(agent_id: str, task: str, result: str):
    out_dir = AGENTS_DIR / agent_id
    out_dir.mkdir(parents=True, exist_ok=True)
    result_file = out_dir / "result.txt"
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    result_file.write_text(
        f"Agent: {agent_id}\nTask: {task}\nTimestamp: {ts}\n\n{result}\n"
    )


# ── Module-level singleton ────────────────────────────────────────────────────
_manager: Optional[AgentManager] = None


def get_manager() -> AgentManager:
    global _manager
    if _manager is None:
        _manager = AgentManager()
    return _manager
