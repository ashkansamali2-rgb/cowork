import asyncio, json, os, subprocess, sys, time, requests
from pathlib import Path
from datetime import datetime, timedelta
import ast

COWORK = Path("/Users/ashkansamali/cowork")
LOG = COWORK / "self_improve/nightly_log.md"
TOPICS = [
    "Python asyncio performance 2025",
    "local LLM inference Apple Silicon optimization",
    "aider coding agent best practices",
    "FastAPI WebSocket reliability",
    "Whisper STT speed tricks",
]

def log(msg: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {msg}"
    with open(LOG, "a") as f:
        f.write(entry)
    print(f"[Nightly]{entry}")

def run_syntax_checks() -> bool:
    for f in COWORK.rglob("*.py"):
        if any(x in str(f) for x in [".venv", "node_modules", "__pycache__"]):
            continue
        try:
            ast.parse(f.read_text())
        except SyntaxError as e:
            log(f"SYNTAX ERROR {f.name}: {e}")
            return False
    return True

def check_services() -> list[str]:
    import socket
    results = []
    for port, name in [(8001, "Jarvis"), (8002, "Bus"), (8081, "Gemma31B")]:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=2)
            s.close()
            results.append(f"{name}:UP")
        except:
            results.append(f"{name}:DOWN")
    return results

async def learn_topic(topic: str) -> str:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(topic, max_results=2))
        text = "\n\n".join(r.get("body", "") for r in results)[:3000]
        r = requests.post("http://localhost:8081/v1/chat/completions", json={
            "messages": [{"role": "user", "content": f"Give 3 specific actionable tips from this about {topic}:\n{text}"}],
            "temperature": 0.1, "max_tokens": 300, "stream": False
        }, timeout=45)
        summary = r.json()["choices"][0]["message"]["content"].strip()
        knowledge_dir = COWORK / "jarvis/knowledge"
        knowledge_dir.mkdir(exist_ok=True)
        slug = topic.replace(" ", "_")[:40]
        (knowledge_dir / f"{slug}.md").write_text(f"# {topic}\n\n{summary}\n")
        return summary[:150]
    except Exception as e:
        return f"learn failed: {e}"

async def attempt_fix(problem: dict) -> bool:
    sys.path.insert(0, str(COWORK / "jarvis"))
    from core.agents.runtime import create_agent

    subprocess.run(["git", "stash"], cwd=COWORK, capture_output=True)
    try:
        agent = create_agent(
            f"Fix this issue with minimal changes: {problem['description']} in {problem['file']}. Read the file first. Do not break other functionality.",
            agent_id=f"NIGHT-{int(time.time())}"
        )
        await asyncio.wait_for(agent.run(None), timeout=180)

        if not run_syntax_checks():
            subprocess.run(["git", "stash", "pop"], cwd=COWORK, capture_output=True)
            return False

        subprocess.run(["git", "stash", "drop"], cwd=COWORK, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=COWORK, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"nightly-fix: {problem['description'][:50]}"],
                      cwd=COWORK, capture_output=True)
        return True
    except Exception as e:
        log(f"attempt_fix error: {e}")
        subprocess.run(["git", "stash", "pop"], cwd=COWORK, capture_output=True)
        return False

async def nightly_run():
    log("Nightly run starting")
    services = check_services()
    log(f"Services: {' | '.join(services)}")

    topic_idx = datetime.now().timetuple().tm_yday % len(TOPICS)
    knowledge = await learn_topic(TOPICS[topic_idx])
    log(f"Learned: {knowledge[:80]}")

    problems_path = COWORK / "self_improve/problems.json"
    if problems_path.exists():
        problems = json.loads(problems_path.read_text())
        pending = [p for p in problems if not p.get("resolved") and p.get("attempts", 0) < 3]
        if pending:
            p = pending[0]
            p["attempts"] = p.get("attempts", 0) + 1
            problems_path.write_text(json.dumps(problems, indent=2))
            success = await attempt_fix(p)
            if success:
                p["resolved"] = True
                problems_path.write_text(json.dumps(problems, indent=2))
                log(f"FIXED: {p['description']}")
            else:
                log(f"FAILED: {p['description']}")

    log("Nightly run complete")

async def run_scheduler():
    while True:
        now = datetime.now()
        next_2am = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if next_2am <= now:
            next_2am += timedelta(days=1)
        wait = (next_2am - now).total_seconds()
        log(f"Next run in {wait/3600:.1f}h")
        await asyncio.sleep(wait)
        await nightly_run()

if __name__ == "__main__":
    asyncio.run(run_scheduler())
