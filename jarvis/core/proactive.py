#!/usr/bin/env python3
"""Proactive Jarvis — periodic background checks and macOS notifications."""
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path

BUILD_LOG = Path("/Users/ashkansamali/cowork/self_improve/build_log.md")
COWORK    = Path("/Users/ashkansamali/cowork")


class ProactiveJarvis:

    def __init__(self):
        self._last_check_hour = -1

    async def check_and_notify(self) -> list[str]:
        suggestions = []

        # Check uncommitted git changes
        try:
            r = subprocess.run(
                ["git", "-C", str(COWORK), "status", "--short"],
                capture_output=True, text=True, timeout=5
            )
            if r.stdout.strip():
                file_count = len([l for l in r.stdout.strip().splitlines() if l.strip()])
                suggestions.append(f"{file_count} uncommitted changes in cowork")
        except Exception:
            pass

        # Check voice daemon
        try:
            r = subprocess.run(["pgrep", "-f", "live_voice"], capture_output=True, timeout=3)
            if r.returncode != 0:
                suggestions.append("Voice daemon is not running")
        except Exception:
            pass

        # Check recent build failures
        if BUILD_LOG.exists():
            try:
                tail = BUILD_LOG.read_text()[-500:]
                if "FAILED" in tail:
                    suggestions.append("Recent improvement attempt failed — check build log")
            except Exception:
                pass

        return suggestions

    def _notify(self, message: str, title: str = "Jarvis"):
        """Send macOS notification."""
        try:
            safe_msg   = message.replace('"', "'")
            safe_title = title.replace('"', "'")
            subprocess.run(["osascript", "-e",
                f'display notification "{safe_msg}" with title "{safe_title}"'],
                timeout=5
            )
        except Exception:
            pass

    async def run_periodic(self):
        """Run checks every 30 minutes, send at most 1 notification per check."""
        while True:
            await asyncio.sleep(1800)  # 30 minutes
            try:
                suggestions = await self.check_and_notify()
                if suggestions:
                    self._notify(suggestions[0])
            except Exception:
                pass
