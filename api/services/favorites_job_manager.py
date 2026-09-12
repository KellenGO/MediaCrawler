from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from aggregate_search.models import UnifiedSearchResult
from aggregate_search.protocol import WorkerRequest, parse_event_line
from base.runtime_paths import application_root
from ..schemas.favorites import FavoritePlatformInfo, FavoritesJobRequest, FavoritesJobResponse
from .accounts import mark_login_required_from_search

_ROOT = application_root()
_WORKER = str(_ROOT / "aggregate_search" / "worker.py")
_TIMEOUT = 190


def _command() -> List[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--aggregate-worker"]
    return [sys.executable, _WORKER]


class _Job:
    def __init__(self, request: FavoritesJobRequest):
        self.job_id = uuid.uuid4().hex[:12]
        self.created_at = datetime.now(timezone.utc)
        self.completed_at: Optional[datetime] = None
        self.limit = request.limit_per_platform
        self.order = list(request.platforms)
        self.platforms = {p: FavoritePlatformInfo() for p in self.order}
        self.items: Dict[str, List[UnifiedSearchResult]] = {p: [] for p in self.order}
        self.task: Optional[asyncio.Task] = None
        self.procs: List[asyncio.subprocess.Process] = []

    def terminal(self) -> bool:
        return self.completed_at is not None

    def upsert(self, platform: str, data: dict) -> None:
        result = UnifiedSearchResult(**data)
        for index, existing in enumerate(self.items[platform]):
            if (existing.content_id, existing.content_type) == (result.content_id, result.content_type):
                self.items[platform][index] = result
                return
        if len(self.items[platform]) < self.limit:
            self.items[platform].append(result)

    def response(self) -> FavoritesJobResponse:
        merged: List[UnifiedSearchResult] = []
        maximum = max((len(v) for v in self.items.values()), default=0)
        for index in range(maximum):
            for platform in self.order:
                if index < len(self.items[platform]):
                    merged.append(self.items[platform][index])
        statuses = [info.status for info in self.platforms.values()]
        success = sum(s in ("succeeded", "empty") for s in statuses)
        overall = "running" if not self.terminal() else (
            "completed" if success == len(statuses) else "partial" if success or merged else "failed")
        return FavoritesJobResponse(
            job_id=self.job_id, overall=overall, created_at=self.created_at,
            completed_at=self.completed_at, platforms=self.platforms, results=merged)


class FavoritesJobManager:
    def __init__(self) -> None:
        self._active: Optional[_Job] = None
        self._recent: Optional[_Job] = None

    def is_active(self) -> bool:
        return bool(self._active and not self._active.terminal())

    def active_task(self) -> Optional[asyncio.Task]:
        return self._active.task if self._active else None

    async def create(self, request: FavoritesJobRequest) -> FavoritesJobResponse:
        if self.is_active():
            raise RuntimeError("favorites_in_progress")
        job = _Job(request)
        self._active = self._recent = job
        job.task = asyncio.create_task(self._run(job), name=f"favorites-{job.job_id}")
        return job.response()

    async def get(self, job_id: str) -> Optional[FavoritesJobResponse]:
        job = self._active if self._active and self._active.job_id == job_id else self._recent
        return job.response() if job and job.job_id == job_id else None

    async def latest(self) -> Optional[FavoritesJobResponse]:
        """Return the most recent favourites job so the page can restore it.

        The snapshot (including per-platform status, results and the original
        ``completed_at``) lives in process memory only, so the favourites page
        can render immediately after navigation or a browser refresh without
        re-reading every platform. It is dropped when the backend restarts,
        which is also when the cached copy would be gone anyway.
        """
        return self._recent.response() if self._recent else None

    async def _run(self, job: _Job) -> None:
        try:
            await asyncio.gather(*(self._run_platform(job, platform) for platform in job.order))
        finally:
            job.completed_at = datetime.now(timezone.utc)

    async def _run_platform(self, job: _Job, platform: str) -> None:
        info = job.platforms[platform]
        info.status = "running"
        proc = None
        try:
            env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                   "PYTHONUNBUFFERED": "1"}
            proc = await asyncio.create_subprocess_exec(
                *_command(), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, cwd=str(_ROOT), env=env,
                limit=2 * 1024 * 1024)
            job.procs.append(proc)
            payload = WorkerRequest(job_id=job.job_id, mode="favorites", platform=platform,
                                    limit=job.limit).model_dump_json().encode("utf-8") + b"\n"
            assert proc.stdin and proc.stdout
            proc.stdin.write(payload)
            await proc.stdin.drain()
            proc.stdin.close()

            async def read() -> bool:
                done = False
                while True:
                    raw = await proc.stdout.readline()
                    if not raw:
                        break
                    event = parse_event_line(raw.decode("utf-8", errors="replace").strip())
                    if not event or event.job_id != job.job_id or event.platform != platform:
                        continue
                    if event.event == "result" and isinstance(event.data, dict):
                        try:
                            job.upsert(platform, event.data)
                            info.result_count = len(job.items[platform])
                        except Exception:
                            pass
                    elif event.event == "status":
                        status = (event.data or {}).get("status")
                        if status in ("running", "succeeded", "empty"):
                            info.status = status
                    elif event.event == "error":
                        error = event.data or {}
                        info.status = error.get("type", "failed")
                        info.error_summary = str(error.get("message") or "收藏夹同步失败")[:160]
                        if info.status == "login_required":
                            mark_login_required_from_search(platform)
                    elif event.event == "done":
                        done = True
                        break
                return done

            done = await asyncio.wait_for(read(), timeout=_TIMEOUT)
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            if not done and info.status == "running":
                info.status, info.error_summary = "failed", "平台 worker 未正常结束"
            elif info.status == "running":
                info.status = "succeeded" if job.items[platform] else "empty"
        except asyncio.TimeoutError:
            info.status, info.error_summary = "timed_out", "收藏夹同步超时"
        except Exception as exc:
            info.status, info.error_summary = "failed", type(exc).__name__
        finally:
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            if proc in job.procs:
                job.procs.remove(proc)

    async def cleanup(self) -> None:
        job = self._active
        if job and job.task and not job.task.done():
            job.task.cancel()
            for proc in list(job.procs):
                try:
                    proc.kill()
                except Exception:
                    pass
            await asyncio.gather(job.task, return_exceptions=True)


favorites_job_manager = FavoritesJobManager()
