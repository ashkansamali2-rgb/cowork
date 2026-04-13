#!/usr/bin/env python3
"""Web learning pipeline — Jarvis learns from the web daily."""
import asyncio
import json
import re
import time
from datetime import datetime, date
from pathlib import Path

import requests

COWORK        = Path("/Users/ashkansamali/cowork")
KNOWLEDGE_DIR = COWORK / "jarvis" / "knowledge"
BUILD_LOG     = COWORK / "self_improve" / "build_log.md"
PROBLEMS_FILE = COWORK / "self_improve" / "problems.json"
LAST_LEARN    = COWORK / "self_improve" / "last_learn_date.txt"
QWEN_URL      = "http://localhost:8081/v1/chat/completions"

TOPICS = [
    "local LLM inference optimization Apple Silicon",
    "FastAPI WebSocket performance tips",
    "aider coding agent best practices",
    "Whisper STT speed optimization",
    "python-pptx advanced presentations",
    "pyautogui Mac automation tips",
    "mediapipe hand detection performance",
    "Electron app memory optimization",
]


def _slug(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")


def _log(msg: str):
    BUILD_LOG.parent.mkdir(parents=True, exist_ok=True)
    with BUILD_LOG.open("a") as f:
        f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [WebLearner] {msg}\n")
    print(f"[WebLearner] {msg}")


def _qwen(prompt: str) -> str:
    try:
        r = requests.post(QWEN_URL, json={
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2, "max_tokens": 800, "stream": False,
        }, timeout=30)
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[qwen error: {e}]"


def _ddg_search(query: str) -> list[str]:
    """DuckDuckGo search, return list of result URLs."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=4))
        return [r["href"] for r in results if r.get("href")]
    except Exception as e:
        _log(f"DDG search failed: {e}")
        return []


def _fetch_url(url: str, max_chars: int = 4000) -> str:
    """Fetch URL text content."""
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 403:
            return ""
        # Strip HTML tags roughly
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception:
        return ""


class WebLearner:

    async def learn_topic(self, topic: str) -> str:
        _log(f"Learning: {topic}")
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

        urls = _ddg_search(topic)
        fetched = []
        for url in urls[:4]:
            content = _fetch_url(url)
            if content and len(content) > 200:
                fetched.append(content[:2000])
            if len(fetched) >= 2:
                break

        if not fetched:
            _log(f"No content found for: {topic}")
            return ""

        combined = "\n\n---\n\n".join(fetched)
        summary_prompt = (
            f"Summarize the key technical insights about: {topic}\n\n"
            f"Focus on practical tips, best practices, and optimization techniques. "
            f"Format as structured markdown with sections.\n\n"
            f"Source content:\n{combined[:4000]}"
        )
        summary = _qwen(summary_prompt)

        # Save to knowledge base
        slug     = _slug(topic)
        out_path = KNOWLEDGE_DIR / f"{slug}.md"
        out_path.write_text(
            f"# {topic}\n\n*Learned: {datetime.now().strftime('%Y-%m-%d')}*\n\n{summary}"
        )
        _log(f"Saved: {out_path}")

        # Check if learning reveals improvement opportunities
        check_prompt = (
            f"Based on this summary about '{topic}', list any specific improvements "
            f"that could be applied to a local AI system (jarvis). "
            f"Return JSON array: [{{\"description\": \"...\", \"file\": \"path/to/file.py\"}}] "
            f"or empty array [] if none.\n\n{summary[:2000]}"
        )
        raw = _qwen(check_prompt)
        try:
            start = raw.find("[")
            end   = raw.rfind("]") + 1
            if start != -1 and end > start:
                improvements = json.loads(raw[start:end])
                if improvements and PROBLEMS_FILE.exists():
                    problems = json.loads(PROBLEMS_FILE.read_text())
                    max_id   = max((p.get("id", 0) for p in problems), default=0)
                    for imp in improvements[:2]:
                        max_id += 1
                        problems.append({
                            "id": max_id,
                            "description": imp.get("description", ""),
                            "file": imp.get("file", ""),
                            "priority": "low",
                            "attempts": 0,
                            "status": "open",
                            "source": "web_learner",
                        })
                    PROBLEMS_FILE.write_text(json.dumps(problems, indent=2))
                    _log(f"Added {len(improvements[:2])} improvement ideas from learning.")
        except Exception:
            pass

        return summary

    async def daily_learning(self):
        """Pick one topic per day (rotate) and learn it."""
        today = str(date.today())
        if LAST_LEARN.exists() and LAST_LEARN.read_text().strip() == today:
            _log("Already learned today. Skipping.")
            return

        # Pick topic based on day of year
        topic_idx = date.today().timetuple().tm_yday % len(TOPICS)
        topic     = TOPICS[topic_idx]
        await self.learn_topic(topic)

        LAST_LEARN.parent.mkdir(parents=True, exist_ok=True)
        LAST_LEARN.write_text(today)
        _log(f"Daily learning complete: {topic}")


if __name__ == "__main__":
    import sys
    topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    learner = WebLearner()
    if topic:
        asyncio.run(learner.learn_topic(topic))
    else:
        asyncio.run(learner.daily_learning())
