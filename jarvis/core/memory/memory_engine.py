#!/usr/bin/env python3
import json
import os
import requests
from pathlib import Path

EPISODES_PATH = Path(os.path.expanduser("~/cowork/jarvis/memory/episodes.json"))
E4B_URL = "http://localhost:8080/v1/chat/completions"

class MemoryEngine:
    def __init__(self, user_model):
        self.user_model = user_model
        EPISODES_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.last_extracted_keys = []

    def _load_episodes(self) -> list:
        if EPISODES_PATH.exists():
            try:
                return json.loads(EPISODES_PATH.read_text())
            except Exception:
                pass
        return []

    def _save_episodes(self, episodes: list):
        EPISODES_PATH.write_text(json.dumps(episodes, indent=2))

    def _get_episode_limit(self):
        return 200

    def forget_last(self) -> str:
        if not self.last_extracted_keys:
            return "No recently extracted facts to forget."
        forgotten = []
        for cat, key in self.last_extracted_keys:
            if self.user_model.forget(key):
                forgotten.append(f"{cat}: {key}")
        self.last_extracted_keys = []
        return f"Forgot: {', '.join(forgotten)}" if forgotten else "Could not find last fact to forget."

    def store_episode(self, user_turn: str, jarvis_response: str):
        episodes = self._load_episodes()
        episodes.append({
            "user": user_turn,
            "jarvis": jarvis_response
        })
        if len(episodes) > self._get_episode_limit():
            episodes = episodes[-self._get_episode_limit():]
        self._save_episodes(episodes)
        self._detect_habits(episodes)

    def _detect_habits(self, episodes: list):
        # A naive heuristic for habits using phrase repetition
        requests = [e["user"].lower() for e in episodes]
        counts = {}
        for req in requests:
            counts[req] = counts.get(req, 0) + 1
            if counts[req] == 3:
                # Add to habits
                self.user_model.update("habits", req, f"User frequently asks: {req}")

    def extract_and_store(self, user_turn: str, jarvis_response: str):
        # Store rolling turns
        self.store_episode(user_turn, jarvis_response)

        prompt = (
            "Extract any facts about the user from this conversation turn. "
            "Return JSON only: {\"facts\": [{\"category\": \"...\", \"key\": \"...\", \"value\": \"...\"}]}. "
            "Categories can be: identity, preferences, projects, habits, goals, relationships, raw_facts.\n"
            "If nothing new, return {\"facts\": []}.\n\n"
            f"Conversation:\nUser: {user_turn}\nJarvis: {jarvis_response}"
        )
        try:
            resp = requests.post(E4B_URL, json={
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1, "max_tokens": 300, "stream": False
            }, timeout=20)
            
            raw = resp.json()["choices"][0]["message"]["content"]
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                data = json.loads(raw[start:end])
                new_keys = []
                for fact in data.get("facts", []):
                    cat = fact.get("category", "raw_facts")
                    key = fact.get("key", "")
                    val = fact.get("value", "")
                    if cat and key and val:
                        self.user_model.update(cat, key, val)
                        new_keys.append((cat, key))
                if new_keys:
                    self.last_extracted_keys = new_keys
        except Exception as e:
            print(f"[MemoryEngine] Failed to extract facts: {e}")
