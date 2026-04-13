#!/usr/bin/env python3
"""Long-term memory system for Jarvis."""
import json
import re
from datetime import datetime
from pathlib import Path

import requests

DB_PATH  = Path("/Users/ashkansamali/cowork/jarvis/memory/long_term.json")
QWEN_URL = "http://localhost:8081/v1/chat/completions"


class LongTermMemory:

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        if DB_PATH.exists():
            try:
                return json.loads(DB_PATH.read_text())
            except Exception:
                pass
        return {}

    def _save(self, memories: dict):
        DB_PATH.write_text(json.dumps(memories, indent=2))

    def remember(self, key: str, value: str, category: str = "general"):
        memories = self._load()
        memories[key] = {
            "value": value,
            "category": category,
            "timestamp": datetime.now().isoformat(),
            "access_count": memories.get(key, {}).get("access_count", 0),
        }
        self._save(memories)

    def recall(self, query: str) -> list[dict]:
        memories = self._load()
        results  = []
        ql = query.lower()
        for key, mem in memories.items():
            if ql in key.lower() or ql in mem.get("value", "").lower():
                mem["access_count"] = mem.get("access_count", 0) + 1
                results.append({"key": key, **mem})
        self._save(memories)
        return sorted(results, key=lambda x: x.get("access_count", 0), reverse=True)[:5]

    def get_all(self) -> dict:
        return self._load()

    def forget(self, key: str) -> bool:
        memories = self._load()
        if key in memories:
            del memories[key]
            self._save(memories)
            return True
        return False

    def summarize_and_store(self, messages: list[dict]):
        """Extract key facts from recent messages and store as memories."""
        if not messages:
            return
        text = "\n".join(f"{m.get('role','?')}: {m.get('content','')}" for m in messages[-10:])
        prompt = (
            f"Extract key facts, preferences, and tasks from this conversation. "
            f"Return a JSON object where each key is a short label and value is the fact.\n\n"
            f"{text}\n\nReturn ONLY valid JSON object."
        )
        try:
            resp = requests.post(QWEN_URL, json={
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1, "max_tokens": 400, "stream": False,
            }, timeout=20)
            raw  = resp.json()["choices"][0]["message"]["content"]
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start != -1 and end > start:
                facts = json.loads(raw[start:end])
                for k, v in facts.items():
                    self.remember(str(k), str(v), category="auto")
        except Exception:
            pass

    def get_relevant(self, query: str, top_n: int = 3) -> list[str]:
        """Return top_n relevant memories as formatted strings."""
        results = self.recall(query)[:top_n]
        return [f"{r['key']}: {r['value']}" for r in results]
