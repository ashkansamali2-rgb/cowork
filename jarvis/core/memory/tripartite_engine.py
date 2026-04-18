#!/usr/bin/env python3
"""Tripartite Memory Engine — merged from V2/V3 research.

Three tiers:
  1. Episodic (short-term): Raw conversation turns, last 50
  2. Summary (mid-term): Compressed summaries of older episodes
  3. Semantic (long-term): Extracted facts in user_model + salience scores
"""
import json
import os
import requests
from pathlib import Path
from datetime import datetime

MEMORY_DIR = Path(os.path.expanduser("~/cowork/jarvis/memory"))
EPISODES_PATH = MEMORY_DIR / "episodes.json"
SUMMARIES_PATH = MEMORY_DIR / "summaries.json"

BRAIN_URL = "http://localhost:8081/v1/chat/completions"


class TripartiteEngine:
    def __init__(self, user_model):
        self.user_model = user_model
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self.episodes = self._load(EPISODES_PATH, [])
        self.summaries = self._load(SUMMARIES_PATH, [])

    # ── Persistence ───────────────────────────────────────────────────────────
    @staticmethod
    def _load(path: Path, default):
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                return default
        return default

    @staticmethod
    def _save(path: Path, data):
        path.write_text(json.dumps(data, indent=2))

    # ── Tier 1: Episodic ──────────────────────────────────────────────────────
    def store_episode(self, user_turn: str, jarvis_response: str):
        self.episodes.append({
            "ts": datetime.now().isoformat(),
            "user": user_turn,
            "jarvis": jarvis_response,
            "salience": self._score_salience(user_turn),
        })
        # Compress oldest episodes into summaries when buffer > 50
        if len(self.episodes) > 50:
            self._compress_oldest()
        self._save(EPISODES_PATH, self.episodes)
        # Also extract semantic facts
        self.extract_and_store(user_turn, jarvis_response)

    def _score_salience(self, text: str) -> float:
        """Quick heuristic salience score (0-1). Higher = more important."""
        score = 0.3  # baseline
        important_signals = [
            "remember", "important", "always", "never", "preference",
            "project", "build", "deadline", "password", "key", "secret",
        ]
        for signal in important_signals:
            if signal in text.lower():
                score += 0.15
        return min(score, 1.0)

    # ── Tier 2: Summaries ─────────────────────────────────────────────────────
    def _compress_oldest(self):
        """Compress the 20 oldest episodes into a single summary."""
        to_compress = self.episodes[:20]
        self.episodes = self.episodes[20:]

        text_block = "\n".join(
            f"U: {e['user']}\nJ: {e['jarvis']}" for e in to_compress
        )
        try:
            resp = requests.post(BRAIN_URL, json={
                "messages": [{"role": "user", "content":
                    f"Summarize these conversations into 3-5 bullet points of key facts:\n{text_block}"}],
                "temperature": 0.1, "max_tokens": 300, "stream": False,
            }, timeout=30)
            summary_text = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            summary_text = f"[{len(to_compress)} episodes compressed, extraction failed]"

        self.summaries.append({
            "ts": datetime.now().isoformat(),
            "period": f"{to_compress[0]['ts']} → {to_compress[-1]['ts']}",
            "summary": summary_text,
        })
        self._save(SUMMARIES_PATH, self.summaries)

    # ── Tier 3: Semantic Extraction ───────────────────────────────────────────
    def extract_and_store(self, user_turn: str, jarvis_response: str):
        prompt = (
            "Extract permanent facts about the user. JSON only: "
            "{\"facts\": [{\"category\": \"...\", \"key\": \"...\", \"value\": \"...\"}]}.\n\n"
            f"User: {user_turn}\nJarvis: {jarvis_response}"
        )
        try:
            resp = requests.post(BRAIN_URL, json={
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1, "max_tokens": 300,
            }, timeout=10)
            raw = resp.json()["choices"][0]["message"]["content"]
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            data = json.loads(raw)
            for fact in data.get("facts", []):
                self.user_model.update(
                    fact.get("category", "raw_facts"),
                    fact.get("key", "misc"),
                    fact.get("value", ""),
                )
        except Exception:
            pass  # Non-critical

    # ── Retrieval ─────────────────────────────────────────────────────────────
    def get_context(self, query: str = "") -> str:
        profile = self.user_model.get_profile_summary()
        recent = self.episodes[-3:]
        recent_str = "\n".join(f"U: {e['user']}\nJ: {e['jarvis']}" for e in recent)
        summary_str = "\n".join(s["summary"] for s in self.summaries[-3:])
        return (
            f"USER PROFILE:\n{profile}\n\n"
            f"RECENT MEMORY:\n{recent_str}\n\n"
            f"COMPRESSED HISTORY:\n{summary_str}"
        )

    def forget_last(self) -> str:
        if self.episodes:
            self.episodes.pop()
            self._save(EPISODES_PATH, self.episodes)
            return "Last memory forgotten."
        return "Nothing to forget."
