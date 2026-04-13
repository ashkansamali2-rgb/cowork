#!/usr/bin/env python3
"""Code quality auto-reviewer using Qwen."""
import json
import subprocess
from pathlib import Path

import requests

COWORK   = Path("/Users/ashkansamali/cowork")
QWEN_URL = "http://localhost:8081/v1/chat/completions"


class CodeReviewer:

    def _qwen(self, prompt: str) -> str:
        try:
            r = requests.post(QWEN_URL, json={
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 800,
                "stream": False,
            }, timeout=60)
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return f'{{"issues": [], "error": "{e}"}}'

    def review_file(self, file_path: str) -> dict:
        try:
            code = Path(file_path).read_text(errors="replace")
        except Exception as e:
            return {"issues": [], "error": str(e)}

        if len(code) > 8000:
            code = code[:8000]

        prompt = (
            f"Review this Python code. Find specific bugs, missing error handling, "
            f"and performance issues. Be brief and specific. "
            f'Return JSON only: {{"issues": [{{"line": N, "severity": "high/medium/low", '
            f'"description": "what", "fix": "how"}}]}}\n\n'
            f"Code:\n{code}"
        )

        raw = self._qwen(prompt)
        try:
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {"issues": [], "raw": raw[:200]}

    def review_recent_changes(self) -> dict:
        """Review Python files changed in last commit."""
        try:
            r = subprocess.run(
                ["git", "-C", str(COWORK), "diff", "HEAD~1", "--name-only"],
                capture_output=True, text=True, timeout=10
            )
            changed = [f for f in r.stdout.strip().splitlines()
                       if f.endswith(".py") and not f.startswith("agents/")]
        except Exception:
            changed = []

        reviews = {}
        for rel_path in changed[:3]:
            full_path = COWORK / rel_path
            if full_path.exists():
                reviews[rel_path] = self.review_file(str(full_path))
        return reviews

    def format_review(self, reviews: dict) -> str:
        """Format review results as readable text."""
        if not reviews:
            return "No Python files changed in last commit."

        lines = []
        for file_path, result in reviews.items():
            issues = result.get("issues", [])
            lines.append(f"\n{file_path}:")
            if not issues:
                lines.append("  No issues found.")
            else:
                for issue in issues:
                    sev  = issue.get("severity", "?").upper()
                    line = issue.get("line", "?")
                    desc = issue.get("description", "")
                    fix  = issue.get("fix", "")
                    lines.append(f"  [{sev}] line {line}: {desc}")
                    if fix:
                        lines.append(f"    Fix: {fix}")
        return "\n".join(lines)
