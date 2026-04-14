#!/usr/bin/env python3
"""Hierarchical agent system: Architect (Gemma) + Engineers (Qwen) + Executors (AgentRuntime)."""
import asyncio
import json
import sys
import time
from pathlib import Path

import requests

BRAIN_URL = "http://localhost:8081/v1/chat/completions"   # Gemma 4 31B — single model
# Aliases for internal use
GEMMA_URL = BRAIN_URL
QWEN_URL  = BRAIN_URL


def _call_gemma(prompt: str, max_tokens: int = 500) -> str:
    try:
        r = requests.post(GEMMA_URL, json={
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1, "max_tokens": max_tokens, "stream": False,
        }, timeout=60)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[gemma error: {e}]"


def _call_qwen(prompt: str, max_tokens: int = 800) -> str:
    try:
        r = requests.post(QWEN_URL, json={
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1, "max_tokens": max_tokens, "stream": False,
        }, timeout=60)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[qwen error: {e}]"


async def _send(websocket, data: dict):
    if websocket:
        try:
            await websocket.send(json.dumps(data))
        except Exception:
            pass


class AgentHierarchy:

    async def run(self, task: str, websocket=None) -> str:
        await _send(websocket, {"type": "status", "msg": "[Architect] Analyzing task..."})

        subtasks = await self._architect(task, websocket)

        await _send(websocket, {"type": "status",
                                "msg": f"[Architect] Planning {len(subtasks)} subtasks..."})
        plans = []
        for i, subtask in enumerate(subtasks):
            plan = await asyncio.to_thread(self._engineer, subtask, i)
            plans.append(plan)

        await _send(websocket, {"type": "status", "msg": "[Executors] Running in parallel..."})
        results = await asyncio.gather(*[
            self._executor(plan, i, websocket) for i, plan in enumerate(plans)
        ])

        await _send(websocket, {"type": "status", "msg": "[Reviewer] Synthesizing..."})
        final = await asyncio.to_thread(self._reviewer, task, subtasks, results)

        await _send(websocket, {"type": "final", "msg": final})
        return final

    async def _architect(self, task: str, websocket) -> list:
        prompt = (
            f"Break this task into 2-4 independent parallel subtasks.\n"
            f"Task: {task}\n"
            f"Return JSON only: {{\"subtasks\": [\"subtask 1\", \"subtask 2\"]}}\n"
            f"Each subtask must be independently executable. Maximum 4 subtasks."
        )
        raw = await asyncio.to_thread(_call_gemma, prompt)
        try:
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start != -1 and end > start:
                data = json.loads(raw[start:end])
                subtasks = data.get("subtasks", [])
                if subtasks:
                    return subtasks[:4]
        except Exception:
            pass
        return [task]

    def _engineer(self, subtask: str, idx: int) -> dict:
        prompt = (
            f"Design the implementation for this subtask.\n"
            f"Subtask: {subtask}\n"
            f"Return JSON: {{\"subtask\": \"...\", \"approach\": \"...\", "
            f"\"tools\": [], \"steps\": [], \"output\": \"...\"}}"
        )
        raw = _call_qwen(prompt, max_tokens=400)
        try:
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {"subtask": subtask, "approach": subtask, "tools": [],
                "steps": [subtask], "output": "result"}

    async def _executor(self, plan: dict, idx: int, websocket) -> str:
        agent_id = f"EXEC-{idx + 1}-{int(time.time())}"
        subtask  = plan.get("subtask", plan.get("approach", ""))

        await _send(websocket, {
            "type": "agent_update", "agent_id": agent_id,
            "step": 0, "action": "starting",
            "observation": f"Executor {idx + 1}: {subtask[:60]}",
            "task": subtask,
        })

        try:
            sys.path.insert(0, str(Path.home() / "cowork" / "jarvis"))
            from core.agents.runtime import AgentRuntime
            agent = AgentRuntime(task=subtask, max_steps=20)
            result = await asyncio.wait_for(agent.run(websocket), timeout=300)
            return str(result)[:500]
        except asyncio.TimeoutError:
            return f"[Executor {idx + 1}] Timed out after 300s"
        except Exception as e:
            return f"[Executor {idx + 1}] Error: {e}"

    def _reviewer(self, task: str, subtasks: list, results: list) -> str:
        summary = "\n".join(
            f"- {s[:60]}: {r[:120]}" for s, r in zip(subtasks, results)
        )
        prompt = (
            f"Synthesize these parallel results into a final answer.\n"
            f"Original task: {task}\n\n"
            f"Results:\n{summary}\n\n"
            f"Provide a clear, concise final summary."
        )
        return _call_qwen(prompt, max_tokens=600)


# Wire into router.py — caller adds this trigger block:
HIERARCHY_TRIGGERS = [
    "build a full", "create a complete", "build and launch",
    "build a project", "build an app", "create an app",
    "build a website", "set up a project", "scaffold",
    "build and run", "create and launch", "build me a",
]
