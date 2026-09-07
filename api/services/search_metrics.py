"""Bounded, process-local search measurements and platform cooldowns.

Keep numeric measurements and status enums only, never keywords or results.
"""

from __future__ import annotations

import math
import time
from collections import Counter, deque
from datetime import datetime, timezone
from statistics import mean, median

from aggregate_search.models import PLATFORM_SLUGS


class PlatformCooldowns:
    BASE_SECONDS = 60
    MAX_SECONDS = 300

    def __init__(self, clock=time.monotonic, wall_clock=time.time):
        self._clock = clock
        self._wall_clock = wall_clock
        self._states = {}

    def remaining(self, platform: str) -> int:
        state = self._states.get(platform)
        return max(0, math.ceil(state[1] - self._clock())) if state else 0

    def until(self, platform: str):
        state = self._states.get(platform)
        return state[2] if state and self.remaining(platform) else None

    def record(self, platform: str, status: str) -> None:
        if status in ("succeeded", "empty"):
            self._states.pop(platform, None)
        elif status == "rate_limited":
            previous = self._states.get(platform)
            strikes = min((previous[0] if previous else 0) + 1, 4)
            seconds = min(self.BASE_SECONDS * 2 ** (strikes - 1), self.MAX_SECONDS)
            until = datetime.fromtimestamp(self._wall_clock() + seconds, timezone.utc).isoformat()
            self._states[platform] = (strikes, self._clock() + seconds, until)


def _duration(values):
    values = sorted(v for v in values if isinstance(v, (int, float))
                    and not isinstance(v, bool) and math.isfinite(v) and v >= 0)
    return {"samples": len(values), "mean_ms": round(mean(values)) if values else None,
            "median_ms": round(median(values)) if values else None,
            "p95_ms": values[math.ceil(len(values) * .95) - 1] if values else None}


class SearchMetrics:
    MAX_JOBS = 100

    def __init__(self):
        self._jobs = deque(maxlen=self.MAX_JOBS)

    def record(self, job) -> None:
        if job.statistics_recorded:
            return
        job.statistics_recorded = True
        platforms = {}
        for platform in job.platforms:
            info, timing = job.platforms_state[platform], job.timings[platform]
            platforms[platform] = {
                "status": info.status, "cache_hit": info.cache_hit,
                "cooldown_skipped": info.cooldown_skipped,
                "worker_run": platform in job.worker_platforms,
                "fallback_active": timing.fallback_active,
                **{key: getattr(timing, key) for key in
                   ("first_result_ms", "total_ms", "spawn_ms", "browser_launch_ms")},
            }
        self._jobs.append({"completed_at": job.completed_at, "total_ms": job.total_ms,
                           "overall": job._compute_overall(), "platforms": platforms})

    def snapshot(self, cooldowns: PlatformCooldowns) -> dict:
        platforms = {}
        for platform in PLATFORM_SLUGS:
            rows = [job["platforms"][platform] for job in self._jobs if platform in job["platforms"]]
            workers = [row for row in rows if row["worker_run"]]
            completed = [row for row in workers if row["status"] != "cancelled"]
            fallback = [row for row in completed if isinstance(row["fallback_active"], bool)]
            successes = sum(row["status"] in ("succeeded", "empty") for row in completed)
            platforms[platform] = {
                "requests": len(rows), "worker_runs": len(workers),
                "successes": successes, "success_samples": len(completed),
                "success_rate": successes / len(completed) if completed else None,
                "cache_hits": sum(row["cache_hit"] for row in rows),
                "cache_hit_rate": sum(row["cache_hit"] for row in rows) / len(rows) if rows else None,
                "cooldown_skips": sum(row["cooldown_skipped"] for row in rows),
                "cancelled_runs": sum(row["status"] == "cancelled" for row in workers),
                "fallback_samples": len(fallback),
                "fallback_rate": sum(row["fallback_active"] for row in fallback) / len(fallback) if fallback else None,
                "failures": dict(Counter(row["status"] for row in completed
                                         if row["status"] not in ("succeeded", "empty"))),
                "cooldown_until": cooldowns.until(platform),
                **{key: _duration(row[key] for row in completed) for key in
                   ("first_result_ms", "total_ms", "spawn_ms", "browser_launch_ms")},
            }
        return {"max_jobs": self.MAX_JOBS, "job_count": len(self._jobs),
                "since": self._jobs[0]["completed_at"] if self._jobs else None,
                "job_total_ms": _duration(job["total_ms"] for job in self._jobs),
                "platforms": platforms}
