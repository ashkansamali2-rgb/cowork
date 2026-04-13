#!/usr/bin/env python3
"""Performance monitor — tracks response times and success rates."""
import json
import time
from pathlib import Path

METRICS_FILE = Path("/Users/ashkansamali/cowork/logs/metrics.json")


class PerformanceMonitor:

    def __init__(self):
        METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = self._load()
        self.response_times: list  = data.get("response_times", [])
        self.success_count:  int   = data.get("success_count", 0)
        self.failure_count:  int   = data.get("failure_count", 0)

    def _load(self) -> dict:
        if METRICS_FILE.exists():
            try:
                return json.loads(METRICS_FILE.read_text())
            except Exception:
                pass
        return {}

    def _save(self):
        try:
            METRICS_FILE.write_text(json.dumps({
                "response_times": self.response_times[-100:],
                "success_count":  self.success_count,
                "failure_count":  self.failure_count,
                "updated":        time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, indent=2))
        except Exception:
            pass

    def record_response(self, duration: float, success: bool):
        self.response_times.append(round(duration, 3))
        if len(self.response_times) > 100:
            self.response_times.pop(0)
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self._save()

    def get_avg_response(self) -> float:
        recent = self.response_times[-20:]
        return round(sum(recent) / len(recent), 3) if recent else 0.0

    def get_success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 100.0
        return round((self.success_count / total) * 100, 1)

    def summary(self) -> str:
        return (
            f"avg response: {self.get_avg_response()}s  "
            f"success rate: {self.get_success_rate()}%  "
            f"total: {self.success_count + self.failure_count}"
        )
